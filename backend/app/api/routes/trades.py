from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.core.time import to_utc_iso
from app.core.trading_calendar import shanghai_day_bounds
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import Market
from app.services.trade_service import trade_to_dict

router = APIRouter(tags=["trades"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@router.get("/trades")
def list_trades(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    market: str | None = None,
    symbol: str | None = None,
    client_order_id: str | None = None,
    strategy_id: str | None = None,
    scope: Literal["today", "all"] = Query("all"),
    start: str | None = None,
    end: str | None = None,
):
    offset = (page - 1) * page_size
    mkt = Market(market) if market else None
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    if scope == "today":
        start_dt, end_dt = shanghai_day_bounds()
    repo = TradeRepository(db)
    rows, total = repo.list_trades(
        market=mkt,
        symbol=symbol,
        client_order_id=client_order_id,
        strategy_id=strategy_id,
        start=start_dt,
        end=end_dt,
        offset=offset,
        limit=page_size,
    )
    return ok(
        {
            "items": [trade_to_dict(r) for r in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "scope": scope,
            "scope_label": "今日成交（上海时区）" if scope == "today" else "全部成交",
            "range_start": to_utc_iso(start_dt),
            "range_end": to_utc_iso(end_dt),
            "timezone": "Asia/Shanghai",
        },
        correlation_id=correlation_id,
    )
