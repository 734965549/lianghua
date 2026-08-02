from collections import deque
from decimal import Decimal

from app.sdk.models import KlineBar
from app.strategies.indicators.base import Indicator, _to_decimal
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


class KDJIndicator(Indicator):
    """KDJ 随机指标（A 股常用 1/3 平滑算法）。"""

    output_names = ("k", "d", "j")

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._highs: deque[Decimal] = deque(maxlen=period)
        self._lows: deque[Decimal] = deque(maxlen=period)
        self._k = Decimal("50")
        self._d = Decimal("50")

    def update(self, bar: KlineBar) -> None:
        self._highs.append(_to_decimal(bar.high))
        self._lows.append(_to_decimal(bar.low))
        close = _to_decimal(bar.close)

        if len(self._highs) < self.period:
            self._set_outputs({"k": None, "d": None, "j": None})
            return

        highest = max(self._highs)
        lowest = min(self._lows)
        if highest == lowest:
            rsv = Decimal("50")
        else:
            rsv = (close - lowest) / (highest - lowest) * Decimal("100")

        k = (Decimal("2") / Decimal("3")) * self._k + (Decimal("1") / Decimal("3")) * rsv
        d = (Decimal("2") / Decimal("3")) * self._d + (Decimal("1") / Decimal("3")) * k
        j = Decimal("3") * k - Decimal("2") * d

        self._k = k
        self._d = d
        self._set_outputs({"k": k, "d": d, "j": j})


class CCIIndicator(Indicator):
    """商品通道指数 CCI。"""

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._typical: deque[Decimal] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        tp = (_to_decimal(bar.high) + _to_decimal(bar.low) + _to_decimal(bar.close)) / Decimal("3")
        self._typical.append(tp)
        if len(self._typical) < self.period:
            self._set_value(None)
            return
        mean = sum(self._typical) / Decimal(self.period)
        mean_dev = sum(abs(v - mean) for v in self._typical) / Decimal(self.period)
        if mean_dev == 0:
            self._set_value(Decimal("0"))
            return
        self._set_value((tp - mean) / (Decimal("0.015") * mean_dev))


class WilliamsRIndicator(Indicator):
    """威廉指标 %R。"""

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._highs: deque[Decimal] = deque(maxlen=period)
        self._lows: deque[Decimal] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        self._highs.append(_to_decimal(bar.high))
        self._lows.append(_to_decimal(bar.low))
        close = _to_decimal(bar.close)
        if len(self._highs) < self.period:
            self._set_value(None)
            return
        highest = max(self._highs)
        lowest = min(self._lows)
        if highest == lowest:
            self._set_value(Decimal("-50"))
            return
        wr = (highest - close) / (highest - lowest) * Decimal("-100")
        self._set_value(wr)


class MFIIndicator(Indicator):
    """资金流量指数 MFI。"""

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._prev_tp: Decimal | None = None
        self._pos_flow: deque[Decimal] = deque(maxlen=period)
        self._neg_flow: deque[Decimal] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        tp = (_to_decimal(bar.high) + _to_decimal(bar.low) + _to_decimal(bar.close)) / Decimal("3")
        raw_flow = tp * _to_decimal(bar.volume)
        if self._prev_tp is None:
            self._prev_tp = tp
            self._set_value(None)
            return

        if tp > self._prev_tp:
            self._pos_flow.append(raw_flow)
            self._neg_flow.append(Decimal("0"))
        elif tp < self._prev_tp:
            self._pos_flow.append(Decimal("0"))
            self._neg_flow.append(raw_flow)
        else:
            self._pos_flow.append(Decimal("0"))
            self._neg_flow.append(Decimal("0"))
        self._prev_tp = tp

        if len(self._pos_flow) < self.period:
            self._set_value(None)
            return

        pos = sum(self._pos_flow)
        neg = sum(self._neg_flow)
        if neg == 0:
            self._set_value(Decimal("100"))
            return
        mfr = pos / neg
        self._set_value(Decimal("100") - (Decimal("100") / (Decimal("1") + mfr)))


class StochRSIIndicator(Indicator):
    """随机 RSI。"""

    output_names = ("k", "d")

    def __init__(
        self,
        *,
        period: int,
        source: str = "close",
        stoch_period: int = 14,
        k_smooth: int = 3,
        d_smooth: int = 3,
    ):
        super().__init__(period=period, source=source)
        self.stoch_period = stoch_period
        self.k_smooth = k_smooth
        self.d_smooth = d_smooth
        self._rsi = RSIIndicator(period=period, source=source)
        self._rsi_window: deque[Decimal] = deque(maxlen=stoch_period)
        self._k_window: deque[Decimal] = deque(maxlen=k_smooth)
        self._d_window: deque[Decimal] = deque(maxlen=d_smooth)

    @property
    def warmup_bars(self) -> int:
        return self.period + self.stoch_period + self.k_smooth + self.d_smooth

    def update(self, bar: KlineBar) -> None:
        self._rsi.update(bar)
        if not self._rsi.ready or self._rsi.value is None:
            self._set_outputs({"k": None, "d": None})
            return

        self._rsi_window.append(self._rsi.value)
        if len(self._rsi_window) < self.stoch_period:
            self._set_outputs({"k": None, "d": None})
            return

        rsi_vals = list(self._rsi_window)
        lowest = min(rsi_vals)
        highest = max(rsi_vals)
        if highest == lowest:
            stoch = Decimal("50")
        else:
            stoch = (self._rsi.value - lowest) / (highest - lowest) * Decimal("100")

        self._k_window.append(stoch)
        if len(self._k_window) < self.k_smooth:
            self._set_outputs({"k": None, "d": None})
            return
        k = sum(self._k_window) / Decimal(self.k_smooth)
        self._d_window.append(k)
        if len(self._d_window) < self.d_smooth:
            self._set_outputs({"k": k, "d": None})
            return
        d = sum(self._d_window) / Decimal(self.d_smooth)
        self._set_outputs({"k": k, "d": d})


class AOIndicator(Indicator):
    """Awesome Oscillator 动量震荡。"""

    def __init__(
        self,
        *,
        period: int | None = None,
        source: str = "close",
        fast: int = 5,
        slow: int = 34,
    ):
        super().__init__(period=period, source=source)
        self.fast_period = fast
        self.slow_period = slow
        self._median_window_fast: deque[Decimal] = deque(maxlen=fast)
        self._median_window_slow: deque[Decimal] = deque(maxlen=slow)

    @property
    def warmup_bars(self) -> int:
        return self.slow_period + 1

    def update(self, bar: KlineBar) -> None:
        median = (_to_decimal(bar.high) + _to_decimal(bar.low)) / Decimal("2")
        self._median_window_fast.append(median)
        self._median_window_slow.append(median)

        if len(self._median_window_fast) < self.fast_period or len(self._median_window_slow) < self.slow_period:
            self._set_value(None)
            return

        fast_sma = sum(self._median_window_fast) / Decimal(self.fast_period)
        slow_sma = sum(self._median_window_slow) / Decimal(self.slow_period)
        self._set_value(fast_sma - slow_sma)
