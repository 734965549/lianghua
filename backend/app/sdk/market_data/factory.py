from app.schemas.enums import Market
from app.sdk.base import SDKNotConfigured
from app.sdk.market_data.base import MarketDataAdapter


_PROVIDER_MAP: dict[str, type[MarketDataAdapter]] = {}


def _register(provider: str, cls: type[MarketDataAdapter]) -> None:
    _PROVIDER_MAP[provider] = cls


def _ensure_registry() -> None:
    """延迟导入，避免循环依赖并减少启动开销。"""
    if _PROVIDER_MAP:
        return
    from app.sdk.market_data.ifind_adapter import IFindAdapter
    from app.sdk.market_data.rqdata_adapter import RQDataAdapter
    from app.sdk.market_data.tdx_adapter import TdxAdapter
    from app.sdk.market_data.tushare_adapter import TushareProAdapter
    from app.sdk.market_data.wind_adapter import WindAdapter

    _register("ifind", IFindAdapter)
    _register("tdx", TdxAdapter)
    _register("tushare_pro", TushareProAdapter)
    _register("rqdata", RQDataAdapter)
    _register("wind", WindAdapter)


def get_market_data_adapter(market: str | Market, provider: str, config: dict) -> MarketDataAdapter:
    """根据 provider 名称创建行情适配器。

    Args:
        market: 市场枚举或字符串。
        provider: 行情源标识，如 tushare_pro / rqdata / wind / mock。
        config: 配置字典，包含 token/账号/轮询间隔等。

    Returns:
        MarketDataAdapter 实例。

    Raises:
        SDKNotConfigured: provider 未配置或对应 SDK 未安装。
        ValueError: 不支持的 provider。
    """
    if isinstance(market, str):
        market = Market(market)

    if provider in ("", "mock"):
        raise SDKNotConfigured(f"行情 provider 为 {provider!r} 时不应创建 MarketDataAdapter，请使用 TradingAdapter")

    _ensure_registry()
    cls = _PROVIDER_MAP.get(provider)
    if cls is None:
        raise ValueError(f"不支持的行情数据源: {provider}")
    return cls(market=market, config=config)


def list_supported_providers() -> list[str]:
    """返回当前已注册的专业行情数据源列表。"""
    _ensure_registry()
    return list(_PROVIDER_MAP.keys())
