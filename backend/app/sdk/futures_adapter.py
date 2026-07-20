from app.schemas.enums import Market
from app.sdk.ths_adapter_base import ThsTradingAdapterBase


class FuturesTradingAdapter(ThsTradingAdapterBase):
    """同花顺期货 SDK 适配器（开平/平今昨经 mapping.build_place_payload 表达）。"""

    def __init__(self, *, config: dict | None = None):
        super().__init__(market=Market.FUTURES, config=config)
