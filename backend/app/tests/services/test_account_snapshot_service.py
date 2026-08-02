from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.models.position import Position
from app.repositories.account_repo import AccountRepository
from app.repositories.asset_repo import AssetRepository
from app.repositories.position_repo import PositionRepository
from app.schemas.enums import Market
from app.sdk.models import AccountSnapshot, PositionSnapshot
from app.services.account_snapshot_service import AccountSnapshotService
from app.workers.sync_jobs import sync_positions


def test_empty_account_snapshot_is_not_reconciled(db):
    snapshot = AccountSnapshotService(db).get_snapshot()

    assert snapshot["has_account_snapshot"] is False
    assert snapshot["reconciled"] is False


def test_account_snapshot_uses_one_reconciled_component_set(db):
    now = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)
    accounts = AccountRepository(db)
    assets = AssetRepository(db)
    positions = PositionRepository(db)
    stock = accounts.get_or_create_default(Market.STOCK)
    futures = accounts.get_or_create_default(Market.FUTURES)

    assets.insert_snapshot(
        stock.id,
        AccountSnapshot(
            account_id=uuid4(),
            account_no="stock",
            total_asset=Decimal("1000"),
            available_cash=Decimal("800"),
            frozen_cash=Decimal("0"),
            market_value=Decimal("200"),
            pnl=Decimal("10"),
            snapshot_time=now,
        ),
    )
    assets.insert_snapshot(
        futures.id,
        AccountSnapshot(
            account_id=uuid4(),
            account_no="futures",
            total_asset=Decimal("500"),
            available_cash=Decimal("400"),
            frozen_cash=Decimal("0"),
            market_value=Decimal("100"),
            pnl=Decimal("5"),
            snapshot_time=now,
        ),
    )
    positions.insert_snapshot(
        PositionSnapshot(
            account_id=stock.id,
            symbol="600000.SH",
            market=Market.STOCK,
            direction="net",
            quantity=Decimal("20"),
            available_quantity=Decimal("20"),
            avg_cost=Decimal("10"),
            market_value=Decimal("200"),
            pnl=Decimal("10"),
            snapshot_time=now,
        )
    )
    positions.insert_snapshot(
        PositionSnapshot(
            account_id=futures.id,
            symbol="IF2509",
            market=Market.FUTURES,
            direction="net",
            quantity=Decimal("1"),
            available_quantity=Decimal("1"),
            avg_cost=Decimal("100"),
            market_value=Decimal("100"),
            pnl=Decimal("5"),
            snapshot_time=now,
        )
    )
    db.flush()

    snapshot = AccountSnapshotService(db).get_snapshot()

    assert snapshot["reconciled"] is True
    assert snapshot["total_asset"] == "1500"
    assert snapshot["available_cash"] == "1200"
    assert snapshot["market_value"] == "300"
    assert snapshot["other_equity"] == "0"
    assert len(snapshot["component_snapshot_ids"]) == 4
    assert len(snapshot["positions"]) == 2


def test_sync_positions_writes_zero_snapshot_for_disappeared_position(db, monkeypatch):
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    PositionRepository(db).insert_snapshot(
        PositionSnapshot(
            account_id=account.id,
            symbol="600000.SH",
            market=Market.STOCK,
            direction="net",
            quantity=Decimal("100"),
            available_quantity=Decimal("100"),
            avg_cost=Decimal("10"),
            market_value=Decimal("1000"),
            pnl=Decimal("0"),
            snapshot_time=datetime(2026, 7, 31, 1, 0, tzinfo=timezone.utc),
        )
    )
    db.flush()

    adapter = type("Adapter", (), {"get_positions": lambda self: []})()
    monkeypatch.setattr("app.workers.sync_jobs.market_service._started", True)
    monkeypatch.setattr(
        "app.workers.sync_jobs.sdk_manager.get_adapter_for_market",
        lambda market: adapter,
    )

    sync_positions(db)

    assert PositionRepository(db).list_latest(
        account_id=account.id, market=Market.STOCK
    ) == []
    latest = (
        db.query(Position)
        .filter(Position.account_id == account.id, Position.symbol == "600000.SH")
        .order_by(Position.snapshot_time.desc())
        .first()
    )
    assert Decimal(str(latest.quantity)) == Decimal("0")
