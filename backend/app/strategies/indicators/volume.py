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


class OBVIndicator(Indicator):
    """能量潮 OBV。"""

    def __init__(self, *, period: int | None = None, source: str = "close"):
        super().__init__(period=period, source=source)
        self._prev_close: Decimal | None = None
        self._obv = Decimal("0")

    @property
    def warmup_bars(self) -> int:
        return 2

    def update(self, bar: KlineBar) -> None:
        close = _to_decimal(bar.close)
        vol = _to_decimal(bar.volume)
        if self._prev_close is None:
            self._prev_close = close
            self._set_value(None)
            return
        if close > self._prev_close:
            self._obv += vol
        elif close < self._prev_close:
            self._obv -= vol
        self._prev_close = close
        self._set_value(self._obv)


class VWAPIndicator(Indicator):
    """滚动 VWAP（成交量加权平均价）。"""

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._tp_vol: deque[tuple[Decimal, Decimal]] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        tp = (_to_decimal(bar.high) + _to_decimal(bar.low) + _to_decimal(bar.close)) / Decimal("3")
        vol = _to_decimal(bar.volume)
        self._tp_vol.append((tp * vol, vol))
        if len(self._tp_vol) < self.period:
            self._set_value(None)
            return
        total_vol = sum(v for _, v in self._tp_vol)
        if total_vol == 0:
            self._set_value(None)
            return
        self._set_value(sum(pv for pv, _ in self._tp_vol) / total_vol)


class CMFIndicator(Indicator):
    """柴金资金流 CMF。"""

    def __init__(self, *, period: int, source: str = "close"):
        super().__init__(period=period, source=source)
        self._mfv: deque[Decimal] = deque(maxlen=period)
        self._vol: deque[Decimal] = deque(maxlen=period)

    def update(self, bar: KlineBar) -> None:
        high = _to_decimal(bar.high)
        low = _to_decimal(bar.low)
        close = _to_decimal(bar.close)
        vol = _to_decimal(bar.volume)
        if high == low:
            mfm = Decimal("0")
        else:
            mfm = ((close - low) - (high - close)) / (high - low)
        self._mfv.append(mfm * vol)
        self._vol.append(vol)
        if len(self._mfv) < self.period:
            self._set_value(None)
            return
        total_vol = sum(self._vol)
        if total_vol == 0:
            self._set_value(Decimal("0"))
            return
        self._set_value(sum(self._mfv) / total_vol)


class ADLineIndicator(Indicator):
    """累积/派发线 A/D Line。"""

    def __init__(self, *, period: int | None = None, source: str = "close"):
        super().__init__(period=period, source=source)
        self._ad = Decimal("0")

    @property
    def warmup_bars(self) -> int:
        return 1

    def update(self, bar: KlineBar) -> None:
        high = _to_decimal(bar.high)
        low = _to_decimal(bar.low)
        close = _to_decimal(bar.close)
        vol = _to_decimal(bar.volume)
        if high == low:
            mfm = Decimal("0")
        else:
            mfm = ((close - low) - (high - close)) / (high - low)
        self._ad += mfm * vol
        self._set_value(self._ad)
