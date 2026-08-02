from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.market_snapshot import MarketSnapshot
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.sdk.models import QuoteSnapshot


def _quote(last_price: str, raw_sequence: int) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol="600000.SH",
        market=Market.STOCK,
        quote_time=datetime(2026, 7, 31, 1, 30, tzinfo=timezone.utc),
        last_price=Decimal(last_price),
        change_rate=Decimal("1.25"),
        volume=Decimal("123456"),
        bid_price=Decimal("10.10"),
        ask_price=Decimal("10.12"),
        bid_volume=Decimal("100"),
        ask_volume=Decimal("200"),
        raw_payload={"sequence": raw_sequence},
    )


def test_insert_snapshot_upserts_duplicate_identity(db: Session) -> None:
    repo = MarketRepository(db)

    first = repo.insert_snapshot(_quote("10.11", 1))
    db.commit()
    first_id = first.id

    second = repo.insert_snapshot(_quote("10.21", 2))
    db.commit()

    rows = (
        db.query(MarketSnapshot)
        .filter(
            MarketSnapshot.market == Market.STOCK,
            MarketSnapshot.symbol == "600000.SH",
            MarketSnapshot.quote_time
            == datetime(2026, 7, 31, 1, 30, tzinfo=timezone.utc),
        )
        .all()
    )

    assert len(rows) == 1
    assert second.id == first_id
    assert rows[0].id == first_id
    assert Decimal(rows[0].last_price) == Decimal("10.21")
    assert rows[0].raw_payload == {"sequence": 2}
