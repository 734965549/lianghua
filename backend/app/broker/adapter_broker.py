from typing import Callable

from app.broker.base import Broker
from app.sdk.base import TradingAdapter
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


class AdapterBroker(Broker):
    """基于现有 TradingAdapter 的 Broker 实现，用于 THS / Mock / Akshare 等适配器。

    初始化时会保留 adapter 上已存在的回调，触发事件时同时调用原回调和 broker
    自身注册的回调，避免创建 broker 后覆盖测试或市场服务注册的回调。
    """

    def __init__(self, adapter: TradingAdapter):
        super().__init__()
        self._adapter = adapter
        # 保存 adapter 上已有的回调（如测试、市场服务直接注册到 adapter 的回调）
        self._adapter_order_update_cb: Callable[[OrderUpdateEvent], None] | None = getattr(
            adapter, "_on_order_update", None
        )
        self._adapter_trade_update_cb: Callable[[TradeUpdateEvent], None] | None = getattr(
            adapter, "_on_trade_update", None
        )
        self._adapter_quote_update_cb: Callable[[QuoteSnapshot], None] | None = getattr(
            adapter, "_on_quote_update", None
        )
        self._adapter_connection_change_cb: Callable[[ConnectionEvent], None] | None = getattr(
            adapter, "_on_connection_change", None
        )
        self._adapter.on_order_update(self._emit_order_update)
        self._adapter.on_trade_update(self._emit_trade_update)
        self._adapter.on_quote_update(self._emit_quote_update)
        self._adapter.on_connection_change(self._emit_connection_change)

    def _emit_order_update(self, event: OrderUpdateEvent) -> None:
        if self._adapter_order_update_cb:
            self._adapter_order_update_cb(event)
        if self._on_order_update:
            self._on_order_update(event)

    def _emit_trade_update(self, event: TradeUpdateEvent) -> None:
        if self._adapter_trade_update_cb:
            self._adapter_trade_update_cb(event)
        if self._on_trade_update:
            self._on_trade_update(event)

    def _emit_quote_update(self, event: QuoteSnapshot) -> None:
        if self._adapter_quote_update_cb:
            self._adapter_quote_update_cb(event)
        if self._on_quote_update:
            self._on_quote_update(event)

    def _emit_connection_change(self, event: ConnectionEvent) -> None:
        if self._adapter_connection_change_cb:
            self._adapter_connection_change_cb(event)
        if self._on_connection_change:
            self._on_connection_change(event)

    @property
    def market(self):
        return self._adapter.market

    @property
    def adapter(self) -> TradingAdapter:
        return self._adapter

    def connect(self) -> dict:
        status = self._adapter.connect()
        return status.model_dump(mode="json") if hasattr(status, "model_dump") else dict(status)

    def disconnect(self) -> None:
        self._adapter.disconnect()

    def is_connected(self) -> bool:
        return getattr(self._adapter, "_connected", True)

    def get_account(self) -> AccountSnapshot:
        return self._adapter.get_account()

    def get_positions(self) -> list[PositionSnapshot]:
        return self._adapter.get_positions()

    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        return self._adapter.place_order(request)

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult:
        return self._adapter.cancel_order(request)

    def query_orders(self, request: OrderQuery | None = None) -> list[OrderSnapshot]:
        return self._adapter.query_orders(request)

    def query_trades(self, request: TradeQuery | None = None) -> list[TradeSnapshot]:
        return self._adapter.query_trades(request)
