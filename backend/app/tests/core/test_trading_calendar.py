from datetime import date, datetime

import pytest

from app.core.config import settings
from app.core.trading_calendar import (
    SHANGHAI_TZ,
    TradingCalendarError,
    is_open_session,
    is_trading_day,
    trading_calendar_status,
    validate_trading_calendar,
)
from app.schemas.enums import Market


def _local(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SHANGHAI_TZ)


def test_stock_session_keeps_midday_break():
    assert is_open_session(Market.STOCK, _local(2026, 7, 31, 9, 30)) is True
    assert is_open_session(Market.STOCK, _local(2026, 7, 31, 11, 45)) is False
    assert is_open_session(Market.STOCK, _local(2026, 7, 31, 15, 0)) is False


def test_cffex_index_and_bond_sessions_are_product_specific():
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 9, 15), symbol="IF2608") is False
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 9, 30), symbol="IF2608") is True
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 15, 10), symbol="IF2608") is False
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 15, 10), symbol="T2609") is True
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 15, 15), symbol="T2609") is False


def test_commodity_day_session_honors_exchange_breaks():
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 10, 10), symbol="RB2610") is True
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 10, 20), symbol="RB2610") is False
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 13, 15), symbol="RB2610") is False
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 13, 30), symbol="RB2610") is True


def test_night_session_close_depends_on_product_and_crosses_midnight():
    friday_night = _local(2026, 7, 31, 23, 30)
    saturday_early = _local(2026, 8, 1, 1, 30)

    assert is_open_session(Market.FUTURES, friday_night, symbol="RB2610") is False
    assert is_open_session(Market.FUTURES, friday_night, symbol="AU2612") is True
    assert is_open_session(Market.FUTURES, saturday_early, symbol="AU2612") is True
    assert is_open_session(Market.FUTURES, saturday_early, symbol="CU2610") is False


def test_day_only_exchange_does_not_inherit_generic_night_session():
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 21, 30), symbol="IF2608") is False
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 21, 30), symbol="LC2609") is False
    assert is_open_session(Market.FUTURES, _local(2026, 7, 31, 21, 30), symbol="UNKNOWN1") is False


def test_official_holidays_are_closed_without_manual_configuration(monkeypatch):
    monkeypatch.setattr(settings, "stock_market_holidays", "")
    monkeypatch.setattr(settings, "futures_market_holidays", "")

    for holiday in (
        date(2026, 1, 2),
        date(2026, 2, 23),
        date(2026, 4, 6),
        date(2026, 5, 4),
        date(2026, 6, 19),
        date(2026, 9, 25),
        date(2026, 10, 7),
    ):
        assert is_trading_day(Market.STOCK, holiday) is False
        assert is_trading_day(Market.FUTURES, holiday) is False


def test_holiday_eve_night_session_is_closed_without_manual_configuration(
    monkeypatch,
):
    monkeypatch.setattr(settings, "futures_market_holidays", "")

    assert is_open_session(
        Market.FUTURES,
        _local(2026, 9, 30, 21, 30),
        symbol="AU2612",
    ) is False


def test_calendar_validation_reports_full_current_year_coverage():
    status = validate_trading_calendar(date(2026, 7, 31))

    assert status["provider"] == "exchange-calendars:XSHG"
    assert status["supported"] is True
    assert status["supported_through"] >= "2026-12-31"
    assert status["weekday_holiday_count"] >= 1
    assert trading_calendar_status(date(2026, 7, 31)) == status


def test_calendar_validation_fails_closed_outside_provider_range():
    with pytest.raises(TradingCalendarError, match="未覆盖 2027 完整年度"):
        validate_trading_calendar(date(2027, 1, 1))
