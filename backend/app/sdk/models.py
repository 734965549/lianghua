from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction


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
    raw_payload: dict | None = None


class ConnectionEvent(BaseModel):
    market: Market
    connected: bool
    reason: str = ""
    event_time: datetime
