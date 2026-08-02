from collections import deque
from decimal import Decimal

from pydantic import Field

from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.sdk.models import KlineBar, QuoteSnapshot
from app.strategies.base import Strategy, StrategyParamSchema
from app.strategies.context import StrategyContext
from app.strategies.registry import register


class MultiFactorParams(StrategyParamSchema):
    symbols: list[str] = Field(default_factory=lambda: ["600519.SH"])
    interval: str = "1m"
    ma_period: int = 20
    rsi_period: int = 14
    quantity: Decimal = Decimal("10")


@register
class MultiFactorStrategy(Strategy):
    strategy_id = "multi_factor"
    name = "多因子 RSIMa"
    description = "RSI 超卖且价格上穿均线买入，RSI 超买且价格下穿均线卖出"
    param_schema = MultiFactorParams
    supported_markets = ["stock", "futures"]

    def __init__(self, parameters: dict):
        super().__init__(parameters)
        self._closes: dict[str, deque] = {}

    def on_start(self, context: StrategyContext) -> None:
        self.context = context
        needed = max(self.parameters.ma_period, self.parameters.rsi_period) + 1
        for symbol in self.parameters.symbols:
            self._closes[symbol] = deque(maxlen=needed)
            bars = context.get_klines(symbol, self.parameters.interval, needed)
            for bar in bars:
                self._closes[symbol].append(bar.close)
        context.log("info", f"multi_factor 启动，监控 {self.parameters.symbols}")

    def on_quote(self, quote: QuoteSnapshot) -> list:
        return []

    def on_bar(self, bar: KlineBar) -> list:
        if bar.symbol not in self._closes:
            return []
        closes = self._closes[bar.symbol]
        closes.append(bar.close)
        if len(closes) < max(self.parameters.ma_period, self.parameters.rsi_period) + 1:
            return []

        close_list = list(closes)
        ma = sum(close_list[-self.parameters.ma_period :]) / self.parameters.ma_period
        rsi = self._rsi(close_list[-self.parameters.rsi_period :])
        prev_close = close_list[-2]
        prev_ma = sum(close_list[-self.parameters.ma_period - 1 : -1]) / self.parameters.ma_period

        signals: list[str] = []
        if rsi is not None and rsi < Decimal("30") and prev_close <= prev_ma and bar.close > ma:
            sid = self.context.submit_signal(
                symbol=bar.symbol,
                market=bar.market,
                side=OrderSide.BUY,
                action=SignalAction.OPEN,
                price_type=PriceType.LIMIT,
                price=bar.close,
                quantity=self.parameters.quantity,
                reason=f"RSI{rsi:.2f}超卖+上穿均线",
            )
            signals.append(sid)
        elif rsi is not None and rsi > Decimal("70") and prev_close >= prev_ma and bar.close < ma:
            sid = self.context.submit_signal(
                symbol=bar.symbol,
                market=bar.market,
                side=OrderSide.SELL,
                action=SignalAction.CLOSE,
                price_type=PriceType.LIMIT,
                price=bar.close,
                quantity=self.parameters.quantity,
                reason=f"RSI{rsi:.2f}超买+下穿均线",
            )
            signals.append(sid)
        return signals

    def _rsi(self, values: list[Decimal]) -> Decimal | None:
        if len(values) < 2:
            return None
        gains = []
        losses = []
        for i in range(1, len(values)):
            diff = values[i] - values[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(Decimal("0"))
            else:
                gains.append(Decimal("0"))
                losses.append(-diff)
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        if avg_loss == 0:
            return Decimal("100")
        rs = avg_gain / avg_loss
        return Decimal("100") - Decimal("100") / (Decimal("1") + rs)

    def on_stop(self) -> None:
        if self.context:
            self.context.log("info", "multi_factor 停止")
