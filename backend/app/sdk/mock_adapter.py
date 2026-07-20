import random
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.base import SDKDisconnected, SDKOrderRejected, TradingAdapter
from app.sdk.models import (
    AccountSnapshot,
    AdapterStatus,
    CancelOrderRequest,
    CancelOrderResult,
    ConnectionEvent,
    KlineBar,
    OrderUpdateEvent,
    PlaceOrderRequest,
    PlaceOrderResult,
    QuoteSnapshot,
    TradeUpdateEvent,
)


class MockTradingAdapter(TradingAdapter):
    """Mock 适配器：行情用 daemon Thread 推送，成交模拟用 Thread+sleep。"""

    def __init__(self, *, market: Market, config: dict | None = None):
        super().__init__()
        self.market = market
        self.config = config or {}
        self._connected = False
        self._subscribed: set[str] = set()
        self._latest_quotes: dict[str, QuoteSnapshot] = {}
        self._orders: dict[str, dict] = {}
        self._sdk_order_map: dict[str, str] = {}
        self._trades_seen: set[str] = set()
        self._quote_thread: threading.Thread | None = None
        self._quote_stop = threading.Event()
        self._inject_fail = False
        self._inject_disconnect = False
        self._latency_ms = self.config.get("latency_ms", 50)
        self._lock = threading.Lock()

    def connect(self) -> AdapterStatus:
        if self._inject_disconnect:
            raise SDKDisconnected("Mock 注入断线")
        self._connected = True
        status = AdapterStatus(
            connected=True,
            account_no=f"MOCK_{self.market.value.upper()}",
            latency_ms=self._latency_ms,
        )
        if self._on_connection_change:
            self._on_connection_change(
                ConnectionEvent(
                    market=self.market,
                    connected=True,
                    event_time=datetime.now(timezone.utc),
                )
            )
        return status

    def disconnect(self) -> None:
        self.stop_quotes()
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

    def subscribe_quotes(self, symbols: list[str]) -> None:
        if not self._connected:
            raise SDKDisconnected("Mock 未连接")
        with self._lock:
            self._subscribed.update(symbols)
        if self._quote_thread is None or not self._quote_thread.is_alive():
            self._quote_stop.clear()
            self._quote_thread = threading.Thread(target=self._quote_loop, daemon=True)
            self._quote_thread.start()

    def stop_quotes(self) -> None:
        """测试辅助：停止行情推送线程。"""
        self._quote_stop.set()
        if self._quote_thread is not None:
            self._quote_thread.join(timeout=2.0)
            self._quote_thread = None

    def _quote_loop(self) -> None:
        base_prices: dict[str, Decimal] = {}
        default_price = Decimal("10.00") if self.market == Market.STOCK else Decimal("3500.00")
        while not self._quote_stop.is_set() and self._connected:
            with self._lock:
                symbols = list(self._subscribed)
            for symbol in symbols:
                if symbol not in base_prices:
                    base_prices[symbol] = default_price
                delta = Decimal(str(random.uniform(-0.05, 0.05)))
                base_prices[symbol] = max(Decimal("0.01"), base_prices[symbol] + delta)
                price = base_prices[symbol].quantize(Decimal("0.01"))
                spread = Decimal("0.01")
                snap = QuoteSnapshot(
                    symbol=symbol,
                    market=self.market,
                    last_price=price,
                    change_rate=Decimal(str(random.uniform(-0.02, 0.02))).quantize(Decimal("0.000001")),
                    volume=Decimal(str(random.randint(1000, 50000))),
                    bid_price=price - spread,
                    ask_price=price + spread,
                    bid_volume=Decimal("100"),
                    ask_volume=Decimal("100"),
                    quote_time=datetime.now(timezone.utc),
                )
                with self._lock:
                    self._latest_quotes[symbol] = snap
                if self._on_quote_update:
                    self._on_quote_update(snap)
            time.sleep(0.5)

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        if not self._connected:
            raise SDKDisconnected("Mock 未连接")
        with self._lock:
            if symbol in self._latest_quotes:
                return self._latest_quotes[symbol]
        default_price = Decimal("10.00") if self.market == Market.STOCK else Decimal("3500.00")
        return QuoteSnapshot(
            symbol=symbol,
            market=self.market,
            last_price=default_price,
            quote_time=datetime.now(timezone.utc),
        )

    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        if not self._connected:
            raise SDKDisconnected("Mock 未连接")
        step_map = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "1d": timedelta(days=1),
        }
        step = step_map.get(interval, timedelta(minutes=1))
        bars: list[KlineBar] = []
        t = start
        price = Decimal("10.00") if self.market == Market.STOCK else Decimal("3500.00")
        max_bars = 2000
        while t < end and len(bars) < max_bars:
            bars.append(
                KlineBar(
                    symbol=symbol,
                    market=self.market,
                    interval=interval,
                    bar_time=t,
                    open=price,
                    high=price + Decimal("0.1"),
                    low=price - Decimal("0.1"),
                    close=price,
                    volume=Decimal("10000"),
                )
            )
            t += step
        return bars

    def get_account(self) -> AccountSnapshot:
        if not self._connected:
            raise SDKDisconnected("Mock 未连接")
        return AccountSnapshot(
            account_id=uuid4(),
            account_no=f"MOCK_{self.market.value.upper()}",
            total_asset=Decimal("1000000"),
            available_cash=Decimal("800000"),
            frozen_cash=Decimal("50000"),
            market_value=Decimal("150000"),
            pnl=Decimal("0"),
            snapshot_time=datetime.now(timezone.utc),
        )

    def get_positions(self) -> list:
        return []

    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if not self._connected:
            raise SDKDisconnected("Mock 未连接")
        if self._inject_fail:
            self._inject_fail = False
            raise SDKOrderRejected("Mock 注入下单失败")

        sdk_order_id = f"MOCK_{int(time.time() * 1000)}_{random.randint(100, 999)}"
        with self._lock:
            self._orders[request.client_order_id] = {
                "sdk_order_id": sdk_order_id,
                "status": OrderStatus.SUBMITTED,
                "filled": Decimal("0"),
                "remaining": request.quantity,
                "symbol": request.symbol,
                "side": request.side,
            }
            self._sdk_order_map[sdk_order_id] = request.client_order_id

        threading.Thread(
            target=self._simulate_fill,
            args=(request.client_order_id, sdk_order_id, request.quantity, request.symbol, request.side),
            daemon=True,
        ).start()

        return PlaceOrderResult(
            success=True,
            client_order_id=request.client_order_id,
            sdk_order_id=sdk_order_id,
            status=OrderStatus.SUBMITTED,
            message="Mock 接受委托",
        )

    def _simulate_fill(
        self,
        client_order_id: str,
        sdk_order_id: str,
        quantity: Decimal,
        symbol: str,
        side: OrderSide,
    ) -> None:
        time.sleep(0.2)
        partial = (quantity * Decimal("0.5")).quantize(Decimal("1"))
        if partial <= 0:
            partial = quantity
        self._emit_trade(sdk_order_id, client_order_id, partial, Decimal("10.05"), symbol, side)
        self._emit_order_update(client_order_id, sdk_order_id, OrderStatus.PARTIALLY_FILLED, partial, quantity - partial)
        if quantity > partial:
            time.sleep(0.2)
            rest = quantity - partial
            self._emit_trade(sdk_order_id, client_order_id, rest, Decimal("10.06"), symbol, side)
            self._emit_order_update(client_order_id, sdk_order_id, OrderStatus.FILLED, quantity, Decimal("0"))
        else:
            self._emit_order_update(client_order_id, sdk_order_id, OrderStatus.FILLED, quantity, Decimal("0"))

    def _emit_trade(
        self,
        sdk_order_id: str,
        client_order_id: str,
        qty: Decimal,
        price: Decimal,
        symbol: str,
        side: OrderSide,
    ) -> None:
        sdk_trade_id = f"MOCKT_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        with self._lock:
            if sdk_trade_id in self._trades_seen:
                return
            self._trades_seen.add(sdk_trade_id)
        if self._on_trade_update:
            self._on_trade_update(
                TradeUpdateEvent(
                    sdk_trade_id=sdk_trade_id,
                    client_order_id=client_order_id,
                    sdk_order_id=sdk_order_id,
                    symbol=symbol,
                    market=self.market,
                    side=side,
                    price=price,
                    quantity=qty,
                    trade_time=datetime.now(timezone.utc),
                )
            )

    def _emit_order_update(
        self,
        client_order_id: str,
        sdk_order_id: str,
        status: OrderStatus,
        filled: Decimal,
        remaining: Decimal,
    ) -> None:
        with self._lock:
            order = self._orders.get(client_order_id)
            if order:
                order["status"] = status
                order["filled"] = filled
                order["remaining"] = remaining
        if self._on_order_update:
            self._on_order_update(
                OrderUpdateEvent(
                    client_order_id=client_order_id,
                    sdk_order_id=sdk_order_id,
                    status=status,
                    filled_quantity=filled,
                    remaining_quantity=remaining,
                    event_time=datetime.now(timezone.utc),
                )
            )

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult:
        if not self._connected:
            raise SDKDisconnected("Mock 未连接")
        with self._lock:
            order = self._orders.get(request.client_order_id)
            if not order:
                raise SDKOrderRejected(f"Mock 未找到订单 {request.client_order_id}")
            order["status"] = OrderStatus.CANCELLED
            sdk_order_id = order.get("sdk_order_id") or request.sdk_order_id
        return CancelOrderResult(
            success=True,
            client_order_id=request.client_order_id,
            sdk_order_id=sdk_order_id,
            status=OrderStatus.CANCELLED,
            message="Mock 撤单成功",
        )

    def query_orders(self, filters: dict) -> list[dict]:
        with self._lock:
            rows = []
            for client_order_id, order in self._orders.items():
                rows.append(
                    {
                        "client_order_id": client_order_id,
                        "sdk_order_id": order.get("sdk_order_id"),
                        "status": order.get("status"),
                        "filled": str(order.get("filled", "0")),
                        "filled_quantity": str(order.get("filled", "0")),
                        "remaining_quantity": str(order.get("remaining", "0")),
                    }
                )
            return rows

    def query_trades(self, filters: dict) -> list[dict]:
        return []

    def inject_next_order_fail(self) -> None:
        self._inject_fail = True

    def inject_disconnect(self) -> None:
        self._inject_disconnect = True
        self._connected = False
        self.stop_quotes()

    def clear_inject_disconnect(self) -> None:
        """测试辅助：清除断线注入，允许重新 connect。"""
        self._inject_disconnect = False

    def inject_unknown_status(self, client_order_id: str, raw_status: str = "SDK_STATUS_XYZ") -> None:
        """测试辅助：将订单状态改为 SDK 无法映射的原始码。"""
        with self._lock:
            order = self._orders.get(client_order_id)
            if order is not None:
                order["status"] = raw_status
