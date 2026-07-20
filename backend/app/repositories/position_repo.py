from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc

from app.db.models.position import Position
from app.repositories.base import BaseRepository
from app.schemas.enums import Market
from app.sdk.models import PositionSnapshot


class PositionRepository(BaseRepository[Position]):
    model = Position

    def insert_snapshot(self, snap: PositionSnapshot) -> Position:
        row = Position(
            account_id=snap.account_id,
            symbol=snap.symbol,
            market=snap.market,
            direction=snap.direction,
            quantity=snap.quantity,
            available_quantity=snap.available_quantity,
            avg_cost=snap.avg_cost,
            market_value=snap.market_value,
            pnl=snap.pnl,
            snapshot_time=snap.snapshot_time,
            raw_payload=snap.raw_payload,
        )
        return self.add(row)

    def list_latest(
        self,
        *,
        account_id: UUID | None = None,
        market: Market | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[Position]:
        q = self.db.query(Position)
        if account_id is not None:
            q = q.filter(Position.account_id == account_id)
        if market is not None:
            q = q.filter(Position.market == market)
        if symbol:
            q = q.filter(Position.symbol == symbol)
        return q.order_by(desc(Position.snapshot_time)).limit(limit).all()

    def get_latest_for_symbol(
        self,
        *,
        account_id: UUID,
        market: Market,
        symbol: str,
    ) -> Position | None:
        return (
            self.db.query(Position)
            .filter(
                Position.account_id == account_id,
                Position.market == market,
                Position.symbol == symbol,
            )
            .order_by(desc(Position.snapshot_time))
            .first()
        )
