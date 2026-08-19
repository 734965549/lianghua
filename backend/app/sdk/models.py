from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.enums import (
    HedgeFlag,
    Market,
    OffsetFlag,
    OrderSide,
    OrderStatus,
    PositionDate,
    PositionDirection,
    PriceType,
    SignalAction,
)


class AdapterStatus(BaseModel):
    connected: bool
    account_no: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class QuoteSnapshot(BaseModel):
    symbol: str
    market: Market
    last_price: Decimal
    change_rate: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    bid_volume: Decimal | None = None
    ask_volume: Decimal | None = None
    quote_time: datetime
    raw_payload: dict | None = None


class KlineBar(BaseModel):
    symbol: str
    market: Market
    interval: str
    bar_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    raw_payload: dict | None = None


class PositionSnapshot(BaseModel):
    account_id: UUID
    symbol: str
    market: Market
    direction: str = "net"
    quantity: Decimal
    available_quantity: Decimal
    avg_cost: Decimal
    market_value: Decimal
    pnl: Decimal
    snapshot_time: datetime
    # 期货扩展（8.2 节）：多空、今昨仓、冻结与可平数量
    exchange_id: str = ""
    position_date: PositionDate | str | None = None
    position_direction: PositionDirection | str | None = None
    quantity_today: Decimal = Decimal("0")
    quantity_yesterday: Decimal = Decimal("0")
    frozen_quantity: Decimal = Decimal("0")
    frozen_today: Decimal = Decimal("0")
    frozen_yesterday: Decimal = Decimal("0")
    available_today: Decimal = Decimal("0")
    available_yesterday: Decimal = Decimal("0")
    margin: Decimal = Decimal("0")
    position_profit: Decimal = Decimal("0")
    trading_day: str | None = None
    raw_payload: dict | None = None


class AccountSnapshot(BaseModel):
    account_id: UUID
    account_no: str
    total_asset: Decimal
    available_cash: Decimal
    frozen_cash: Decimal
    market_value: Decimal
    pnl: Decimal
    snapshot_time: datetime
    # 期货扩展（8.3 节）：CTP 资金账户字段，可空兼容股票
    balance: Decimal | None = None
    curr_margin: Decimal | None = None
    frozen_margin: Decimal | None = None
    commission: Decimal | None = None
    close_profit: Decimal | None = None
    position_profit: Decimal | None = None
    risk_ratio: Decimal | None = None
    trading_day: str | None = None
    raw_payload: dict | None = None


class PlaceOrderRequest(BaseModel):
    client_order_id: str
    account_id: UUID
    market: Market
    symbol: str
    side: OrderSide
    action: SignalAction
    price_type: PriceType
    price: Decimal | None = None
    quantity: Decimal
    metadata: dict = Field(default_factory=dict)
    # 期货强类型字段（8.1 节）：迁移期可从 metadata 读取兼容值
    exchange_id: str = ""
    offset_flag: OffsetFlag | str | None = None
    hedge_flag: HedgeFlag | str | None = None
    trading_day: str | None = None


class PlaceOrderResult(BaseModel):
    success: bool
    client_order_id: str
    sdk_order_id: str | None = None
    status: OrderStatus
    message: str = ""
    raw_payload: dict | None = None


class CancelOrderRequest(BaseModel):
    client_order_id: str
    sdk_order_id: str | None = None
    market: Market
    reason: str = ""


class CancelOrderResult(BaseModel):
    success: bool
    client_order_id: str
    sdk_order_id: str | None = None
    status: OrderStatus
    message: str = ""
    raw_payload: dict | None = None


class OrderUpdateEvent(BaseModel):
    client_order_id: str | None = None
    sdk_order_id: str | None = None
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    event_time: datetime
    # 期货强类型字段
    exchange_id: str = ""
    offset_flag: OffsetFlag | str | None = None
    hedge_flag: HedgeFlag | str | None = None
    trading_day: str | None = None
    broker_type: str = ""
    raw_payload: dict | None = None


class TradeUpdateEvent(BaseModel):
    sdk_trade_id: str
    client_order_id: str | None = None
    sdk_order_id: str | None = None
    symbol: str
    market: Market
    side: OrderSide
    price: Decimal
    quantity: Decimal
    fee: Decimal = Decimal("0")
    trade_time: datetime
    # 期货强类型字段：成交唯一键需包含 broker/账户/交易日/交易所
    exchange_id: str = ""
    trading_day: str | None = None
    broker_type: str = ""
    raw_payload: dict | None = None


class ConnectionEvent(BaseModel):
    market: Market
    connected: bool
    reason: str = ""
    event_time: datetime


class OrderQuery(BaseModel):
    """订单查询过滤条件。"""

    client_order_id: str | None = None
    sdk_order_id: str | None = None
    symbol: str | None = None
    status: OrderStatus | str | None = None

    model_config = {"extra": "allow"}


class TradeQuery(BaseModel):
    """成交查询过滤条件。"""

    client_order_id: str | None = None
    sdk_order_id: str | None = None
    symbol: str | None = None
    sdk_trade_id: str | None = None

    model_config = {"extra": "allow"}


class OrderSnapshot(BaseModel):
    """轮询/查询得到的订单快照。"""

    client_order_id: str | None = None
    sdk_order_id: str | None = None
    status: OrderStatus | str
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    symbol: str | None = None
    market: Market | None = None
    # 期货扩展：委托身份与开平/投保
    exchange_id: str = ""
    offset_flag: OffsetFlag | str | None = None
    hedge_flag: HedgeFlag | str | None = None
    trading_day: str | None = None
    order_ref: str | None = None
    front_id: int | None = None
    session_id: int | None = None
    order_sys_id: str | None = None
    raw_payload: dict | None = None


class TradeSnapshot(BaseModel):
    """轮询/查询得到的成交快照。"""

    sdk_trade_id: str
    client_order_id: str | None = None
    sdk_order_id: str | None = None
    symbol: str = ""
    market: Market | None = None
    side: OrderSide | str | None = None
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    trade_time: datetime | None = None
    # 期货扩展
    exchange_id: str = ""
    trading_day: str | None = None
    raw_payload: dict | None = None


def coerce_order_query(filters: OrderQuery | dict | None) -> OrderQuery:
    if filters is None:
        return OrderQuery()
    if isinstance(filters, OrderQuery):
        return filters
    return OrderQuery.model_validate(filters)


def coerce_trade_query(filters: TradeQuery | dict | None) -> TradeQuery:
    if filters is None:
        return TradeQuery()
    if isinstance(filters, TradeQuery):
        return filters
    return TradeQuery.model_validate(filters)


def coerce_order_snapshots(rows: list) -> list[OrderSnapshot]:
    out: list[OrderSnapshot] = []
    for r in rows:
        if isinstance(r, OrderSnapshot):
            out.append(r)
            continue
        d = dict(r)
        if "filled_quantity" not in d and d.get("filled") is not None:
            d["filled_quantity"] = d["filled"]
        out.append(OrderSnapshot.model_validate(d))
    return out


def coerce_trade_snapshots(rows: list) -> list[TradeSnapshot]:
    out: list[TradeSnapshot] = []
    for r in rows:
        if isinstance(r, TradeSnapshot):
            out.append(r)
            continue
        if isinstance(r, TradeUpdateEvent):
            out.append(
                TradeSnapshot(
                    sdk_trade_id=r.sdk_trade_id,
                    client_order_id=r.client_order_id,
                    sdk_order_id=r.sdk_order_id,
                    symbol=r.symbol,
                    market=r.market,
                    side=r.side,
                    price=r.price,
                    quantity=r.quantity,
                    fee=r.fee,
                    trade_time=r.trade_time,
                    raw_payload=r.raw_payload,
                )
            )
            continue
        out.append(TradeSnapshot.model_validate(r))
    return out
