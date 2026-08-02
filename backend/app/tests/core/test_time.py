from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.time import market_time_as_utc, to_utc_iso


def test_to_utc_iso_treats_naive_database_value_as_utc():
    assert to_utc_iso(datetime(2026, 7, 28, 19, 34)) == "2026-07-28T19:34:00+00:00"


def test_to_utc_iso_converts_shanghai_time_to_utc():
    value = datetime(2026, 7, 29, 3, 34, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert to_utc_iso(value) == "2026-07-28T19:34:00+00:00"


def test_market_time_as_utc_interprets_naive_vendor_time_as_shanghai():
    value = datetime(2026, 7, 31, 15, 0)
    assert market_time_as_utc(value).isoformat() == "2026-07-31T07:00:00+00:00"
