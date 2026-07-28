from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models.strategy_signal import StrategySignal
from app.repositories.base import BaseRepository
from app.schemas.enums import Market, OrderSide, PriceType, SignalAction


class SignalRepository(BaseRepository[StrategySignal]):
    model = StrategySignal

    def add_signal(
        self,
        *,
        signal_id: UUID,
        strategy_id: str,
        symbol: str,
        market: Market,
        side: OrderSide,
        action: SignalAction,
        price_type: PriceType,
        price: Decimal,
        quantity: Decimal,
        reason: str,
        signal_time: datetime,
        metadata: dict | None = None,
    ) -> StrategySignal:
        row = StrategySignal(
            signal_id=signal_id,
            strategy_id=strategy_id,
            symbol=symbol,
            market=market,
            side=side,
            action=action,
            price_type=price_type,
            price=price,
            quantity=quantity,
            reason=reason,
            signal_time=signal_time,
            metadata_=metadata or {},
        )
        return self.add(row)

    def list_signals(
        self,
        *,
        strategy_id: str | None = None,
        symbol: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[StrategySignal], int]:
        q = self.db.query(StrategySignal)
        if strategy_id:
            q = q.filter(StrategySignal.strategy_id == strategy_id)
        if symbol:
            q = q.filter(StrategySignal.symbol == symbol)
        total = q.count()
        rows = q.order_by(desc(StrategySignal.signal_time)).offset(offset).limit(limit).all()
        return rows, total

    def recent_duplicates(
        self,
        *,
        strategy_id: str,
        symbol: str,
        side: OrderSide,
        action: SignalAction | None = None,
        window_seconds: int,
        now: datetime | None = None,
    ) -> list[StrategySignal]:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)
        q = self.db.query(StrategySignal).filter(
            StrategySignal.strategy_id == strategy_id,
            StrategySignal.symbol == symbol,
            StrategySignal.side == side,
            StrategySignal.signal_time >= cutoff,
        )
        if action is not None:
            q = q.filter(StrategySignal.action == action)
        return q.order_by(desc(StrategySignal.signal_time)).all()

