import time

import pytest
from sqlalchemy.orm import Session

from app.db.models.market_snapshot import MarketSnapshot
from app.schemas.enums import Market
from app.sdk.mock_adapter import MockTradingAdapter
from app.services.market_service import MarketService


@pytest.mark.integration
def test_subscribe_persists_snapshots(db: Session):
    svc = MarketService()
    adapter = MockTradingAdapter(market=Market.STOCK)
    adapter.connect()

    def on_quote(quote):
        from app.repositories.market_repo import MarketRepository

        repo = MarketRepository(db)
        repo.insert_snapshot(quote)
        db.commit()

    adapter.on_quote_update(on_quote)
    adapter.subscribe_quotes(["600000.SH"])
    time.sleep(1.5)
    adapter.stop_quotes()
    adapter.disconnect()

    count = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.market == Market.STOCK, MarketSnapshot.symbol == "600000.SH")
        .count()
    )
    assert count >= 1
