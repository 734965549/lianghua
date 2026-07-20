from datetime import datetime
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models.risk_check import RiskCheck
from app.db.models.risk_config import RiskConfig
from app.repositories.base import BaseRepository
from app.schemas.enums import RiskResult


class RiskRepository(BaseRepository[RiskConfig]):
    model = RiskConfig

    SINGLETON_ID = 1

    def get_config(self) -> RiskConfig | None:
        return self.db.get(RiskConfig, self.SINGLETON_ID)

    def ensure_config(self) -> RiskConfig:
        row = self.get_config()
        if row is None:
            row = RiskConfig(
                id=self.SINGLETON_ID,
                allowed_symbols=["600000.SH", "IF2509"],
                blocked_symbols=["ST001.SH"],
                trading_sessions=[],
            )
            self.add(row)
        return row

    def update_config(self, updates: dict) -> RiskConfig:
        row = self.ensure_config()
        for key, value in updates.items():
            if hasattr(row, key) and value is not None:
                setattr(row, key, value)
        self.db.flush()
        return row

    def config_to_dict(self, row: RiskConfig | None = None) -> dict:
        row = row or self.ensure_config()
        return {
            "allowed_symbols": row.allowed_symbols or [],
            "blocked_symbols": row.blocked_symbols or [],
            "trading_sessions": row.trading_sessions or [],
            "max_order_amount": str(row.max_order_amount),
            "max_order_quantity": str(row.max_order_quantity),
            "max_symbol_position": str(row.max_symbol_position),
            "max_total_position": str(row.max_total_position),
            "daily_loss_limit": str(row.daily_loss_limit),
            "daily_trade_count_limit": row.daily_trade_count_limit,
            "sdk_disconnect_timeout_seconds": row.sdk_disconnect_timeout_seconds,
            "quote_stale_timeout_seconds": row.quote_stale_timeout_seconds,
            "consecutive_order_fail_limit": row.consecutive_order_fail_limit,
            "duplicate_signal_window_seconds": row.duplicate_signal_window_seconds,
            "auto_cancel_on_breaker": row.auto_cancel_on_breaker,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def add_check(
        self,
        *,
        signal_id: UUID | None,
        client_order_id: str | None,
        result: RiskResult,
        rule_code: str,
        reason: str,
        checked_at: datetime,
        snapshot: dict,
    ) -> RiskCheck:
        row = RiskCheck(
            signal_id=signal_id,
            client_order_id=client_order_id,
            result=result,
            rule_code=rule_code,
            reason=reason,
            checked_at=checked_at,
            snapshot=snapshot,
        )
        return self.add(row)

    def list_checks(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        result: RiskResult | None = None,
        client_order_id: str | None = None,
        signal_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[list[RiskCheck], int]:
        q = self.db.query(RiskCheck)
        if result is not None:
            q = q.filter(RiskCheck.result == result)
        if client_order_id:
            q = q.filter(RiskCheck.client_order_id == client_order_id)
        if signal_id is not None:
            q = q.filter(RiskCheck.signal_id == signal_id)
        if start is not None:
            q = q.filter(RiskCheck.checked_at >= start)
        if end is not None:
            q = q.filter(RiskCheck.checked_at <= end)
        total = q.count()
        rows = q.order_by(desc(RiskCheck.checked_at)).offset(offset).limit(limit).all()
        return rows, total

    def count_rejected(self, range_start: datetime, range_end: datetime) -> int:
        return (
            self.db.query(RiskCheck)
            .filter(
                RiskCheck.result == RiskResult.REJECTED,
                RiskCheck.checked_at >= range_start,
                RiskCheck.checked_at <= range_end,
            )
            .count()
        )

    def count_breaker(self, range_start: datetime, range_end: datetime) -> int:
        from app.db.models.system_event import SystemEvent

        return (
            self.db.query(SystemEvent)
            .filter(
                SystemEvent.event_code.in_(["CIRCUIT_BREAKER", "EMERGENCY_STOP"]),
                SystemEvent.event_time >= range_start,
                SystemEvent.event_time <= range_end,
            )
            .count()
        )

    def list_by_client_order_id(self, client_order_id: str) -> list[RiskCheck]:
        return (
            self.db.query(RiskCheck)
            .filter(RiskCheck.client_order_id == client_order_id)
            .order_by(RiskCheck.checked_at.asc())
            .all()
        )
