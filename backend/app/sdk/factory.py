from app.schemas.enums import Market
from app.sdk.base import TradingAdapter
from app.sdk.market_data.backed_adapter import MarketDataBackedAdapter
from app.sdk.market_data.factory import get_market_data_adapter
from app.sdk.mock_adapter import MockTradingAdapter


_PROFESSIONAL_PROVIDERS = {"ifind", "tdx", "tushare_pro", "rqdata", "wind", "tqsdk"}


def resolve_quote_provider(market: Market, config: dict) -> str:
    """按市场解析行情源；未配置拆分字段时回退旧的 quote_provider。"""
    legacy = str(config.get("quote_provider") or "mock").strip().lower()
    if market == Market.STOCK:
        specific = str(config.get("stock_quote_provider") or "").strip().lower()
    else:
        specific = str(config.get("futures_quote_provider") or "").strip().lower()
    return specific or legacy


def get_adapter(market: str | Market, config: dict) -> TradingAdapter:
    """根据配置返回适配器。MVP 默认返回 Mock。"""
    if isinstance(market, str):
        market = Market(market)
    mode = config.get("mode", "mock")
    quote_provider = resolve_quote_provider(market, config)

    # 行情源 = akshare 时，用 AkshareAdapter（行情真 + 交易模拟）
    if quote_provider == "akshare":
        from app.sdk.akshare_adapter import AkshareAdapter

        return AkshareAdapter(market=market, config=config)

    # 专业行情数据源：行情由 MarketDataAdapter 提供，交易由 mock/real 提供。
    # tqsdk 仅作为行情源，不会自动启用 FuturesTradingAdapter 实盘交易；
    # 实盘仍由 FUTURES_BROKER_TYPE=tqsdk 的 Broker 层负责。
    if quote_provider in _PROFESSIONAL_PROVIDERS:
        md_adapter = get_market_data_adapter(market, quote_provider, config)
        trading_adapter: TradingAdapter | None = None
        if mode == "mock":
            trading_adapter = MockTradingAdapter(market=market, config=config)
        elif market == Market.STOCK and mode == "real":
            from app.sdk.stock_adapter import StockTradingAdapter

            trading_adapter = StockTradingAdapter(config=config)
        elif market == Market.FUTURES and mode == "real" and quote_provider != "tqsdk":
            from app.sdk.futures_adapter import FuturesTradingAdapter

            trading_adapter = FuturesTradingAdapter(config=config)
        elif market == Market.FUTURES and mode == "real" and quote_provider == "tqsdk":
            # 行情走 TqSdk，交易侧仍用 mock 记账；真实下单走 Broker 层。
            trading_adapter = MockTradingAdapter(market=market, config=config)
        return MarketDataBackedAdapter(
            market=market,
            market_data_adapter=md_adapter,
            trading_adapter=trading_adapter,
        )

    if mode == "mock":
        return MockTradingAdapter(market=market, config=config)
    if market == Market.STOCK and mode == "real":
        from app.sdk.stock_adapter import StockTradingAdapter

        return StockTradingAdapter(config=config)
    if market == Market.FUTURES and mode == "real":
        from app.sdk.futures_adapter import FuturesTradingAdapter

        return FuturesTradingAdapter(config=config)
    raise ValueError(f"不支持的适配器: market={market} mode={mode} quote_provider={quote_provider}")
