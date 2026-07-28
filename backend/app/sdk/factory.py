from app.schemas.enums import Market
from app.sdk.base import TradingAdapter
from app.sdk.mock_adapter import MockTradingAdapter


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
    
    if mode == "mock":
        return MockTradingAdapter(market=market, config=config)
    if market == Market.STOCK and mode == "real":
        from app.sdk.stock_adapter import StockTradingAdapter

        return StockTradingAdapter(config=config)
    if market == Market.FUTURES and mode == "real":
        from app.sdk.futures_adapter import FuturesTradingAdapter

        return FuturesTradingAdapter(config=config)
    raise ValueError(f"不支持的适配器: market={market} mode={mode}")
