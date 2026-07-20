from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc

from app.db.models.account_asset import AccountAsset
from app.repositories.base import BaseRepository
from app.sdk.models import AccountSnapshot


class AssetRepository(BaseRepository[AccountAsset]):
    model = AccountAsset

    def insert_snapshot(self, account_id: UUID, snap: AccountSnapshot) -> AccountAsset:
        row = AccountAsset(
            account_id=account_id,
            total_asset=snap.total_asset,
            available_cash=snap.available_cash,
            frozen_cash=snap.frozen_cash,
            market_value=snap.market_value,
            pnl=snap.pnl,
            snapshot_time=snap.snapshot_time,
            raw_payload=snap.raw_payload,
        )
        return self.add(row)

    def get_latest(self, account_id: UUID) -> AccountAsset | None:
        return (
            self.db.query(AccountAsset)
            .filter(AccountAsset.account_id == account_id)
            .order_by(desc(AccountAsset.snapshot_time))
            .first()
        )

    def list_latest(self, *, account_id: UUID | None = None, limit: int = 50) -> list[AccountAsset]:
        q = self.db.query(AccountAsset)
        if account_id is not None:
            q = q.filter(AccountAsset.account_id == account_id)
        return q.order_by(desc(AccountAsset.snapshot_time)).limit(limit).all()

    def curve(
        self,
        range_start: datetime,
        range_end: datetime,
        *,
        account_id: UUID | None = None,
    ) -> list[dict]:
        q = self.db.query(AccountAsset).filter(
            AccountAsset.snapshot_time >= range_start,
            AccountAsset.snapshot_time <= range_end,
        )
        if account_id is not None:
            q = q.filter(AccountAsset.account_id == account_id)
        rows = q.order_by(AccountAsset.snapshot_time.asc()).all()
        return [
            {
                "total_asset": r.total_asset,
                "snapshot_time": r.snapshot_time,
                "pnl": r.pnl,
            }
            for r in rows
        ]
