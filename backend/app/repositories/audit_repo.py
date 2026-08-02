from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    def add(
        self,
        *,
        action: str,
        module: str,
        object_type: str = "",
        object_id: str = "",
        result: str,
        reason: str = "",
        request_summary: dict | None = None,
        correlation_id: str = "",
        operator: str = "local_user",
        event_time: datetime | None = None,
    ) -> AuditLog:
        row = AuditLog(
            action=action,
            module=module,
            object_type=object_type,
            object_id=object_id,
            result=result,
            reason=reason,
            request_summary=request_summary or {},
            correlation_id=correlation_id,
            operator=operator,
            event_time=event_time or datetime.now(timezone.utc),
        )
        return super().add(row)

    def list_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        module: str | None = None,
        action: str | None = None,
        object_type: str | None = None,
        result: str | None = None,
        query: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        q = self.db.query(AuditLog)
        if module:
            q = q.filter(AuditLog.module == module)
        if action:
            q = q.filter(AuditLog.action == action)
        if object_type:
            q = q.filter(AuditLog.object_type == object_type)
        if result:
            q = q.filter(AuditLog.result == result)
        if query:
            pattern = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    AuditLog.action.ilike(pattern),
                    AuditLog.module.ilike(pattern),
                    AuditLog.object_type.ilike(pattern),
                    AuditLog.object_id.ilike(pattern),
                    AuditLog.reason.ilike(pattern),
                    AuditLog.correlation_id.ilike(pattern),
                )
            )
        if start:
            q = q.filter(AuditLog.event_time >= start)
        if end:
            q = q.filter(AuditLog.event_time <= end)

        total = q.count()
        offset = max(page - 1, 0) * page_size
        items = q.order_by(AuditLog.event_time.desc()).offset(offset).limit(page_size).all()
        return items, total
