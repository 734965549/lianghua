from dataclasses import dataclass
from decimal import Decimal

from app.backtest.data_source import MarketEvent
from app.schemas.enums import FillModel as FillModelEnum
from app.schemas.enums import OrderSide, PriceType


@dataclass
class FillPrice:
    price: Decimal
    slippage: Decimal = Decimal("0")


class FillModelEngine:
    """撮合价格模型。"""

    def __init__(self, fill_model: FillModelEnum, slippage: Decimal = Decimal("0")):
        self.model = fill_model
        self.slippage = slippage

    def can_fill(self, order, event: MarketEvent) -> FillPrice | None:
        """判断订单是否能在当前事件成交，返回成交价（含滑点）或 None。"""
        if event.bar is not None:
            return self._fill_against_bar(order, event)
        if event.quote is not None:
            return self._fill_against_quote(order, event)
        return None

    def _fill_against_bar(self, order, event: MarketEvent) -> FillPrice | None:
        bar = event.bar
        if bar is None:
            return None

        if self.model == FillModelEnum.NEXT_OPEN:
            price = bar.open
        elif self.model == FillModelEnum.NEXT_CLOSE:
            price = bar.close
        elif self.model == FillModelEnum.VWAP:
            price = (bar.open + bar.high + bar.low + bar.close) / Decimal("4")
        elif self.model == FillModelEnum.TICK_PRICE:
            # K 线模式下 tick_price 退化为 close
            price = bar.close
        else:
            price = bar.close

        if order.price_type == PriceType.MARKET:
            return FillPrice(price=self._apply_slippage(price, order.side), slippage=self.slippage)

        if order.price_type == PriceType.LIMIT and order.price is not None:
            limit = Decimal(str(order.price))
            if order.side == OrderSide.BUY and price <= limit:
                return FillPrice(price=min(price, limit), slippage=Decimal("0"))
            if order.side == OrderSide.SELL and price >= limit:
                return FillPrice(price=max(price, limit), slippage=Decimal("0"))
        return None

    def _fill_against_quote(self, order, event: MarketEvent) -> FillPrice | None:
        quote = event.quote
        if quote is None:
            return None
        price = quote.last_price

        if order.price_type == PriceType.MARKET:
            return FillPrice(price=self._apply_slippage(price, order.side), slippage=self.slippage)

        if order.price_type == PriceType.LIMIT and order.price is not None:
            limit = Decimal(str(order.price))
            if order.side == OrderSide.BUY and price <= limit:
                return FillPrice(price=min(price, limit), slippage=Decimal("0"))
            if order.side == OrderSide.SELL and price >= limit:
                return FillPrice(price=max(price, limit), slippage=Decimal("0"))
        return None

    def _apply_slippage(self, price: Decimal, side: str) -> Decimal:
        if side == OrderSide.BUY.value:
            return price * (Decimal("1") + self.slippage)
        return price * (Decimal("1") - self.slippage)
