"""指标引擎单元测试。"""

from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.enums import Market
from app.sdk.models import KlineBar
from app.strategies.indicators.moving_average import EMAIndicator, SMAIndicator
from app.strategies.indicators.momentum import RSIIndicator


def _bar(close: str, idx: int = 0) -> KlineBar:
    return KlineBar(
        symbol="600000.SH",
        market=Market.STOCK,
        interval="1d",
        bar_time=datetime(2023, 1, idx + 1, tzinfo=timezone.utc),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("1000"),
    )


def test_sma_golden():
    ind = SMAIndicator(period=3, source="close")
    for i, c in enumerate(["10", "20", "30"]):
        ind.update(_bar(c, i))
    assert ind.ready
    assert ind.value == Decimal("20")


def test_ema_incremental():
    ind = EMAIndicator(period=3, source="close")
    closes = ["10", "11", "12", "13", "14"]
    for i, c in enumerate(closes):
        ind.update(_bar(c, i))
    assert ind.ready
    assert ind.prev_value is not None
    assert ind.value > ind.prev_value


def test_rsi_bounds():
    ind = RSIIndicator(period=3, source="close")
    closes = ["10", "12", "14", "16", "18", "20"]
    for i, c in enumerate(closes):
        ind.update(_bar(c, i))
    assert ind.ready
    assert Decimal("0") <= ind.value <= Decimal("100")
