from collections import deque
from decimal import Decimal

from app.sdk.models import KlineBar
from app.strategies.indicators.base import Indicator
from app.strategies.indicators.moving_average import EMAIndicator


class RSIIndicator(Indicator):
    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._prev_close: Decimal | None = None
        self._gains: deque[Decimal] = deque(maxlen=period)
        self._losses: deque[Decimal] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        close = self._bar_field(bar)
        if self._prev_close is None:
            self._prev_close = close
            self._set_value(None)
            return

        change = close - self._prev_close
        self._prev_close = close
        gain = change if change > 0 else Decimal("0")
        loss = -change if change < 0 else Decimal("0")
        self._gains.append(gain)
        self._losses.append(loss)

        if len(self._gains) < self.period:
            self._set_value(None)
            return

        avg_gain = sum(self._gains) / Decimal(self.period)
        avg_loss = sum(self._losses) / Decimal(self.period)
        if avg_loss == 0:
            self._set_value(Decimal("100"))
            return
        rs = avg_gain / avg_loss
        rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
        self._set_value(rsi)


class MACDIndicator(Indicator):
    output_names = ("value", "signal", "histogram")

    def __init__(
        self,
        *,
        period: int | None = None,
        source: str = "close",
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ):
        super().__init__(period=period, source=source)
        self.fast_period = fast
        self.slow_period = slow
        self.signal_period = signal
        self._fast_ema = EMAIndicator(period=fast, source=source)
        self._slow_ema = EMAIndicator(period=slow, source=source)
        self._signal_ema: Decimal | None = None
        self._signal_alpha = Decimal("2") / Decimal(signal + 1)
        self._signal_count = 0
        self._prev_macd: Decimal | None = None
        self._prev_signal: Decimal | None = None

    @property
    def warmup_bars(self) -> int:
        return self.slow_period + self.signal_period

    def update(self, bar: KlineBar) -> None:
        self._fast_ema.update(bar)
        self._slow_ema.update(bar)
        if not self._fast_ema.ready or not self._slow_ema.ready:
            self._set_outputs({"value": None, "signal": None, "histogram": None})
            return

        macd = self._fast_ema.value - self._slow_ema.value
        self._signal_count += 1
        if self._signal_ema is None:
            self._signal_ema = macd
        else:
            self._signal_ema = self._signal_alpha * macd + (Decimal("1") - self._signal_alpha) * self._signal_ema

        if self._signal_count < self.signal_period:
            self._set_outputs({"value": None, "signal": None, "histogram": None})
            return

        signal = self._signal_ema
        histogram = macd - signal
        self._set_outputs({"value": macd, "signal": signal, "histogram": histogram})
        self._prev_macd = macd
        self._prev_signal = signal

    def get_prev_output(self, name: str = "value") -> Decimal | None:
        if name == "value":
            return self._prev_macd
        if name == "signal":
            return self._prev_signal
        if name == "histogram" and self._prev_macd is not None and self._prev_signal is not None:
            return self._prev_macd - self._prev_signal
        return super().get_prev_output(name)


class ROCIndicator(Indicator):
    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._window: deque[Decimal] = deque(maxlen=period + 1)

    def update(self, bar: KlineBar) -> None:
        price = self._bar_field(bar)
        self._window.append(price)
        if len(self._window) <= self.period:
            self._set_value(None)
            return
        old = self._window[0]
        if old == 0:
            self._set_value(None)
            return
        roc = (price - old) / old * Decimal("100")
        self._set_value(roc)
