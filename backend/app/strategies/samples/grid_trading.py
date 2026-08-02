from collections import deque
from decimal import Decimal

from pydantic import Field

from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.sdk.models import KlineBar, QuoteSnapshot
from app.strategies.base import Strategy, StrategyParamSchema
from app.strategies.context import StrategyContext
from app.strategies.registry import register


class GridTradingParams(StrategyParamSchema):
    symbols: list[str] = Field(default_factory=lambda: ["600519.SH"])
    interval: str = "1m"
    grid_size: Decimal = Decimal("0.5")
    quantity: Decimal = Decimal("10")


@register
class GridTradingStrategy(Strategy):
    strategy_id = "grid_trading"
    name = "网格交易"
    version = "1.0.0"
    description = "按固定价格网格低买高卖"
    param_schema = GridTradingParams
    supported_markets = ["stock", "futures"]

    def __init__(self, parameters: dict):
        super().__init__(parameters)
        self._last_grid_index: dict[str, int] = {}

    def on_start(self, context: StrategyContext) -> None:
        self.context = context
        for symbol in self.parameters.symbols:
            bars = context.get_klines(symbol, self.parameters.interval, 1)
            if bars:
                base = bars[-1].close
                idx = int(base / self.parameters.grid_size)
                self._last_grid_index[symbol] = idx
        context.log("info", f"grid_trading 启动，监控 {self.parameters.symbols}")

    def on_quote(self, quote: QuoteSnapshot) -> list:
        return []

    def on_bar(self, bar: KlineBar) -> list:
        if bar.symbol not in self._last_grid_index:
            self._last_grid_index[bar.symbol] = int(bar.close / self.parameters.grid_size)
            return []

        current_index = int(bar.close / self.parameters.grid_size)
        last_index = self._last_grid_index[bar.symbol]
        signals: list[str] = []

        if current_index <= last_index - 1:
            sid = self.context.submit_signal(
                symbol=bar.symbol,
                market=bar.market,
                side=OrderSide.BUY,
                action=SignalAction.OPEN,
                price_type=PriceType.LIMIT,
                price=bar.close,
                quantity=self.parameters.quantity,
                reason=f"网格下穿 {last_index} -> {current_index}",
            )
            signals.append(sid)
            self._last_grid_index[bar.symbol] = current_index
        elif current_index >= last_index + 1:
            sid = self.context.submit_signal(
                symbol=bar.symbol,
                market=bar.market,
                side=OrderSide.SELL,
                action=SignalAction.CLOSE,
                price_type=PriceType.LIMIT,
                price=bar.close,
                quantity=self.parameters.quantity,
                reason=f"网格上穿 {last_index} -> {current_index}",
            )
            signals.append(sid)
            self._last_grid_index[bar.symbol] = current_index

        return signals

    def on_stop(self) -> None:
        if self.context:
            self.context.log("info", "grid_trading 停止")
