from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.system_event import SystemEvent
from app.repositories.base import BaseRepository
from app.schemas.enums import Severity


class SystemEventRepository(BaseRepository[SystemEvent]):
    model = SystemEvent

    def add(
        self,
        *,
        module: str,
        event_code: str,
        message: str = "",
        severity: Severity = Severity.INFO,
        resolved: bool = False,
        payload: dict | None = None,
        event_time: datetime | None = None,
    ) -> SystemEvent:
        row = SystemEvent(
            module=module,
            event_code=event_code,
            message=message,
            severity=severity,
            resolved=resolved,
            payload=payload or {},
            event_time=event_time or datetime.now(timezone.utc),
        )
        return super().add(row)

    def list_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        severity: str | None = None,
        module: str | None = None,
        resolved: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[list[SystemEvent], int]:
        q = self.db.query(SystemEvent)
        if severity:
            q = q.filter(SystemEvent.severity == severity)
        if module:
            q = q.filter(SystemEvent.module == module)
        if resolved is not None:
            q = q.filter(SystemEvent.resolved == resolved)
        if start:
            q = q.filter(SystemEvent.event_time >= start)
        if end:
            q = q.filter(SystemEvent.event_time <= end)

        total = q.count()
        offset = max(page - 1, 0) * page_size
        items = q.order_by(SystemEvent.event_time.desc()).offset(offset).limit(page_size).all()
        return items, total

    def list_recent(self, limit: int = 5) -> list[SystemEvent]:
        return (
            self.db.query(SystemEvent)
            .order_by(SystemEvent.event_time.desc())
            .limit(limit)
            .all()
        )
