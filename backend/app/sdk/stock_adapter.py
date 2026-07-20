from app.schemas.enums import Market
from app.sdk.ths_adapter_base import ThsTradingAdapterBase


class StockTradingAdapter(ThsTradingAdapterBase):
    """同花顺股票 SDK 适配器。"""

    def __init__(self, *, config: dict | None = None):
        super().__init__(market=Market.STOCK, config=config)
