from datetime import datetime, timezone
from decimal import Decimal

from app.backtest.data_source import KlineDataSource
from app.db.models.kline_bar import KlineBar as KlineBarModel
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.sdk.models import KlineBar
from app.workers.data_quality import data_overview, integrity_report


def _bar(bar_time: datetime, *, close: str = "10.5", provider: str = "feed_a"):
    return KlineBar(
        symbol="600000.SH",
        market=Market.STOCK,
        interval="1d",
        bar_time=bar_time,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal(close),
        volume=Decimal("1000"),
        raw_payload={"provider": provider},
    )


def _legacy_row(bar_time: datetime, *, close: str = "10.5"):
    return KlineBarModel(
        symbol="600000.SH",
        market=Market.STOCK,
        interval="1d",
        bar_time=bar_time,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal(close),
        volume=Decimal("1000"),
        raw_payload={"source": "legacy"},
    )


def test_upsert_normalizes_and_deduplicates_daily_bars(db):
    repo = MarketRepository(db)
    outcome = repo.upsert_klines(
        [
            _bar(datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc)),
            _bar(
                datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc),
                close="10.8",
                provider="feed_b",
            ),
        ]
    )
    db.commit()

    rows = db.query(KlineBarModel).all()
    assert outcome["accepted"] == 1
    assert outcome["deduplicated"] == 1
    assert len(rows) == 1
    assert Decimal(str(rows[0].close)) == Decimal("10.8")
    assert rows[0].raw_payload["source"] == "feed_b"


def test_upsert_quarantines_weekend_daily_bar(db):
    outcome = MarketRepository(db).upsert_klines(
        [_bar(datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc))]
    )

    assert outcome["accepted"] == 0
    assert outcome["quarantined"] == 1
    assert outcome["quarantine_reasons"][0]["reasons"] == ["non_trading_day"]
    assert db.query(KlineBarModel).count() == 0


def test_legacy_dirty_bars_are_excluded_from_backtest_and_counted(db):
    db.add_all(
        [
            _legacy_row(datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)),
            _legacy_row(datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc)),
            _legacy_row(
                datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc), close="10.6"
            ),
        ]
    )
    db.commit()

    repo = MarketRepository(db)
    trusted = repo.query_klines(
        market=Market.STOCK,
        symbol="600000.SH",
        interval="1d",
        limit=10,
    )
    raw = repo.query_klines(
        market=Market.STOCK,
        symbol="600000.SH",
        interval="1d",
        limit=10,
        trusted_only=False,
    )
    events = list(
        KlineDataSource(db).load_events(
            ["600000.SH"],
            datetime(2026, 7, 1, tzinfo=timezone.utc),
            datetime(2026, 7, 31, tzinfo=timezone.utc),
            "1d",
        )
    )
    overview = data_overview(db)
    integrity = integrity_report(db)

    assert len(raw) == 3
    assert len(trusted) == 1
    assert len(events) == 1
    assert overview["kline_total"] == 3
    assert overview["kline_trusted"] == 1
    assert overview["kline_quarantined"] == 1
    assert overview["kline_duplicates"] == 1
    assert integrity["items"][0]["raw_count"] == 3
    assert integrity["items"][0]["count"] == 1
