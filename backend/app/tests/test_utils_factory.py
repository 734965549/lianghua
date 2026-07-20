"""time_utils 与 sdk factory 单元测试。"""

from datetime import datetime, timezone

import pytest

from app.schemas.enums import Market
from app.services.time_utils import is_in_session
from app.sdk.factory import get_adapter


@pytest.mark.unit
def test_is_in_session_empty_allows_all():
    dt = datetime(2026, 7, 20, 10, 30, tzinfo=timezone.utc)
    assert is_in_session(dt, []) is True


@pytest.mark.unit
def test_is_in_session_stock_day_window():
    dt = datetime(2026, 7, 20, 2, 30, tzinfo=timezone.utc)  # 北京时间 10:30 周一
    sessions = [{"days": ["mon", "tue", "wed", "thu", "fri"], "start": "09:30", "end": "15:00"}]
    assert is_in_session(dt, sessions) is True


@pytest.mark.unit
def test_is_in_session_outside_window():
    dt = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)  # 北京时间 16:00
    sessions = [{"days": ["mon", "tue", "wed", "thu", "fri"], "start": "09:30", "end": "15:00"}]
    assert is_in_session(dt, sessions) is False


@pytest.mark.unit
def test_get_adapter_mock():
    adapter = get_adapter(Market.STOCK, {"mode": "mock"})
    from app.sdk.mock_adapter import MockTradingAdapter

    assert isinstance(adapter, MockTradingAdapter)


@pytest.mark.unit
def test_get_adapter_real_stock():
    adapter = get_adapter("stock", {"mode": "real", "stock_sdk_path": "", "stock_sdk_account": "SIM"})
    from app.sdk.stock_adapter import StockTradingAdapter

    assert isinstance(adapter, StockTradingAdapter)
