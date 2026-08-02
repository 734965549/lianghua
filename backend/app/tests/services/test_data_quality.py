"""数据质量校验测试。"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.api.response import BizError
from app.backtest.models import BacktestCreateRequest
from app.db.models.kline_bar import KlineBar as KlineBarModel
from app.repositories.market_repo import MarketRepository
from app.schemas.error_codes import ErrorCode
from app.services.market_service import MarketService, quote_validation_error
from app.schemas.enums import Market
from app.sdk.models import QuoteSnapshot
from app.services.backtest_service import BacktestService
from app.workers.data_quality import (
    _is_valid_ohlc,
    check_symbol_klines,
    evaluate_data_quality_gate,
)


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


def _daily_bar(symbol: str, when: datetime, *, raw_payload: dict | None = None):
    return KlineBarModel(
        symbol=symbol,
        market=Market.STOCK,
        interval="1d",
        bar_time=when,
        open=10,
        high=11,
        low=9,
        close=10.5,
        volume=1000,
        raw_payload=raw_payload,
    )


def test_data_quality_gate_rejects_missing_daily_bar(db):
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = datetime(2026, 7, 3, tzinfo=timezone.utc)
    db.add_all([_daily_bar("600000.SH", start), _daily_bar("600000.SH", end)])
    db.flush()

    gate = evaluate_data_quality_gate(
        db,
        targets=[(Market.STOCK, "600000.SH")],
        interval="1d",
        start=start,
        end=end,
    )

    assert gate["ready"] is False
    assert "missing_daily_bars" in gate["blockers"][0]["reasons"]


def test_data_quality_gate_rejects_quarantine_and_duplicate_period(db):
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    db.add_all(
        [
            _daily_bar("600000.SH", start),
            _daily_bar("600000.SH", start + timedelta(hours=1)),
            _daily_bar(
                "600000.SH",
                start + timedelta(days=1),
                raw_payload={
                    "quality_status": "quarantined",
                    "quality_reasons": ["price_invalid"],
                },
            ),
        ]
    )
    db.flush()

    gate = evaluate_data_quality_gate(
        db,
        targets=[(Market.STOCK, "600000.SH")],
        interval="1d",
    )

    reasons = set(gate["blockers"][0]["reasons"])
    assert {"quarantined_records", "duplicate_trading_periods"} <= reasons


def test_formal_backtest_refuses_missing_data(db):
    request = BacktestCreateRequest(
        strategy_id="ma_cross",
        symbols=["600000.SH"],
        start_time=datetime(2026, 7, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 7, 3, tzinfo=timezone.utc),
        interval="1d",
    )

    with pytest.raises(BizError) as exc_info:
        BacktestService().run_backtest(db, request)

    assert exc_info.value.code == ErrorCode.DATA_QUALITY_NOT_READY
    assert "无可用数据" in exc_info.value.message


def test_suspended_requires_zero_volume_and_unchanged_price(db):
    from datetime import datetime, timezone

    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i, (close, volume) in enumerate([(10, 1000), (10, 0), (10, 0), (10, 0)]):
        db.add(
            KlineBarModel(
                symbol="600000.SH",
                market=Market.STOCK,
                interval="1d",
                bar_time=base.replace(day=base.day + i),
                open=10,
                high=10,
                low=10,
                close=close,
                volume=volume,
            )
        )
    db.flush()
    report = check_symbol_klines(db, market=Market.STOCK, symbol="600000.SH", interval="1d")
    assert any(i["type"] == "suspended" for i in report["issues"])


def test_zero_volume_with_price_change_not_suspended(db):
    from datetime import datetime, timezone

    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i, close in enumerate([10, 11, 12]):
        db.add(
            KlineBarModel(
                symbol="600000.SH",
                market=Market.STOCK,
                interval="1d",
                bar_time=base.replace(day=base.day + i),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=0,
            )
        )
    db.flush()
    report = check_symbol_klines(db, market=Market.STOCK, symbol="600000.SH", interval="1d")
    assert not any(i["type"] == "suspended" for i in report["issues"])


def test_quote_change_rate_uses_ratio_and_quarantines_percent_points():
    valid = QuoteSnapshot(
        symbol="000001.SZ",
        market=Market.STOCK,
        last_price=Decimal("11.47"),
        change_rate=Decimal("0.1007"),
        volume=Decimal("1000"),
        quote_time=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    abnormal = valid.model_copy(update={"change_rate": Decimal("10.07")})
    double_scaled = valid.model_copy(update={"change_rate": Decimal("0.172")})

    assert quote_validation_error(valid) is None
    assert "超出" in (quote_validation_error(abnormal) or "")
    assert "超出" in (quote_validation_error(double_scaled) or "")


def test_quote_without_timezone_is_quarantined():
    quote = QuoteSnapshot(
        symbol="600519.SH",
        market=Market.STOCK,
        last_price=Decimal("1400"),
        change_rate=Decimal("-0.0082"),
        volume=Decimal("1000"),
        quote_time=datetime(2026, 7, 31, 10, 30),
    )

    assert quote_validation_error(quote) == "行情时间缺少时区"


def test_abnormal_quote_is_not_persisted_or_dispatched(monkeypatch):
    calls = {"event": 0, "insert": 0, "broadcast": []}

    class FakeDb:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    class FakeEventRepository:
        def __init__(self, db):
            self.db = db

        def add(self, **kwargs):
            calls["event"] += 1
            calls["event_code"] = kwargs["event_code"]

    class FakeMarketRepository:
        def __init__(self, db):
            self.db = db

        def insert_snapshot(self, quote):
            calls["insert"] += 1

    monkeypatch.setattr("app.services.market_service.SessionLocal", FakeDb)
    monkeypatch.setattr(
        "app.services.market_service.SystemEventRepository", FakeEventRepository
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketRepository", FakeMarketRepository
    )
    monkeypatch.setattr(
        "app.services.market_service.broadcast_sync",
        lambda topic, payload: calls["broadcast"].append(topic),
    )
    quote = QuoteSnapshot(
        symbol="000001.SZ",
        market=Market.STOCK,
        last_price=Decimal("11.47"),
        change_rate=Decimal("10.07"),
        volume=Decimal("1000"),
        quote_time=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    MarketService()._handle_quote(quote)

    assert calls["event"] == 1
    assert calls["event_code"] == "QUOTE_QUARANTINED"
    assert calls["insert"] == 0
    assert calls["broadcast"] == ["quote.quarantined"]


def test_repository_does_not_return_legacy_abnormal_quote(db):
    quote = QuoteSnapshot(
        symbol="000001.SZ",
        market=Market.STOCK,
        last_price=Decimal("11.47"),
        change_rate=Decimal("0.172"),
        volume=Decimal("1000"),
        quote_time=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    repo = MarketRepository(db)
    repo.insert_snapshot(quote)
    db.flush()

    assert repo.get_latest_quote(Market.STOCK, "000001.SZ") is None
