import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db.models.market_snapshot import MarketSnapshot
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market


QUOTE_TIME = datetime(2026, 7, 31, 6, 30, tzinfo=timezone.utc)
CREATED_AT = datetime(2026, 7, 31, 6, 30, 1, tzinfo=timezone.utc)


def _snapshot(
    row_id: int,
    *,
    last_price: str,
    quote_time: datetime = QUOTE_TIME,
    created_at: datetime = CREATED_AT,
) -> MarketSnapshot:
    return MarketSnapshot(
        id=uuid.UUID(int=row_id),
        symbol="LATEST.TEST",
        market=Market.STOCK,
        quote_time=quote_time,
        created_at=created_at,
        last_price=Decimal(last_price),
        change_rate=Decimal("0.01"),
        volume=Decimal("100"),
    )


def test_list_latest_quotes_returns_one_deterministic_row_per_instrument(db):
    db.add_all(
        [
            _snapshot(
                10,
                last_price="10.00",
                quote_time=QUOTE_TIME - timedelta(seconds=1),
                created_at=CREATED_AT + timedelta(seconds=10),
            ),
            _snapshot(
                40,
                last_price="40.00",
                created_at=CREATED_AT - timedelta(seconds=1),
            ),
        ]
    )
    db.commit()

    rows = MarketRepository(db).list_latest_quotes(market=Market.STOCK)
    matches = [row for row in rows if row.symbol == "LATEST.TEST"]

    assert len(matches) == 1
    assert matches[0].id == uuid.UUID(int=40)
    assert Decimal(str(matches[0].last_price)) == Decimal("40.00")


def test_get_latest_quote_prefers_quote_time_over_created_at(db):
    db.add_all(
        [
            _snapshot(
                50,
                last_price="50.00",
                quote_time=QUOTE_TIME - timedelta(seconds=1),
                created_at=CREATED_AT + timedelta(seconds=10),
            ),
            _snapshot(60, last_price="60.00"),
        ]
    )
    db.commit()

    row = MarketRepository(db).get_latest_quote(Market.STOCK, "LATEST.TEST")

    assert row is not None
    assert row.id == uuid.UUID(int=60)
