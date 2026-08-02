from collections import deque
from decimal import Decimal

from app.sdk.models import KlineBar
from app.strategies.indicators.base import Indicator


class SMAIndicator(Indicator):
    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._window: deque[Decimal] = deque(maxlen=period)
        self._sum = Decimal("0")

    def update(self, bar: KlineBar) -> None:
        price = self._bar_field(bar)
        if len(self._window) == self.period:
            self._sum -= self._window[0]
        self._window.append(price)
        self._sum += price
        if len(self._window) < self.period:
            self._set_value(None)
            return
        self._set_value(self._sum / Decimal(self.period))


class WMAIndicator(Indicator):
    """加权移动平均。"""

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._window: deque[Decimal] = deque(maxlen=period)
        self._weight_sum = Decimal(str(period * (period + 1) // 2))

    def update(self, bar: KlineBar) -> None:
        price = self._bar_field(bar)
        self._window.append(price)
        if len(self._window) < self.period:
            self._set_value(None)
            return
        weighted = sum(
            price * Decimal(i + 1) for i, price in enumerate(self._window)
        )
        self._set_value(weighted / self._weight_sum)


class HMAIndicator(Indicator):
    """Hull 移动平均。"""

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        half = max(period // 2, 1)
        sqrt_p = max(int(period**0.5), 1)
        self._wma_half = WMAIndicator(period=half, source=source)
        self._wma_full = WMAIndicator(period=period, source=source)
        self._raw_window: deque[Decimal] = deque(maxlen=sqrt_p)
        self._sqrt_period = sqrt_p

    @property
    def warmup_bars(self) -> int:
        return self.period + self._sqrt_period

    def update(self, bar: KlineBar) -> None:
        self._wma_half.update(bar)
        self._wma_full.update(bar)
        if not self._wma_half.ready or not self._wma_full.ready:
            self._set_value(None)
            return
        raw = Decimal("2") * self._wma_half.value - self._wma_full.value
        self._raw_window.append(raw)
        if len(self._raw_window) < self._sqrt_period:
            self._set_value(None)
            return
        weight_sum = Decimal(str(self._sqrt_period * (self._sqrt_period + 1) // 2))
        weighted = sum(v * Decimal(i + 1) for i, v in enumerate(self._raw_window))
        self._set_value(weighted / weight_sum)


class EMAIndicator(Indicator):
    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._alpha = Decimal("2") / Decimal(period + 1)
        self._count = 0
        self._ema: Decimal | None = None

    def update(self, bar: KlineBar) -> None:
        price = self._bar_field(bar)
        self._count += 1
        if self._ema is None:
            self._ema = price
            if self._count < self.period:
                self._set_value(None)
                return
            self._set_value(self._ema)
            return
        self._ema = self._alpha * price + (Decimal("1") - self._alpha) * self._ema
        if self._count < self.period:
            self._set_value(None)
            return
        self._set_value(self._ema)
