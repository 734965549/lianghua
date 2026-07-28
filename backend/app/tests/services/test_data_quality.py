"""数据质量校验测试。"""

from decimal import Decimal

from app.db.models.kline_bar import KlineBar as KlineBarModel
from app.schemas.enums import Market
from app.workers.data_quality import check_symbol_klines, _is_valid_ohlc


def test_ohlc_validation():
    assert _is_valid_ohlc(Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"))
    assert not _is_valid_ohlc(Decimal("-1"), Decimal("12"), Decimal("9"), Decimal("11"))


def test_check_symbol_klines_empty(db):
    report = check_symbol_klines(db, market=Market.STOCK, symbol="999999.SH", interval="1d")
    assert report["count"] == 0
    assert report["health"] == "red"


def test_check_symbol_klines_valid(db):
    from datetime import datetime, timezone

    db.add(
        KlineBarModel(
            symbol="600000.SH",
            market=Market.STOCK,
            interval="1d",
            bar_time=datetime(2026, 7, 1, tzinfo=timezone.utc),
            open=10,
            high=11,
            low=9,
            close=10.5,
            volume=1000,
        )
    )
    db.flush()
    report = check_symbol_klines(db, market=Market.STOCK, symbol="600000.SH", interval="1d")
    assert report["count"] == 1
    assert report["health"] == "green"
