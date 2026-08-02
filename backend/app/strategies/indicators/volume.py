from collections import deque
from decimal import Decimal

from app.sdk.models import KlineBar
from app.strategies.indicators.base import Indicator, _to_decimal


class VolumeSMAIndicator(Indicator):
    def __init__(self, *, period: int, source: str = "volume"):
        super().__init__(period=period, source=source)
        self._window: deque[Decimal] = deque(maxlen=period)
        self._sum = Decimal("0")

    def update(self, bar: KlineBar) -> None:
        vol = _to_decimal(bar.volume)
        if len(self._window) == self.period:
            self._sum -= self._window[0]
        self._window.append(vol)
        self._sum += vol
        if len(self._window) < self.period:
            self._set_value(None)
            return
        self._set_value(self._sum / Decimal(self.period))
