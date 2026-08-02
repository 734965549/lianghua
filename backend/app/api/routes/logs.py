from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.repositories.audit_repo import AuditRepository
from app.repositories.system_event_repo import SystemEventRepository

router = APIRouter(tags=["logs"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@router.get("/logs/audit")
def list_audit_logs(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    module: str | None = None,
    action: str | None = None,
    object_type: str | None = None,
    result: str | None = None,
    query: str | None = None,
    start: str | None = None,
    end: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    repo = AuditRepository(db)
    items, total = repo.list_paginated(
        page=page,
        page_size=page_size,
        module=module,
        action=action,
        object_type=object_type,
        result=result,
        query=query,
        start=_parse_dt(start),
        end=_parse_dt(end),
    )
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "event_time": row.event_time.isoformat(),
                    "action": row.action,
                    "module": row.module,
                    "object_type": row.object_type,
                    "object_id": row.object_id,
                    "result": row.result,
                    "reason": row.reason,
                    "request_summary": row.request_summary,
                    "correlation_id": row.correlation_id,
                    "operator": row.operator,
                }
                for row in items
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        correlation_id=correlation_id,
    )


@router.get("/logs/system-events")
def list_system_events(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    severity: str | None = None,
    module: str | None = None,
    resolved: bool | None = None,
    query: str | None = None,
    start: str | None = None,
    end: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    repo = SystemEventRepository(db)
    items, total = repo.list_paginated(
        page=page,
        page_size=page_size,
        severity=severity,
        module=module,
        resolved=resolved,
        query=query,
        start=_parse_dt(start),
        end=_parse_dt(end),
    )
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "event_time": row.event_time.isoformat(),
                    "severity": row.severity.value,
                    "module": row.module,
                    "event_code": row.event_code,
                    "message": row.message,
                    "resolved": row.resolved,
                    "payload": row.payload,
                }
                for row in items
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        correlation_id=correlation_id,
    )
