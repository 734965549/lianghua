from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import BizError, ok
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.schemas.error_codes import ErrorCode
from app.schemas.strategy import ConfirmUnknownOrderRequest
from app.services.manual_order_service import manual_order_service
from app.services.order_service import CANCELLABLE, order_service, order_to_dict

router = APIRouter(tags=["orders"])

ATTENTION_ORDER_STATUSES = {
    OrderStatus.PENDING_RISK,
    OrderStatus.SUBMITTING,
    OrderStatus.UNKNOWN,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class CancelOrderBody(BaseModel):
    reason: str = Field(default="user_cancel")


class ManualOrderBody(BaseModel):
    symbol: str
    market: Market
    side: OrderSide
    action: SignalAction = SignalAction.OPEN
    price_type: PriceType = PriceType.MARKET
    quantity: str
    price: str | None = None
    reason: str = "人工下单"


@router.post("/orders")
def create_manual_order(
    body: ManualOrderBody,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = manual_order_service.create_order(
        db,
        symbol=body.symbol,
        market=body.market,
        side=body.side,
        action=body.action,
        price_type=body.price_type,
        quantity=Decimal(body.quantity),
        price=Decimal(body.price) if body.price is not None else None,
        reason=body.reason,
        correlation_id=correlation_id,
    )
    return ok(data, correlation_id=correlation_id)


@router.get("/orders")
def list_orders(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    market: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
    strategy_id: str | None = None,
    scope: Literal["active", "attention", "all"] = Query("all"),
    start: str | None = None,
    end: str | None = None,
):
    offset = (page - 1) * page_size
    mkt = Market(market) if market else None
    st = OrderStatus(status) if status else None
    statuses = (
        CANCELLABLE
        if scope == "active"
        else ATTENTION_ORDER_STATUSES
        if scope == "attention"
        else None
    )
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    rows, total = order_service.list(
        db,
        market=mkt,
        symbol=symbol,
        status=st,
        statuses=statuses,
        strategy_id=strategy_id,
        start=start_dt,
        end=end_dt,
        offset=offset,
        limit=page_size,
    )
    return ok(
        {
            "items": [order_to_dict(r) for r in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "scope": scope,
            "scope_label": {
                "active": "仅可撤委托",
                "attention": "待处理/未知订单",
                "all": "全部委托",
            }[scope],
            "range_start": start_dt.isoformat() if start_dt else None,
            "range_end": end_dt.isoformat() if end_dt else None,
        },
        correlation_id=correlation_id,
    )


@router.get("/orders/{client_order_id}")
def get_order(
    client_order_id: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    from app.services.history_service import HistoryService

    chain = HistoryService(db).order_chain(client_order_id)
    if chain is None:
        raise BizError(ErrorCode.ORDER_NOT_FOUND, f"订单不存在: {client_order_id}", status=404)
    return ok(chain, correlation_id=correlation_id)


@router.post("/orders/{client_order_id}/confirm-unknown")
def confirm_unknown_order(
    client_order_id: str,
    body: ConfirmUnknownOrderRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    if not body.confirm:
        raise BizError(ErrorCode.ORDER_CONFIRM_REQUIRED, "确认 unknown 订单需要 confirm=true")
    resolved = OrderStatus(body.resolved_status)
    row = order_service.confirm_unknown(
        db,
        client_order_id,
        resolved_status=resolved,
        reason=body.reason,
        correlation_id=correlation_id,
    )
    db.commit()
    return ok(order_to_dict(row), correlation_id=correlation_id)


@router.post("/orders/{client_order_id}/cancel")
def cancel_order(
    client_order_id: str,
    body: CancelOrderBody | None = None,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    reason = body.reason if body else "user_cancel"
    row = order_service.cancel(db, client_order_id, reason=reason, correlation_id=correlation_id)
    db.commit()
    return ok(order_to_dict(row), correlation_id=correlation_id)
