from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.schemas.enums import Market, OrderStatus
from app.schemas.strategy import ConfirmUnknownOrderRequest
from app.services.order_service import order_service, order_to_dict

router = APIRouter(tags=["orders"])


class CancelOrderBody(BaseModel):
    reason: str = Field(default="user_cancel")


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
):
    offset = (page - 1) * page_size
    mkt = Market(market) if market else None
    st = OrderStatus(status) if status else None
    rows, total = order_service.list(
        db,
        market=mkt,
        symbol=symbol,
        status=st,
        strategy_id=strategy_id,
        offset=offset,
        limit=page_size,
    )
    return ok(
        {
            "items": [order_to_dict(r) for r in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
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
        from app.api.response import BizError

        raise BizError("ORDER_NOT_FOUND", f"订单不存在: {client_order_id}", status=404)
    return ok(chain, correlation_id=correlation_id)


@router.post("/orders/{client_order_id}/confirm-unknown")
def confirm_unknown_order(
    client_order_id: str,
    body: ConfirmUnknownOrderRequest,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    from app.api.response import BizError

    if not body.confirm:
        raise BizError("ORDER_CONFIRM_REQUIRED", "确认 unknown 订单需要 confirm=true")
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
