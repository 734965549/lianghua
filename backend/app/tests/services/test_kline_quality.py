from datetime import datetime, timezone
from decimal import Decimal

from app.core.config import settings
from app.core.trading_calendar import (
    is_trading_day,
    market_date,
)
from app.schemas.enums import Market
from app.sdk.models import KlineBar
from app.services.kline_quality import prepare_kline, stamp_kline_source


def _bar(bar_time: datetime) -> KlineBar:
    return KlineBar(
        symbol="600000.SH",
        market=Market.STOCK,
        interval="1d",
        bar_time=bar_time,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        volume=Decimal("1000"),
        raw_payload={"provider": "test_feed"},
    )


def test_daily_bar_is_canonicalized_by_shanghai_market_date():
    source_time = datetime(2026, 7, 29, 15, 30, tzinfo=timezone.utc)

    prepared = prepare_kline(_bar(source_time))

    assert prepared.accepted is True
    assert market_date(prepared.bar.bar_time).isoformat() == "2026-07-29"
    assert prepared.bar.bar_time == datetime(
        2026, 7, 28, 16, 0, tzinfo=timezone.utc
    )
    assert prepared.bar.raw_payload["source"] == "test_feed"
    assert prepared.bar.raw_payload["quality_status"] == "accepted"


def test_weekend_daily_bar_is_quarantined():
    prepared = prepare_kline(
        _bar(datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc))
    )

    assert prepared.accepted is False
    assert prepared.reasons == ("non_trading_day",)


def test_configured_stock_holiday_is_closed(monkeypatch):
    monkeypatch.setattr(settings, "stock_market_holidays", "2026-07-29")

    assert is_trading_day(Market.STOCK, datetime(2026, 7, 29).date()) is False
    assert is_trading_day(Market.FUTURES, datetime(2026, 7, 29).date()) is True


def test_naive_timestamp_is_quarantined():
    prepared = prepare_kline(_bar(datetime(2026, 7, 29, 8, 0)))

    assert prepared.accepted is False
    assert "timezone_missing" in prepared.reasons


def test_source_is_stamped_when_adapter_payload_has_no_provider():
    source_bar = _bar(datetime(2026, 7, 29, tzinfo=timezone.utc)).model_copy(
        update={"raw_payload": {"vendor_field": 1}}
    )

    stamped = stamp_kline_source([source_bar], "ifind")

    assert stamped[0].raw_payload["provider"] == "ifind"
    assert stamped[0].raw_payload["vendor_field"] == 1
