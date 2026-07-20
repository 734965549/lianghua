from collections import deque
from decimal import Decimal

from pydantic import Field

from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.sdk.models import KlineBar, QuoteSnapshot
from app.strategies.base import Strategy, StrategyParamSchema
from app.strategies.context import StrategyContext
from app.strategies.registry import register


class MaCrossParams(StrategyParamSchema):
    symbols: list[str] = Field(default_factory=lambda: ["600000.SH"])
    interval: str = "1m"
    fast: int = 5
    slow: int = 20
    quantity: Decimal = Decimal("100")


@register
class MaCrossStrategy(Strategy):
    strategy_id = "ma_cross"
    name = "双均线交叉"
    description = "快线上穿慢线买入，下穿卖出"
    param_schema = MaCrossParams
    supported_markets = ["stock", "futures"]

    def __init__(self, parameters: dict):
        super().__init__(parameters)
        self._closes: dict[str, deque] = {}

    def on_start(self, context: StrategyContext) -> None:
        self.context = context
        for symbol in self.parameters.symbols:
            self._closes[symbol] = deque(maxlen=self.parameters.slow + 1)
            bars = context.get_klines(symbol, self.parameters.interval, self.parameters.slow + 1)
            for bar in bars:
                self._closes[symbol].append(bar.close)
        context.log("info", f"ma_cross 启动，监控 {self.parameters.symbols}")

    def on_quote(self, quote: QuoteSnapshot) -> list:
        return []

    def on_bar(self, bar: KlineBar) -> list:
        if bar.symbol not in self._closes:
            return []
        closes = self._closes[bar.symbol]
        closes.append(bar.close)
        if len(closes) < self.parameters.slow:
            return []

        close_list = list(closes)
        fast_ma = sum(close_list[-self.parameters.fast :]) / self.parameters.fast
        slow_ma = sum(close_list[-self.parameters.slow :]) / self.parameters.slow

        if len(close_list) >= self.parameters.slow + 1:
            prev_fast = sum(close_list[-self.parameters.fast - 1 : -1]) / self.parameters.fast
            prev_slow = sum(close_list[-self.parameters.slow - 1 : -1]) / self.parameters.slow
            signals: list[str] = []
            if prev_fast <= prev_slow and fast_ma > slow_ma:
                sid = self.context.submit_signal(
                    symbol=bar.symbol,
                    market=bar.market,
                    side=OrderSide.BUY,
                    action=SignalAction.OPEN,
                    price_type=PriceType.LIMIT,
                    price=bar.close,
                    quantity=self.parameters.quantity,
                    reason=f"金叉 fast={fast_ma:.2f} slow={slow_ma:.2f}",
                )
                signals.append(sid)
            elif prev_fast >= prev_slow and fast_ma < slow_ma:
                sid = self.context.submit_signal(
                    symbol=bar.symbol,
                    market=bar.market,
                    side=OrderSide.SELL,
                    action=SignalAction.CLOSE,
                    price_type=PriceType.LIMIT,
                    price=bar.close,
                    quantity=self.parameters.quantity,
                    reason=f"死叉 fast={fast_ma:.2f} slow={slow_ma:.2f}",
                )
                signals.append(sid)
            return signals
        return []

    def on_stop(self) -> None:
        if self.context:
            self.context.log("info", "ma_cross 停止")
