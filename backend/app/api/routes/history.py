from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import BizError, ok
from app.schemas.enums import Market, OrderStatus
from app.services.history_service import HistoryService

router = APIRouter(tags=["history"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _wants_csv(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/csv" in accept


@router.get("/history/orders")
def history_orders(
    request: Request,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    market: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
    strategy_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    svc = HistoryService(db)
    mkt = Market(market) if market else None
    st = OrderStatus(status) if status else None
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)

    if _wants_csv(request):
        csv_text = svc.orders_csv(
            market=mkt,
            symbol=symbol,
            status=st,
            strategy_id=strategy_id,
            start=start_dt,
            end=end_dt,
        )
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="history_orders.csv"'},
        )

    items, total = svc.list_orders(
        market=mkt,
        symbol=symbol,
        status=st,
        strategy_id=strategy_id,
        start=start_dt,
        end=end_dt,
        page=page,
        page_size=page_size,
    )
    return ok(
        {"items": items, "page": page, "page_size": page_size, "total": total},
        correlation_id=correlation_id,
    )


@router.get("/history/trades")
def history_trades(
    request: Request,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    market: str | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    svc = HistoryService(db)
    mkt = Market(market) if market else None
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)

    if _wants_csv(request):
        csv_text = svc.trades_csv(
            market=mkt,
            symbol=symbol,
            strategy_id=strategy_id,
            start=start_dt,
            end=end_dt,
        )
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="history_trades.csv"'},
        )

    items, total = svc.list_trades(
        market=mkt,
        symbol=symbol,
        strategy_id=strategy_id,
        start=start_dt,
        end=end_dt,
        page=page,
        page_size=page_size,
    )
    return ok(
        {"items": items, "page": page, "page_size": page_size, "total": total},
        correlation_id=correlation_id,
    )


@router.get("/history/orders/{client_order_id}/chain")
def history_order_chain(
    client_order_id: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    chain = HistoryService(db).order_chain(client_order_id)
    if chain is None:
        raise BizError("ORDER_NOT_FOUND", f"订单不存在: {client_order_id}", status=404)
    return ok(chain, correlation_id=correlation_id)
