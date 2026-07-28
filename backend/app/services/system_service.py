from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Severity, SystemStatus
from app.schemas.error_codes import ErrorCode
from app.services.audit_service import AuditService
from app.db.models.system_state import SystemState

# 合法状态迁移边
VALID_TRANSITIONS: dict[SystemStatus, set[SystemStatus]] = {
    SystemStatus.INITIALIZING: {SystemStatus.READY},
    SystemStatus.READY: {
        SystemStatus.TRADING,
        SystemStatus.PAUSED,
        SystemStatus.CIRCUIT_BREAKER,
        SystemStatus.EMERGENCY_STOPPED,
        SystemStatus.DEGRADED,
        SystemStatus.OFFLINE,
    },
    SystemStatus.TRADING: {
        SystemStatus.PAUSED,
        SystemStatus.CIRCUIT_BREAKER,
        SystemStatus.EMERGENCY_STOPPED,
        SystemStatus.DEGRADED,
    },
    SystemStatus.PAUSED: {
        SystemStatus.TRADING,
        SystemStatus.CIRCUIT_BREAKER,
        SystemStatus.EMERGENCY_STOPPED,
    },
    SystemStatus.CIRCUIT_BREAKER: {SystemStatus.TRADING, SystemStatus.EMERGENCY_STOPPED},
    SystemStatus.EMERGENCY_STOPPED: {SystemStatus.TRADING},
    SystemStatus.DEGRADED: {
        SystemStatus.TRADING,
        SystemStatus.PAUSED,
        SystemStatus.CIRCUIT_BREAKER,
        SystemStatus.EMERGENCY_STOPPED,
    },
    # offline 仅允许通过启动恢复回到 ready（见 startup_ready）
    SystemStatus.OFFLINE: {SystemStatus.READY},
}


class SystemStateService:
    SINGLETON_ID = 1

    def __init__(self, db: Session, correlation_id: str = ""):
        self.db = db
        self.correlation_id = correlation_id
        self.audit = AuditService(db, correlation_id=correlation_id)
        self.events = SystemEventRepository(db)

    def _get_row(self) -> SystemState | None:
        return self.db.get(SystemState, self.SINGLETON_ID)

    def get_status(self) -> dict:
        row = self._get_row()
        if row is None:
            return {
                "status": SystemStatus.READY.value,
                "status_reason": "",
                "status_since": datetime.now(timezone.utc).isoformat(),
                "breaker_reason": None,
            }
        breaker_reason = row.status_reason if row.status == SystemStatus.CIRCUIT_BREAKER else None
        return {
            "status": row.status.value,
            "status_reason": row.status_reason,
            "status_since": row.status_since.isoformat(),
            "breaker_reason": breaker_reason,
        }

    def ensure_initialized(self) -> SystemState:
        row = self._get_row()
        if row is None:
            row = SystemState(id=self.SINGLETON_ID, status=SystemStatus.INITIALIZING)
            self.db.add(row)
            self.db.flush()
        return row

    def transition(
        self,
        to_status: SystemStatus | str,
        reason: str = "",
        correlation_id: str | None = None,
    ) -> SystemState:
        if isinstance(to_status, str):
            to_status = SystemStatus(to_status)

        row = self.ensure_initialized()
        from_status = row.status

        if to_status not in VALID_TRANSITIONS.get(from_status, set()):
            raise BizError(
                ErrorCode.RISK_INVALID_STATE_TRANSITION,
                f"不允许从 {from_status.value} 迁移到 {to_status.value}",
            )

        cid = correlation_id or self.correlation_id
        now = datetime.now(timezone.utc)
        row.status = to_status
        row.status_reason = reason or ""
        row.status_since = now
        row.updated_at = now
        self.db.flush()

        self.audit.log(
            action="state_transition",
            module="system",
            object_type="system_state",
            object_id=str(row.id),
            result="success",
            reason=reason,
            request_summary={
                "from_status": from_status.value,
                "to_status": to_status.value,
            },
        )
        self.events.add(
            module="system",
            event_code="SYSTEM_STATUS_CHANGED",
            message=f"系统状态 {from_status.value} -> {to_status.value}",
            severity=Severity.INFO,
            payload={
                "from_status": from_status.value,
                "to_status": to_status.value,
                "reason": reason,
                "correlation_id": cid,
            },
        )
        from app.api.ws_hub import broadcast_sync

        broadcast_sync(
            "system.status",
            {
                "status": to_status.value,
                "reason": reason,
                "since": now.isoformat(),
            },
            correlation_id=cid,
        )
        return row

    def startup_ready(self) -> None:
        """启动时：若无行则插入；initializing/offline 自动到 ready。

        circuit_breaker / emergency_stopped 保持不变，不自动解除。
        """
        row = self.ensure_initialized()
        if row.status in {SystemStatus.INITIALIZING, SystemStatus.OFFLINE}:
            self.transition(SystemStatus.READY, reason="系统启动完成", correlation_id="startup")
