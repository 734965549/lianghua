from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.schemas.enums import Market
from app.schemas.market import QuoteSubscriptionRequest
from app.services.market_service import market_service

router = APIRouter(tags=["quotes"])


@router.get("/quotes")
def list_quotes(
    market: str | None = Query(None),
    symbols: str | None = Query(None, description="逗号分隔标的"),
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    mkt = Market(market) if market else None
    data = market_service.list_quotes(db, market=mkt, symbols=symbol_list)
    return ok(data, correlation_id=correlation_id)


@router.get("/quotes/{market}/{symbol}")
def get_quote(
    market: str,
    symbol: str,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    data = market_service.get_quote(db, market, symbol)
    return ok(data, correlation_id=correlation_id)


@router.post("/quotes/subscriptions")
def update_subscriptions(
    body: QuoteSubscriptionRequest,
    correlation_id: str = Depends(get_correlation_id),
):
    subscribed = market_service.subscribe(body.symbols, body.market)
    return ok({"subscribed": subscribed}, correlation_id=correlation_id)
