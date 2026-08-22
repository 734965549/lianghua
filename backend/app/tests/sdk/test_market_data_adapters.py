import pytest

from app.schemas.enums import Market
from app.sdk.base import SDKNotConfigured
from app.sdk.market_data.factory import get_market_data_adapter, list_supported_providers


def test_list_supported_providers() -> None:
    providers = list_supported_providers()
    assert set(providers) == {
        "ifind",
        "tdx",
        "tushare_pro",
        "rqdata",
        "wind",
        "tqsdk",
    }


def test_factory_rejects_tqsdk_for_stock() -> None:
    with pytest.raises(ValueError, match="仅支持期货"):
        get_market_data_adapter(Market.STOCK, "tqsdk", {})


def test_tushare_requires_config() -> None:
    with pytest.raises(SDKNotConfigured):
        adapter = get_market_data_adapter(Market.STOCK, "tushare_pro", {})
        adapter.connect()


def test_rqdata_requires_config() -> None:
    with pytest.raises(SDKNotConfigured):
        adapter = get_market_data_adapter(Market.STOCK, "rqdata", {})
        adapter.connect()


def test_wind_requires_config() -> None:
    with pytest.raises(SDKNotConfigured):
        adapter = get_market_data_adapter(Market.STOCK, "wind", {})
        adapter.connect()


def test_factory_rejects_mock() -> None:
    with pytest.raises(SDKNotConfigured):
        get_market_data_adapter(Market.STOCK, "mock", {})


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="不支持的行情数据源"):
        get_market_data_adapter(Market.STOCK, "unknown", {})
