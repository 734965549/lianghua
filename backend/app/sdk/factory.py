from app.schemas.enums import Market
from app.sdk.base import TradingAdapter
from app.sdk.mock_adapter import MockTradingAdapter


def get_adapter(market: str | Market, config: dict) -> TradingAdapter:
    """根据配置返回适配器。MVP 默认返回 Mock。"""
    if isinstance(market, str):
        market = Market(market)
    mode = config.get("mode", "mock")
    if mode == "mock":
        return MockTradingAdapter(market=market, config=config)
    if market == Market.STOCK and mode == "real":
        from app.sdk.stock_adapter import StockTradingAdapter

        return StockTradingAdapter(config=config)
    if market == Market.FUTURES and mode == "real":
        from app.sdk.futures_adapter import FuturesTradingAdapter

        return FuturesTradingAdapter(config=config)
    raise ValueError(f"不支持的适配器: market={market} mode={mode}")
