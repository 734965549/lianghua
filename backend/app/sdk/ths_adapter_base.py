"""真实同花顺适配器基类：封装 driver + 字段映射 + 本地订单 ID 映射。"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.schemas.enums import Market
from app.sdk.base import SDKDisconnected, TradingAdapter
from app.sdk.drivers import create_driver
from app.sdk import mapping
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


class ThsTradingAdapterBase(TradingAdapter):
    """股票/期货真实适配器共享逻辑。"""

    def __init__(self, *, market: Market, config: dict | None = None):
        super().__init__()
        self.market = market
        self.config = config or {}
        self._driver = create_driver(market=market, config=self.config)
        self._connected = False
        self._account_no: str | None = None
        self._account_id: UUID | None = None
        self._client_to_sdk: dict[str, str] = {}
        self._sdk_to_client: dict[str, str] = {}

        self._driver.set_order_callback(self._handle_raw_order)
        self._driver.set_trade_callback(self._handle_raw_trade)
        self._driver.set_quote_callback(self._handle_raw_quote)
        self._driver.set_connection_callback(self._handle_raw_connection)

    def _resolve_client_id(self, sdk_order_id: str | None) -> str | None:
        if not sdk_order_id:
            return None
        return self._sdk_to_client.get(sdk_order_id)

    def _remember_mapping(self, client_order_id: str, sdk_order_id: str) -> None:
        self._client_to_sdk[client_order_id] = sdk_order_id
        self._sdk_to_client[sdk_order_id] = client_order_id

    def connect(self) -> AdapterStatus:
        raw = self._driver.connect()
        self._connected = bool(raw.get("connected", True))
        self._account_no = str(raw.get("AcctNo") or raw.get("account_no") or "")
        if self._on_connection_change:
            self._on_connection_change(
                ConnectionEvent(
                    market=self.market,
                    connected=self._connected,
                    event_time=datetime.now(timezone.utc),
                )
            )
        return AdapterStatus(
            connected=self._connected,
            account_no=self._account_no or None,
            latency_ms=raw.get("latency_ms"),
        )

    def disconnect(self) -> None:
        self._driver.disconnect()
        self._connected = False
        if self._on_connection_change:
            self._on_connection_change(
                ConnectionEvent(
                    market=self.market,
                    connected=False,
                    reason="disconnect",
                    event_time=datetime.now(timezone.utc),
                )
            )

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise SDKDisconnected(f"{self.market.value} SDK 未连接")

    def get_account(self) -> AccountSnapshot:
        self._ensure_connected()
        raw = self._driver.get_account()
        snap = mapping.map_account(raw, market=self.market, account_id=self._account_id)
        self._account_id = snap.account_id
        self._account_no = snap.account_no
        return snap

    def get_positions(self) -> list[PositionSnapshot]:
        self._ensure_connected()
        if self._account_id is None:
            self.get_account()
        account_id = self._account_id or uuid4()
        return [
            mapping.map_position(row, market=self.market, account_id=account_id)
            for row in self._driver.get_positions()
        ]

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self._ensure_connected()
        return mapping.map_quote(self._driver.get_quote(symbol), market=self.market)

    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        self._ensure_connected()
        return [
            mapping.map_kline(row, market=self.market, interval=interval)
            for row in self._driver.get_kline(symbol, interval, start, end)
        ]

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._ensure_connected()
        self._driver.subscribe_quotes(symbols)

    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        self._ensure_connected()
        account_no = self._account_no or ""
        payload = mapping.build_place_payload(request, account_no=account_no)
        raw = self._driver.place_order(payload)
        result = mapping.map_place_result(raw, client_order_id=request.client_order_id)
        if result.sdk_order_id:
            self._remember_mapping(request.client_order_id, result.sdk_order_id)
        return result

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult:
        self._ensure_connected()
        sdk_order_id = request.sdk_order_id or self._client_to_sdk.get(request.client_order_id)
        if not sdk_order_id:
            from app.sdk.base import SDKCancelRejected

            raise SDKCancelRejected(f"缺少 sdk_order_id: {request.client_order_id}")
        raw = self._driver.cancel_order({"OrderID": sdk_order_id})
        return mapping.map_cancel_result(raw, client_order_id=request.client_order_id)

    def query_orders(self, filters: OrderQuery | dict | None = None) -> list[OrderSnapshot]:
        from app.sdk.models import coerce_order_snapshots

        q = filters if isinstance(filters, dict) else (filters.model_dump(exclude_none=True) if filters else {})
        rows = self._driver.query_orders(q or {})
        result = []
        for raw in rows:
            sdk_id = str(raw.get("OrderID") or "")
            client_id = raw.get("LocalRef") or self._resolve_client_id(sdk_id)
            result.append(mapping.map_query_order_row(raw, client_order_id=client_id))
        return coerce_order_snapshots(result)

    def query_trades(self, filters: TradeQuery | dict | None = None) -> list[TradeSnapshot]:
        from app.sdk.models import coerce_trade_snapshots

        q = filters if isinstance(filters, dict) else (filters.model_dump(exclude_none=True) if filters else {})
        rows = self._driver.query_trades(q or {})
        out = []
        for raw in rows:
            sdk_id = str(raw.get("OrderID") or "")
            client_id = raw.get("LocalRef") or self._resolve_client_id(sdk_id)
            event = mapping.map_trade_update(raw, market=self.market, client_order_id=client_id)
            out.append(event)
        return coerce_trade_snapshots(out)

    def _handle_raw_order(self, raw: dict) -> None:
        sdk_id = str(raw.get("OrderID") or "")
        client_id = self._resolve_client_id(sdk_id)
        event = mapping.map_order_update(raw, client_order_id=client_id)
        if self._on_order_update:
            self._on_order_update(event)

    def _handle_raw_trade(self, raw: dict) -> None:
        sdk_id = str(raw.get("OrderID") or "")
        client_id = self._resolve_client_id(sdk_id)
        event = mapping.map_trade_update(raw, market=self.market, client_order_id=client_id)
        if self._on_trade_update:
            self._on_trade_update(event)

    def _handle_raw_quote(self, raw: dict) -> None:
        snap = mapping.map_quote(raw, market=self.market)
        if self._on_quote_update:
            self._on_quote_update(snap)

    def _handle_raw_connection(self, raw: dict) -> None:
        self._connected = bool(raw.get("connected", False))
        if self._on_connection_change:
            self._on_connection_change(
                ConnectionEvent(
                    market=self.market,
                    connected=self._connected,
                    reason=str(raw.get("event") or raw.get("reason") or ""),
                    event_time=datetime.now(timezone.utc),
                )
            )
