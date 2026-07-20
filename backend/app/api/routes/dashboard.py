from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.repositories.system_event_repo import SystemEventRepository
from app.services.system_service import SystemStateService

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    state_svc = SystemStateService(db, correlation_id=correlation_id)
    status = state_svc.get_status()
    events = SystemEventRepository(db).list_recent(limit=5)
    latest_alerts = [
        {
            "id": e.id,
            "event_time": e.event_time.isoformat(),
            "severity": e.severity.value,
            "module": e.module,
            "event_code": e.event_code,
            "message": e.message,
            "resolved": e.resolved,
            "payload": e.payload,
        }
        for e in events
    ]
    return ok(
        {
            "system_status": status["status"],
            "daily_pnl": "0",
            "position_value": "0",
            "available_cash": "0",
            "daily_trade_count": 0,
            "risk_reject_count": 0,
            "breaker_active": status["status"] == "circuit_breaker",
            "running_strategies": 0,
            "latest_orders": [],
            "latest_alerts": latest_alerts,
        },
        correlation_id=correlation_id,
    )
