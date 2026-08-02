from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import BizError, ok
from app.schemas.enums import Market
from app.schemas.error_codes import ErrorCode
from app.schemas.market import QuoteSubscriptionRequest
from app.services.market_service import market_service
from app.services.quote_health_service import assess_quote_health
from app.services.subscription_service import subscription_manager

router = APIRouter(tags=["quotes"])


def _parse_health_targets(value: str | None) -> list[tuple[Market, str]] | None:
    if not value:
        return None
    raw_targets = [item.strip() for item in value.split(",") if item.strip()]
    if len(raw_targets) > 200:
        raise BizError(
            ErrorCode.SYS_VALIDATION_ERROR,
            "单次最多查询 200 个行情健康标的",
            status=422,
        )

    targets: list[tuple[Market, str]] = []
    for raw_target in raw_targets:
        market_text, separator, symbol = raw_target.partition(":")
        if not separator or not symbol.strip():
            raise BizError(
                ErrorCode.SYS_VALIDATION_ERROR,
                f"无效的行情健康标的: {raw_target}",
                status=422,
            )
        try:
            market = Market(market_text.strip())
        except ValueError as exc:
            raise BizError(
                ErrorCode.SYS_VALIDATION_ERROR,
                f"无效的市场类型: {market_text}",
                status=422,
            ) from exc
        targets.append((market, symbol.strip()))
    return targets


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


@router.get("/quotes/health")
def get_quote_health(
    targets: str | None = Query(
        None,
        description="逗号分隔的 market:symbol，仅评估指定标的",
    ),
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    """返回后端判定的逐标的行情健康状态，避免前端把正常休市误报为停更。"""
    return ok(
        assess_quote_health(db, targets=_parse_health_targets(targets)),
        correlation_id=correlation_id,
    )


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
    added = subscription_manager.subscribe(body.subscriber_id, body.market, body.symbols)
    return ok({"subscribed": body.symbols, "added": added}, correlation_id=correlation_id)


@router.delete("/quotes/subscriptions")
def remove_subscriptions(
    body: QuoteSubscriptionRequest,
    correlation_id: str = Depends(get_correlation_id),
):
    removed = subscription_manager.unsubscribe(body.subscriber_id, body.market, body.symbols)
    return ok({"unsubscribed": body.symbols, "removed": removed}, correlation_id=correlation_id)
