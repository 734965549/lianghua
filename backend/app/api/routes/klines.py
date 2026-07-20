from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.services.market_service import market_service

router = APIRouter(tags=["klines"])


@router.get("/klines")
def get_klines(
    market: str = Query(...),
    symbol: str = Query(...),
    interval: str = Query(...),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = market_service.get_klines(
        db,
        market=market,
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        limit=limit,
    )
    return ok(data, correlation_id=correlation_id)
