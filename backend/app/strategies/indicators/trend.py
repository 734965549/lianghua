from collections import deque
from decimal import Decimal

from app.sdk.models import KlineBar
from app.strategies.indicators.base import Indicator, _to_decimal
from app.strategies.indicators.volatility import ATRIndicator


def _wilder_smooth(prev: Decimal | None, current: Decimal, period: int) -> Decimal:
    if prev is None:
        return current
    return (prev * Decimal(period - 1) + current) / Decimal(period)


class ADXIndicator(Indicator):
    """平均趋向指数 ADX，含 +DI / -DI。"""

    output_names = ("value", "plus_di", "minus_di")

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._prev_high: Decimal | None = None
        self._prev_low: Decimal | None = None
        self._prev_close: Decimal | None = None
        self._tr_smooth: Decimal | None = None
        self._plus_dm_smooth: Decimal | None = None
        self._minus_dm_smooth: Decimal | None = None
        self._adx_smooth: Decimal | None = None
        self._bar_count = 0

    @property
    def warmup_bars(self) -> int:
        return self.period * 2

    def update(self, bar: KlineBar) -> None:
        high = _to_decimal(bar.high)
        low = _to_decimal(bar.low)
        close = _to_decimal(bar.close)

        if self._prev_high is None:
            self._prev_high = high
            self._prev_low = low
            self._prev_close = close
            self._set_outputs({"value": None, "plus_di": None, "minus_di": None})
            return

        up_move = high - self._prev_high
        down_move = self._prev_low - low
        plus_dm = up_move if up_move > down_move and up_move > 0 else Decimal("0")
        minus_dm = down_move if down_move > up_move and down_move > 0 else Decimal("0")

        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )

        self._prev_high = high
        self._prev_low = low
        self._prev_close = close
        self._bar_count += 1

        self._tr_smooth = _wilder_smooth(self._tr_smooth, tr, self.period)
        self._plus_dm_smooth = _wilder_smooth(self._plus_dm_smooth, plus_dm, self.period)
        self._minus_dm_smooth = _wilder_smooth(self._minus_dm_smooth, minus_dm, self.period)

        if self._bar_count < self.period or self._tr_smooth is None or self._tr_smooth == 0:
            self._set_outputs({"value": None, "plus_di": None, "minus_di": None})
            return

        plus_di = Decimal("100") * self._plus_dm_smooth / self._tr_smooth
        minus_di = Decimal("100") * self._minus_dm_smooth / self._tr_smooth
        di_sum = plus_di + minus_di
        if di_sum == 0:
            self._set_outputs({"value": None, "plus_di": plus_di, "minus_di": minus_di})
            return

        dx = Decimal("100") * abs(plus_di - minus_di) / di_sum
        self._adx_smooth = _wilder_smooth(self._adx_smooth, dx, self.period)

        if self._bar_count < self.period * 2 - 1:
            self._set_outputs({"value": None, "plus_di": plus_di, "minus_di": minus_di})
            return

        self._set_outputs({"value": self._adx_smooth, "plus_di": plus_di, "minus_di": minus_di})


class ParabolicSARIndicator(Indicator):
    """抛物线 SAR 止损反转指标。"""

    def __init__(
        self,
        *,
        period: int | None = None,
        source: str = "close",
        step: Decimal | str | float = Decimal("0.02"),
        max_step: Decimal | str | float = Decimal("0.2"),
    ):
        super().__init__(period=period, source=source)
        self.step = Decimal(str(step))
        self.max_step = Decimal(str(max_step))
        self._sar: Decimal | None = None
        self._ep: Decimal | None = None
        self._af = self.step
        self._trend = 1  # 1=上升, -1=下降
        self._prev_high: Decimal | None = None
        self._prev_low: Decimal | None = None
        self._initialized = False

    @property
    def warmup_bars(self) -> int:
        return 3

    def update(self, bar: KlineBar) -> None:
        high = _to_decimal(bar.high)
        low = _to_decimal(bar.low)

        if not self._initialized:
            self._sar = low
            self._ep = high
            self._trend = 1
            self._prev_high = high
            self._prev_low = low
            self._initialized = True
            self._set_value(None)
            return

        assert self._sar is not None and self._ep is not None

        if self._trend == 1:
            self._sar = self._sar + self._af * (self._ep - self._sar)
            self._sar = min(self._sar, self._prev_low or low, low)
            if low < self._sar:
                self._trend = -1
                self._sar = self._ep
                self._ep = low
                self._af = self.step
            else:
                if high > self._ep:
                    self._ep = high
                    self._af = min(self._af + self.step, self.max_step)
        else:
            self._sar = self._sar + self._af * (self._ep - self._sar)
            self._sar = max(self._sar, self._prev_high or high, high)
            if high > self._sar:
                self._trend = 1
                self._sar = self._ep
                self._ep = high
                self._af = self.step
            else:
                if low < self._ep:
                    self._ep = low
                    self._af = min(self._af + self.step, self.max_step)

        self._prev_high = high
        self._prev_low = low
        self._set_value(self._sar)


class SuperTrendIndicator(Indicator):
    """超级趋势指标（ATR 通道）。"""

    output_names = ("value", "direction")

    def __init__(
        self,
        *,
        period: int,
        source: str = "close",
        multiplier: Decimal | str | float = Decimal("3"),
    ):
        super().__init__(period=period, source=source)
        self.multiplier = Decimal(str(multiplier))
        self._atr = ATRIndicator(period=period, source=source)
        self._prev_close: Decimal | None = None
        self._final_upper: Decimal | None = None
        self._final_lower: Decimal | None = None
        self._direction = 1

    @property
    def warmup_bars(self) -> int:
        return self.period + 1

    def update(self, bar: KlineBar) -> None:
        high = _to_decimal(bar.high)
        low = _to_decimal(bar.low)
        close = _to_decimal(bar.close)
        self._atr.update(bar)

        if not self._atr.ready or self._atr.value is None:
            self._set_outputs({"value": None, "direction": None})
            return

        hl2 = (high + low) / Decimal("2")
        basic_upper = hl2 + self.multiplier * self._atr.value
        basic_lower = hl2 - self.multiplier * self._atr.value

        if self._final_upper is None or self._final_lower is None:
            self._final_upper = basic_upper
            self._final_lower = basic_lower
        else:
            if basic_upper < self._final_upper or (
                self._prev_close is not None and self._prev_close > self._final_upper
            ):
                self._final_upper = basic_upper
            if basic_lower > self._final_lower or (
                self._prev_close is not None and self._prev_close < self._final_lower
            ):
                self._final_lower = basic_lower

        if self._direction == 1:
            if close <= self._final_lower:
                self._direction = -1
        elif close >= self._final_upper:
            self._direction = 1

        st_value = self._final_lower if self._direction == 1 else self._final_upper
        self._prev_close = close
        self._set_outputs({"value": st_value, "direction": Decimal(self._direction)})


class IchimokuIndicator(Indicator):
    """一目均衡表（不含未来位移，便于规则引用）。"""

    output_names = ("tenkan", "kijun", "senkou_a", "senkou_b")

    def __init__(
        self,
        *,
        period: int | None = None,
        source: str = "close",
        tenkan: int = 9,
        kijun: int = 26,
        senkou_b: int = 52,
    ):
        super().__init__(period=period, source=source)
        self.tenkan_period = tenkan
        self.kijun_period = kijun
        self.senkou_b_period = senkou_b
        self._highs: deque[Decimal] = deque(maxlen=senkou_b)
        self._lows: deque[Decimal] = deque(maxlen=senkou_b)

    @property
    def warmup_bars(self) -> int:
        return self.senkou_b_period

    def _midpoint(self, highs: deque[Decimal], lows: deque[Decimal], n: int) -> Decimal | None:
        if len(highs) < n or len(lows) < n:
            return None
        h_slice = list(highs)[-n:]
        l_slice = list(lows)[-n:]
        return (max(h_slice) + min(l_slice)) / Decimal("2")

    def update(self, bar: KlineBar) -> None:
        self._highs.append(_to_decimal(bar.high))
        self._lows.append(_to_decimal(bar.low))

        tenkan = self._midpoint(self._highs, self._lows, self.tenkan_period)
        kijun = self._midpoint(self._highs, self._lows, self.kijun_period)
        senkou_b = self._midpoint(self._highs, self._lows, self.senkou_b_period)

        senkou_a = None
        if tenkan is not None and kijun is not None:
            senkou_a = (tenkan + kijun) / Decimal("2")

        self._set_outputs(
            {"tenkan": tenkan, "kijun": kijun, "senkou_a": senkou_a, "senkou_b": senkou_b}
        )
