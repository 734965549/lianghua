from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.response import ok
from app.core.config import settings
from app.core.trading_calendar import trading_calendar_status
from app.db.session import check_database
from app.schemas.enums import SystemStatus
from app.services.system_service import SystemStateService

router = APIRouter(tags=["health"])


from app.sdk import manager as sdk_manager


def _sdk_health_status(market: str) -> str:
    from app.schemas.enums import Market

    if settings.sdk_mode == "mock":
        return "connected"
    m = Market.STOCK if market == "stock" else Market.FUTURES
    try:
        adapter = sdk_manager.get_adapter_for_market(m)
        if sdk_manager.is_adapter_connected(adapter):
            return "connected"
        return "disconnected"
    except Exception:
        path = settings.stock_sdk_path if market == "stock" else settings.futures_sdk_path
        account = settings.stock_account if market == "stock" else settings.futures_account
        if not path or not account:
            return "not_configured"
        return "disconnected"


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    cid = getattr(request.state, "correlation_id", "")
    database = check_database()
    stock_sdk = _sdk_health_status("stock")
    futures_sdk = _sdk_health_status("futures")

    try:
        system_status = SystemStateService(db).get_status()["status"]
    except Exception:
        system_status = SystemStatus.READY.value

    return ok(
        {
            "api": "ok",
            "database": database,
            "stock_sdk": stock_sdk,
            "futures_sdk": futures_sdk,
            "trading_calendar": trading_calendar_status(),
            "system_status": system_status,
            "version": "0.1.0",
        },
        correlation_id=cid,
    )
