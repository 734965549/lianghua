from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models.order import Order
from app.repositories.base import BaseRepository
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction


TERMINAL_STATUSES = {
    OrderStatus.RISK_REJECTED,
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.FAILED,
}


class OrderRepository(BaseRepository[Order]):
    model = Order

    def get_by_client_order_id(self, client_order_id: str) -> Order | None:
        return self.db.query(Order).filter(Order.client_order_id == client_order_id).first()

    def get_by_id(self, order_id: UUID) -> Order | None:
        return self.db.get(Order, order_id)

    def create_order(
        self,
        *,
        client_order_id: str,
        account_id: UUID,
        strategy_id: str | None,
        signal_id: UUID | None,
        symbol: str,
        market: Market,
        side: OrderSide,
        action: SignalAction,
        price_type: PriceType,
        price: Decimal,
        quantity: Decimal,
        status: OrderStatus,
        submitted_at: datetime | None = None,
    ) -> Order:
        row = Order(
            client_order_id=client_order_id,
            account_id=account_id,
            strategy_id=strategy_id,
            signal_id=signal_id,
            symbol=symbol,
            market=market,
            side=side,
            action=action,
            price_type=price_type,
            price=price,
            quantity=quantity,
            status=status,
            submitted_at=submitted_at,
            last_event_at=submitted_at,
        )
        return self.add(row)

    def list_orders(
        self,
        *,
        market: Market | None = None,
        symbol: str | None = None,
        status: OrderStatus | None = None,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Order], int]:
        q = self.db.query(Order)
        if market is not None:
            q = q.filter(Order.market == market)
        if symbol:
            q = q.filter(Order.symbol == symbol)
        if status is not None:
            q = q.filter(Order.status == status)
        if strategy_id:
            q = q.filter(Order.strategy_id == strategy_id)
        if start is not None:
            q = q.filter(Order.created_at >= start)
        if end is not None:
            q = q.filter(Order.created_at <= end)
        total = q.count()
        rows = q.order_by(desc(Order.created_at)).offset(offset).limit(limit).all()
        return rows, total

    def list_orders_export(
        self,
        *,
        market: Market | None = None,
        symbol: str | None = None,
        status: OrderStatus | None = None,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 10000,
    ) -> list[Order]:
        rows, _ = self.list_orders(
            market=market,
            symbol=symbol,
            status=status,
            strategy_id=strategy_id,
            start=start,
            end=end,
            offset=0,
            limit=limit,
        )
        return rows

    def list_open_orders(self, *, limit: int = 100) -> list[Order]:
        open_statuses = [
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.UNKNOWN,
        ]
        return (
            self.db.query(Order)
            .filter(Order.status.in_(open_statuses))
            .order_by(desc(Order.created_at))
            .limit(limit)
            .all()
        )
