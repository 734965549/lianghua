"""统一账户、持仓和资金口径。"""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256

from sqlalchemy.orm import Session

from app.core.time import as_utc, to_utc_iso
from app.repositories.account_repo import AccountRepository
from app.repositories.asset_repo import AssetRepository
from app.repositories.position_repo import PositionRepository
from app.schemas.enums import Market


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return text or "0"


class AccountSnapshotService:
    """从同一组最新资金/持仓行构建可复用的账户快照。"""

    def __init__(self, db: Session):
        self.db = db
        self.accounts = AccountRepository(db)
        self.assets = AssetRepository(db)
        self.positions = PositionRepository(db)

    def get_snapshot(self) -> dict:
        asset_rows = []
        position_rows = []
        for market in (Market.STOCK, Market.FUTURES):
            account = self.accounts.get_by_market(market)
            if account is None:
                continue
            asset = self.assets.get_latest(account.id)
            if asset is not None:
                asset_rows.append(asset)
            position_rows.extend(
                self.positions.list_latest(
                    account_id=account.id,
                    market=market,
                    limit=500,
                )
            )

        total_asset = sum((_decimal(row.total_asset) for row in asset_rows), Decimal("0"))
        available_cash = sum(
            (_decimal(row.available_cash) for row in asset_rows), Decimal("0")
        )
        frozen_cash = sum(
            (_decimal(row.frozen_cash) for row in asset_rows), Decimal("0")
        )
        reported_market_value = sum(
            (_decimal(row.market_value) for row in asset_rows), Decimal("0")
        )
        market_value = sum(
            (
                _decimal(row.market_value)
                for row in position_rows
                if _decimal(row.quantity) != 0
            ),
            Decimal("0"),
        )
        pnl = sum((_decimal(row.pnl) for row in position_rows), Decimal("0"))
        other_equity = total_asset - available_cash - frozen_cash - market_value
        market_value_delta = reported_market_value - market_value
        reconciled = bool(asset_rows) and (
            abs(market_value_delta) <= Decimal("0.01")
            and other_equity >= Decimal("-0.01")
        )

        component_ids = sorted(
            [str(row.id) for row in asset_rows]
            + [str(row.id) for row in position_rows]
        )
        snapshot_id = sha256("|".join(component_ids).encode("utf-8")).hexdigest()[:20]
        snapshot_times = [
            as_utc(row.snapshot_time) for row in [*asset_rows, *position_rows]
        ]
        snapshot_time = max(snapshot_times) if snapshot_times else None

        return {
            "snapshot_id": snapshot_id,
            "snapshot_time": to_utc_iso(snapshot_time),
            "total_asset": _decimal_text(total_asset),
            "available_cash": _decimal_text(available_cash),
            "frozen_cash": _decimal_text(frozen_cash),
            "market_value": _decimal_text(market_value),
            "reported_market_value": _decimal_text(reported_market_value),
            "other_equity": _decimal_text(other_equity),
            "pnl": _decimal_text(pnl),
            "market_value_delta": _decimal_text(market_value_delta),
            "reconciled": reconciled,
            "has_account_snapshot": bool(asset_rows),
            "component_snapshot_ids": component_ids,
            "positions": position_rows,
        }
