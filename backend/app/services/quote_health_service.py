from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.time import as_utc, to_utc_iso
from app.core.trading_calendar import is_open_session
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.sdk import manager as sdk_manager

FAILURE_STATES = {
    "source_disconnected",
    "subscription_disconnected",
    "feed_stale",
}


def assess_quote_health(
    db: Session,
    *,
    targets: list[tuple[Market, str]] | None = None,
    now: datetime | None = None,
    timeout_seconds: int = 10,
) -> dict:
    """Classify market closure, source failure and subscription failure."""
    from app.services.market_service import market_service

    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    subscriptions = market_service.get_subscribed() if market_service.started else []
    monitored_targets = targets if targets is not None else subscriptions
    if not monitored_targets:
        return {
            "state": "not_monitored",
            "breaker_required": False,
            "trade_ready": True,
            "checked_at": to_utc_iso(checked_at),
            "timeout_seconds": timeout_seconds,
            "items": [],
        }

    repo = MarketRepository(db)
    items: list[dict] = []
    for market, symbol in dict.fromkeys(monitored_targets):
        market = Market(market)
        if not is_open_session(market, checked_at, symbol=symbol):
            items.append(
                {
                    "market": market.value,
                    "symbol": symbol,
                    "state": "market_closed",
                    "blocking": False,
                }
            )
            continue

        adapter = sdk_manager.get_adapter_for_market(market)
        if not sdk_manager.is_adapter_connected(adapter):
            items.append(
                {
                    "market": market.value,
                    "symbol": symbol,
                    "state": "source_disconnected",
                    "blocking": True,
                }
            )
            continue

        row = repo.get_latest_quote(market, symbol)
        if row is None:
            items.append(
                {
                    "market": market.value,
                    "symbol": symbol,
                    "state": "subscription_disconnected",
                    "blocking": True,
                    "reason": "no_valid_quote",
                }
            )
            continue

        age = max(0.0, (checked_at - as_utc(row.quote_time)).total_seconds())
        stale = age > timeout_seconds
        items.append(
            {
                "market": market.value,
                "symbol": symbol,
                "state": "feed_stale" if stale else "healthy",
                "blocking": stale,
                "quote_time": to_utc_iso(row.quote_time),
                "age_seconds": round(age, 3),
            }
        )

    states = {item["state"] for item in items}
    if "source_disconnected" in states:
        state = "source_disconnected"
    elif "subscription_disconnected" in states:
        state = "subscription_disconnected"
    elif "feed_stale" in states:
        state = "feed_stale"
    elif "healthy" in states:
        state = "healthy"
    else:
        state = "market_closed"
    breaker_required = any(item["state"] in FAILURE_STATES for item in items)
    return {
        "state": state,
        "breaker_required": breaker_required,
        "trade_ready": not breaker_required,
        "checked_at": to_utc_iso(checked_at),
        "timeout_seconds": timeout_seconds,
        "items": items,
    }
