from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc

from app.db.models.trade import Trade
from app.repositories.base import BaseRepository
from app.schemas.enums import Market, OrderSide


class TradeRepository(BaseRepository[Trade]):
    model = Trade

    def get_by_sdk_trade_id(self, market: Market, sdk_trade_id: str) -> Trade | None:
        return (
            self.db.query(Trade)
            .filter(Trade.market == market, Trade.sdk_trade_id == sdk_trade_id)
            .first()
        )

    def create_trade(
        self,
        *,
        sdk_trade_id: str,
        client_order_id: str,
        sdk_order_id: str | None,
        account_id: UUID,
        strategy_id: str | None,
        symbol: str,
        market: Market,
        side: OrderSide,
        price: Decimal,
        quantity: Decimal,
        fee: Decimal,
        trade_time: datetime,
        raw_payload: dict | None = None,
    ) -> Trade:
        row = Trade(
            sdk_trade_id=sdk_trade_id,
            client_order_id=client_order_id,
            sdk_order_id=sdk_order_id,
            account_id=account_id,
            strategy_id=strategy_id,
            symbol=symbol,
            market=market,
            side=side,
            price=price,
            quantity=quantity,
            fee=fee,
            trade_time=trade_time,
            raw_payload=raw_payload,
        )
        return self.add(row)

    def list_trades(
        self,
        *,
        market: Market | None = None,
        symbol: str | None = None,
        client_order_id: str | None = None,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Trade], int]:
        q = self.db.query(Trade)
        if market is not None:
            q = q.filter(Trade.market == market)
        if symbol:
            q = q.filter(Trade.symbol == symbol)
        if client_order_id:
            q = q.filter(Trade.client_order_id == client_order_id)
        if strategy_id:
            q = q.filter(Trade.strategy_id == strategy_id)
        if start is not None:
            q = q.filter(Trade.trade_time >= start)
        if end is not None:
            q = q.filter(Trade.trade_time <= end)
        total = q.count()
        rows = q.order_by(desc(Trade.trade_time)).offset(offset).limit(limit).all()
        return rows, total

    def query_for_metrics(
        self,
        *,
        range_start: datetime,
        range_end: datetime,
        strategy_ids: list[str] | None = None,
        markets: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> list[dict]:
        """返回指标计算用的成交字典列表（按成交时间升序，便于 FIFO）。"""
        q = self.db.query(Trade).filter(
            Trade.trade_time >= range_start,
            Trade.trade_time <= range_end,
        )
        if strategy_ids:
            q = q.filter(Trade.strategy_id.in_(strategy_ids))
        if markets:
            mkt_enums = [Market(m) if not isinstance(m, Market) else m for m in markets]
            q = q.filter(Trade.market.in_(mkt_enums))
        if symbols:
            q = q.filter(Trade.symbol.in_(symbols))
        rows = q.order_by(Trade.trade_time.asc()).all()
        return [
            {
                "sdk_trade_id": r.sdk_trade_id,
                "client_order_id": r.client_order_id,
                "strategy_id": r.strategy_id,
                "symbol": r.symbol,
                "market": r.market.value if hasattr(r.market, "value") else str(r.market),
                "side": r.side.value if hasattr(r.side, "value") else str(r.side),
                "price": r.price,
                "quantity": r.quantity,
                "fee": r.fee,
                "trade_time": r.trade_time,
            }
            for r in rows
        ]

    def list_by_client_order_id(self, client_order_id: str) -> list[Trade]:
        return (
            self.db.query(Trade)
            .filter(Trade.client_order_id == client_order_id)
            .order_by(Trade.trade_time.asc())
            .all()
        )
