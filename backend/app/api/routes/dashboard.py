from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.repositories.order_repo import OrderRepository
from app.repositories.risk_repo import RiskRepository
from app.repositories.system_event_repo import SystemEventRepository
from app.services.account_snapshot_service import AccountSnapshotService
from app.services.metrics_service import MetricsService
from app.services.order_service import order_to_dict
from app.services.risk_service import RiskService
from app.services.strategy_service import strategy_service
from app.services.system_service import SystemStateService

router = APIRouter(tags=["dashboard"])


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    state_svc = SystemStateService(db, correlation_id=correlation_id)
    status = state_svc.get_status()
    risk = RiskService(db, correlation_id=correlation_id)
    risk_status = risk.get_status()

    start = _today_start()
    now = datetime.now(timezone.utc)
    metrics = MetricsService(db).compute(range_start=start, range_end=now)
    daily_pnl_map = metrics.get("daily_pnl") or {}
    today_key = start.date().isoformat()
    daily_pnl = daily_pnl_map.get(today_key) or metrics.get("total_pnl") or "0"

    account_snapshot = AccountSnapshotService(db).get_snapshot()
    position_value = Decimal(account_snapshot["market_value"])
    available_cash = Decimal(account_snapshot["available_cash"])

    risk_reject_count = RiskRepository(db).count_rejected(start, now)
    orders, _ = OrderRepository(db).list_orders(offset=0, limit=5)
    latest_orders = [order_to_dict(o) for o in orders]

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
            "daily_pnl": str(daily_pnl),
            "position_value": str(position_value),
            "available_cash": str(available_cash),
            "total_asset": account_snapshot["total_asset"],
            "frozen_cash": account_snapshot["frozen_cash"],
            "other_equity": account_snapshot["other_equity"],
            "account_snapshot_id": account_snapshot["snapshot_id"],
            "account_snapshot_time": account_snapshot["snapshot_time"],
            "account_reconciled": account_snapshot["reconciled"],
            "daily_trade_count": risk_status.get("daily_trade_count", 0),
            "risk_reject_count": risk_reject_count,
            "breaker_active": status["status"] == "circuit_breaker",
            "running_strategies": strategy_service.running_count(),
            "latest_orders": latest_orders,
            "latest_alerts": latest_alerts,
        },
        correlation_id=correlation_id,
    )
