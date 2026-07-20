from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.audit_repo import AuditRepository


class AuditService:
    def __init__(self, db: Session, correlation_id: str = "", operator: str = "local_user"):
        self.repo = AuditRepository(db)
        self.correlation_id = correlation_id
        self.operator = operator

    def log(
        self,
        *,
        action: str,
        module: str,
        object_type: str = "",
        object_id: str = "",
        result: str,
        reason: str = "",
        request_summary: dict | None = None,
    ) -> None:
        self.repo.add(
            action=action,
            module=module,
            object_type=object_type,
            object_id=object_id,
            result=result,
            reason=reason,
            request_summary=request_summary or {},
            correlation_id=self.correlation_id,
            operator=self.operator,
            event_time=datetime.now(timezone.utc),
        )
