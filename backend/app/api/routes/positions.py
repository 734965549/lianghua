from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.core.time import to_utc_iso
from app.repositories.account_repo import AccountRepository
from app.repositories.asset_repo import AssetRepository
from app.repositories.position_repo import PositionRepository
from app.schemas.enums import Market
from app.services.account_snapshot_service import AccountSnapshotService


def _decimal_str(value) -> str:
    return str(value)


def _position_to_dict(row) -> dict:
    return {
        "id": str(row.id),
        "account_id": str(row.account_id),
        "symbol": row.symbol,
        "market": row.market.value,
        "direction": row.direction,
        "quantity": _decimal_str(row.quantity),
        "available_quantity": _decimal_str(row.available_quantity),
        "avg_cost": _decimal_str(row.avg_cost),
        "market_value": _decimal_str(row.market_value),
        "pnl": _decimal_str(row.pnl),
        "snapshot_time": to_utc_iso(row.snapshot_time),
        "created_at": to_utc_iso(row.created_at),
    }


def _asset_to_dict(row) -> dict:
    return {
        "id": str(row.id),
        "account_id": str(row.account_id),
        "total_asset": _decimal_str(row.total_asset),
        "available_cash": _decimal_str(row.available_cash),
        "frozen_cash": _decimal_str(row.frozen_cash),
        "market_value": _decimal_str(row.market_value),
        "pnl": _decimal_str(row.pnl),
        "snapshot_time": to_utc_iso(row.snapshot_time),
        "created_at": to_utc_iso(row.created_at),
    }


router = APIRouter(tags=["positions"])


@router.get("/account-snapshot")
def get_account_snapshot(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    snapshot = AccountSnapshotService(db).get_snapshot()
    positions = snapshot.pop("positions")
    snapshot["positions"] = [_position_to_dict(row) for row in positions]
    return ok(snapshot, correlation_id=correlation_id)


@router.get("/positions")
def list_positions(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    account_id: str | None = None,
    market: str | None = None,
    symbol: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    mkt = Market(market) if market else None
    acct = UUID(account_id) if account_id else None
    repo = PositionRepository(db)
    rows = repo.list_latest(account_id=acct, market=mkt, symbol=symbol, limit=limit)
    return ok({"items": [_position_to_dict(r) for r in rows]}, correlation_id=correlation_id)


@router.get("/assets")
def list_assets(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    account_id: str | None = None,
    market: str | None = None,
    limit: int = Query(10, ge=2, le=1000),
):
    asset_repo = AssetRepository(db)
    if account_id:
        row = asset_repo.get_latest(UUID(account_id))
        items = [_asset_to_dict(row)] if row else []
    elif market:
        account = AccountRepository(db).get_or_create_default(Market(market))
        row = asset_repo.get_latest(account.id)
        items = [_asset_to_dict(row)] if row else []
    else:
        rows = asset_repo.list_latest(limit=limit)
        items = [_asset_to_dict(r) for r in rows]
    return ok({"items": items}, correlation_id=correlation_id)
