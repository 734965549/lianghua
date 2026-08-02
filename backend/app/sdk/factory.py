from app.schemas.enums import Market
from app.sdk.base import TradingAdapter
from app.sdk.market_data.backed_adapter import MarketDataBackedAdapter
from app.sdk.market_data.factory import get_market_data_adapter
from app.sdk.mock_adapter import MockTradingAdapter


_PROFESSIONAL_PROVIDERS = {"ifind", "tdx", "tushare_pro", "rqdata", "wind"}


def get_adapter(market: str | Market, config: dict) -> TradingAdapter:
    """根据配置返回适配器。MVP 默认返回 Mock。"""
    if isinstance(market, str):
        market = Market(market)
    mode = config.get("mode", "mock")
    quote_provider = config.get("quote_provider", "mock")

    # 行情源 = akshare 时，用 AkshareAdapter（行情真 + 交易模拟）
    if quote_provider == "akshare":
        from app.sdk.akshare_adapter import AkshareAdapter

        return AkshareAdapter(market=market, config=config)

    # 专业行情数据源：行情由 MarketDataAdapter 提供，交易由 mock/real 提供
    if quote_provider in _PROFESSIONAL_PROVIDERS:
        md_adapter = get_market_data_adapter(market, quote_provider, config)
        trading_adapter: TradingAdapter | None = None
        if mode == "mock":
            trading_adapter = MockTradingAdapter(market=market, config=config)
        elif market == Market.STOCK and mode == "real":
            from app.sdk.stock_adapter import StockTradingAdapter

            trading_adapter = StockTradingAdapter(config=config)
        elif market == Market.FUTURES and mode == "real":
            from app.sdk.futures_adapter import FuturesTradingAdapter

            trading_adapter = FuturesTradingAdapter(config=config)
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
