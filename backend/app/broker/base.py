from abc import ABC, abstractmethod
from typing import Callable

from app.schemas.enums import Market
from app.sdk.models import (
    AccountSnapshot,
    CancelOrderRequest,
    CancelOrderResult,
    ConnectionEvent,
    OrderQuery,
    OrderSnapshot,
    OrderUpdateEvent,
    PlaceOrderRequest,
    PlaceOrderResult,
    PositionSnapshot,
    QuoteSnapshot,
    TradeQuery,
    TradeSnapshot,
    TradeUpdateEvent,
)


class Broker(ABC):
    """真实交易接口抽象基类，支持 QMT / PTrade / THS / Mock 等实现。"""

    market: Market

    def __init__(self):
        self._on_order_update: Callable[[OrderUpdateEvent], None] | None = None
        self._on_trade_update: Callable[[TradeUpdateEvent], None] | None = None
        self._on_quote_update: Callable[[QuoteSnapshot], None] | None = None
        self._on_connection_change: Callable[[ConnectionEvent], None] | None = None

    def on_order_update(self, cb: Callable[[OrderUpdateEvent], None]) -> None:
        self._on_order_update = cb

    def on_trade_update(self, cb: Callable[[TradeUpdateEvent], None]) -> None:
        self._on_trade_update = cb

    def on_quote_update(self, cb: Callable[[QuoteSnapshot], None]) -> None:
        self._on_quote_update = cb

    def on_connection_change(self, cb: Callable[[ConnectionEvent], None]) -> None:
        self._on_connection_change = cb

    @abstractmethod
    def connect(self) -> dict: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def get_account(self) -> AccountSnapshot: ...

    @abstractmethod
    def get_positions(self) -> list[PositionSnapshot]: ...

    @abstractmethod
    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult: ...

    @abstractmethod
    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult: ...
    @abstractmethod
    def query_orders(self, request: OrderQuery | None = None) -> list[OrderSnapshot]: ...

    @abstractmethod
    def query_trades(self, request: TradeQuery | None = None) -> list[TradeSnapshot]: ...
