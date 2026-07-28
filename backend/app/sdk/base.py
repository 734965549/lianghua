from abc import ABC, abstractmethod
from typing import Callable

from app.schemas.enums import Market
from app.schemas.error_codes import ErrorCode
from app.sdk.models import (
    AccountSnapshot,
    AdapterStatus,
    CancelOrderRequest,
    CancelOrderResult,
    ConnectionEvent,
    KlineBar,
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


class AdapterError(Exception):
    """适配器标准错误基类。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        raw_code: str | None = None,
        raw_message: str | None = None,
        retryable: bool = False,
    ):
        self.code = code
        self.message = message
        self.raw_code = raw_code
        self.raw_message = raw_message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


class SDKNotConfigured(AdapterError):
    def __init__(self, msg: str = "SDK 未配置"):
        super().__init__(ErrorCode.SDK_NOT_CONFIGURED, msg)


class SDKConnectionFailed(AdapterError):
    def __init__(self, msg: str = "SDK 连接失败", **kw):
        super().__init__(ErrorCode.SDK_CONNECTION_FAILED, msg, retryable=True, **kw)


class SDKAuthFailed(AdapterError):
    def __init__(self, msg: str = "SDK 授权失败", **kw):
        super().__init__(ErrorCode.SDK_AUTH_FAILED, msg, **kw)


class SDKTimeout(AdapterError):
    def __init__(self, msg: str = "SDK 调用超时", **kw):
        super().__init__(ErrorCode.SDK_TIMEOUT, msg, retryable=True, **kw)


class SDKResponseInvalid(AdapterError):
    def __init__(self, msg: str = "SDK 返回字段异常", **kw):
        super().__init__(ErrorCode.SDK_RESPONSE_INVALID, msg, **kw)


class SDKOrderRejected(AdapterError):
    def __init__(self, msg: str = "SDK 拒绝委托", **kw):
        super().__init__(ErrorCode.SDK_ORDER_REJECTED, msg, **kw)


class SDKCancelRejected(AdapterError):
    def __init__(self, msg: str = "SDK 拒绝撤单", **kw):
        super().__init__(ErrorCode.SDK_CANCEL_REJECTED, msg, **kw)


class SDKDisconnected(AdapterError):
    def __init__(self, msg: str = "SDK 连接中断", **kw):
        super().__init__(ErrorCode.SDK_DISCONNECTED, msg, retryable=True, **kw)


class TradingAdapter(ABC):
    """适配器抽象基类。"""

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
    def connect(self) -> AdapterStatus: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_account(self) -> AccountSnapshot: ...

    @abstractmethod
    def get_positions(self) -> list[PositionSnapshot]: ...

    @abstractmethod
    def get_quote(self, symbol: str) -> QuoteSnapshot: ...

    @abstractmethod
    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]: ...

    @abstractmethod
    def subscribe_quotes(self, symbols: list[str]) -> None: ...

    @abstractmethod
    def query_orders(self, filters: OrderQuery | dict | None = None) -> list[OrderSnapshot]: ...

    @abstractmethod
    def query_trades(self, filters: TradeQuery | dict | None = None) -> list[TradeSnapshot]: ...

    @abstractmethod
    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult: ...

    @abstractmethod
    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult: ...
