from collections import deque
from decimal import Decimal

from app.sdk.models import KlineBar
from app.strategies.indicators.base import Indicator, _to_decimal


class ATRIndicator(Indicator):
    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._prev_close: Decimal | None = None
        self._trs: deque[Decimal] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        high = _to_decimal(bar.high)
        low = _to_decimal(bar.low)
        if self._prev_close is None:
            self._prev_close = self._bar_field(bar)
            self._set_value(None)
            return

        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )
        self._prev_close = self._bar_field(bar)
        self._trs.append(tr)
        if len(self._trs) < self.period:
            self._set_value(None)
            return
        self._set_value(sum(self._trs) / Decimal(self.period))


class BollingerIndicator(Indicator):
    output_names = ("value", "upper", "lower", "width", "pct_b")

    def __init__(
        self,
        *,
        period: int,
        source: str = "close",
        std_dev: Decimal | str | float = Decimal("2"),
    ):
        super().__init__(period=period, source=source)
        self.std_dev = Decimal(str(std_dev))
        self._window: deque[Decimal] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        price = self._bar_field(bar)
        self._window.append(price)
        if len(self._window) < self.period:
            self._set_outputs({"value": None, "upper": None, "lower": None})
            return

        values = list(self._window)
        middle = sum(values) / Decimal(self.period)
        variance = sum((v - middle) ** 2 for v in values) / Decimal(self.period)
        std = variance.sqrt() if variance > 0 else Decimal("0")
        upper = middle + self.std_dev * std
        lower = middle - self.std_dev * std
        width = upper - lower if upper > lower else Decimal("0")
        pct_b = (price - lower) / width if width > 0 else Decimal("0.5")
        self._set_outputs(
            {
                "value": middle,
                "upper": upper,
                "lower": lower,
                "width": width,
                "pct_b": pct_b,
            }
        )


class KeltnerIndicator(Indicator):
    """肯特纳通道（EMA + ATR）。"""

    output_names = ("value", "upper", "lower")

    def __init__(
        self,
        *,
        period: int,
        source: str = "close",
        multiplier: Decimal | str | float = Decimal("2"),
    ):
        super().__init__(period=period, source=source)
        self.multiplier = Decimal(str(multiplier))
        from app.strategies.indicators.moving_average import EMAIndicator

        self._ema = EMAIndicator(period=period, source=source)
        self._atr = ATRIndicator(period=period, source=source)

    @property
    def warmup_bars(self) -> int:
        return self.period + 1

    def update(self, bar: KlineBar) -> None:
        self._ema.update(bar)
        self._atr.update(bar)
        if not self._ema.ready or not self._atr.ready or self._atr.value is None:
            self._set_outputs({"value": None, "upper": None, "lower": None})
            return
        middle = self._ema.value
        band = self.multiplier * self._atr.value
        self._set_outputs(
            {"value": middle, "upper": middle + band, "lower": middle - band}
        )


class DonchianIndicator(Indicator):
    """唐奇安通道。"""

    output_names = ("value", "upper", "lower")

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._highs: deque[Decimal] = deque(maxlen=period)
        self._lows: deque[Decimal] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        self._highs.append(_to_decimal(bar.high))
        self._lows.append(_to_decimal(bar.low))
        if len(self._highs) < self.period:
            self._set_outputs({"value": None, "upper": None, "lower": None})
            return
        upper = max(self._highs)
        lower = min(self._lows)
        self._set_outputs({"value": (upper + lower) / Decimal("2"), "upper": upper, "lower": lower})
