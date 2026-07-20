from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import Market
from app.services.trade_service import trade_to_dict

router = APIRouter(tags=["trades"])


@router.get("/trades")
def list_trades(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    market: str | None = None,
    symbol: str | None = None,
    client_order_id: str | None = None,
):
    offset = (page - 1) * page_size
    mkt = Market(market) if market else None
    repo = TradeRepository(db)
    rows, total = repo.list_trades(
        market=mkt,
        symbol=symbol,
        client_order_id=client_order_id,
        offset=offset,
        limit=page_size,
    )
    return ok(
        {
            "items": [trade_to_dict(r) for r in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        correlation_id=correlation_id,
    )
