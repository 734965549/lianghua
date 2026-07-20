"""Simulated 同花顺驱动：返回类 SDK 原始字段，用于映射与双通道测试。"""

import random
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from app.schemas.enums import Market
from app.sdk.base import SDKDisconnected, SDKOrderRejected


class SimulatedThsDriver:
    """模拟同花顺原始 API 字段（与标准模型不同）。"""

    def __init__(self, *, market: Market, config: dict):
        self.market = market
        self.config = config
        acct_key = "stock_account" if market == Market.STOCK else "futures_account"
        self.account_no = (config.get(acct_key) or f"SIM_{market.value.upper()}_001").strip()
        self._connected = False
        self._subscribed: set[str] = set()
        self._quotes: dict[str, dict] = {}
        self._orders: dict[str, dict] = {}  # sdk_order_id -> raw order
        self._client_map: dict[str, str] = {}  # client_order_id -> sdk_order_id
        self._trades: list[dict] = []
        self._trades_seen: set[str] = set()
        self._lock = threading.Lock()
        self._quote_thread: threading.Thread | None = None
        self._quote_stop = threading.Event()
        self._on_order: Callable[[dict], None] | None = None
        self._on_trade: Callable[[dict], None] | None = None
        self._on_quote: Callable[[dict], None] | None = None
        self._on_connection: Callable[[dict], None] | None = None
        self._inject_fail = False

    def set_order_callback(self, cb: Callable[[dict], None] | None) -> None:
        self._on_order = cb

    def set_trade_callback(self, cb: Callable[[dict], None] | None) -> None:
        self._on_trade = cb

    def set_quote_callback(self, cb: Callable[[dict], None] | None) -> None:
        self._on_quote = cb

    def set_connection_callback(self, cb: Callable[[dict], None] | None) -> None:
        self._on_connection = cb

    def connect(self) -> dict:
        self._connected = True
        payload = {
            "connected": True,
            "AcctNo": self.account_no,
            "latency_ms": self.config.get("latency_ms", 20),
        }
        if self._on_connection:
            self._on_connection({**payload, "event": "connected"})
        return payload

    def disconnect(self) -> None:
        self._quote_stop.set()
        if self._quote_thread and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=2.0)
        self._quote_thread = None
        self._connected = False
        if self._on_connection:
            self._on_connection(
                {"connected": False, "AcctNo": self.account_no, "event": "disconnected"}
            )

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise SDKDisconnected("Simulated THS 未连接")

    def get_account(self) -> dict:
        self._ensure_connected()
        return {
            "AcctNo": self.account_no,
            "TotalAsset": "1000000.00",
            "AvailCash": "800000.00",
            "FrozenCash": "50000.00",
            "MktValue": "150000.00",
            "Pnl": "0.00",
        }

    def get_positions(self) -> list[dict]:
        self._ensure_connected()
        if self.market == Market.STOCK:
            return [
                {
                    "Symbol": "600000.SH",
                    "Qty": "1000",
                    "AvailQty": "1000",
                    "AvgCost": "10.50",
                    "MktValue": "10500.00",
                    "Pnl": "500.00",
                    "Direction": "L",
                }
            ]
        return [
            {
                "Symbol": "IF2509",
                "Qty": "2",
                "AvailQty": "2",
                "AvgCost": "3500.00",
                "MktValue": "700000.00",
                "Pnl": "0.00",
                "Direction": "L",
                "OffsetFlag": "O",
            }
        ]

    def get_quote(self, symbol: str) -> dict:
        self._ensure_connected()
        with self._lock:
            if symbol in self._quotes:
                return dict(self._quotes[symbol])
        default = "10.00" if self.market == Market.STOCK else "3500.00"
        return {
            "Symbol": symbol,
            "LastPrice": default,
            "ChangeRate": "0.001",
            "Volume": "10000",
            "BidPrice": str(Decimal(default) - Decimal("0.01")),
            "AskPrice": str(Decimal(default) + Decimal("0.01")),
            "BidVol": "100",
            "AskVol": "100",
            "QuoteTime": datetime.now(timezone.utc).isoformat(),
        }

    def get_kline(self, symbol: str, interval: str, start, end) -> list[dict]:
        self._ensure_connected()
        step_map = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "1d": timedelta(days=1),
        }
        step = step_map.get(interval, timedelta(minutes=1))
        price = "10.00" if self.market == Market.STOCK else "3500.00"
        bars = []
        t = start
        while t < end and len(bars) < 500:
            bars.append(
                {
                    "Symbol": symbol,
                    "Interval": interval,
                    "BarTime": t.isoformat(),
                    "Open": price,
                    "High": str(Decimal(price) + Decimal("0.1")),
                    "Low": str(Decimal(price) - Decimal("0.1")),
                    "Close": price,
                    "Volume": "10000",
                }
            )
            t += step
        return bars

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._ensure_connected()
        with self._lock:
            self._subscribed.update(symbols)
        if self._quote_thread is None or not self._quote_thread.is_alive():
            self._quote_stop.clear()
            self._quote_thread = threading.Thread(target=self._quote_loop, daemon=True)
            self._quote_thread.start()

    def _quote_loop(self) -> None:
        bases: dict[str, Decimal] = {}
        default = Decimal("10.00") if self.market == Market.STOCK else Decimal("3500.00")
        while not self._quote_stop.is_set() and self._connected:
            with self._lock:
                symbols = list(self._subscribed)
            for sym in symbols:
                if sym not in bases:
                    bases[sym] = default
                bases[sym] += Decimal(str(random.uniform(-0.05, 0.05)))
                price = max(Decimal("0.01"), bases[sym]).quantize(Decimal("0.01"))
                raw = {
                    "Symbol": sym,
                    "LastPrice": str(price),
                    "ChangeRate": str(random.uniform(-0.02, 0.02)),
                    "Volume": str(random.randint(1000, 50000)),
                    "BidPrice": str(price - Decimal("0.01")),
                    "AskPrice": str(price + Decimal("0.01")),
                    "BidVol": "100",
                    "AskVol": "100",
                    "QuoteTime": datetime.now(timezone.utc).isoformat(),
                }
                with self._lock:
                    self._quotes[sym] = raw
                if self._on_quote:
                    self._on_quote(raw)
            time.sleep(0.5)

    def query_orders(self, filters: dict) -> list[dict]:
        with self._lock:
            return [dict(o) for o in self._orders.values()]

    def query_trades(self, filters: dict) -> list[dict]:
        with self._lock:
            return [dict(t) for t in self._trades]

    def place_order(self, payload: dict) -> dict:
        self._ensure_connected()
        if self._inject_fail:
            self._inject_fail = False
            raise SDKOrderRejected("Simulated THS 注入下单失败")

        sdk_order_id = f"THS_{int(time.time() * 1000)}_{random.randint(100, 999)}"
        qty = payload.get("Qty", "0")
        raw = {
            "OrderID": sdk_order_id,
            "AcctNo": self.account_no,
            "Symbol": payload.get("Symbol", ""),
            "Side": payload.get("Side", "B"),
            "OrderStatus": "0",
            "Price": payload.get("Price", "0"),
            "Qty": qty,
            "FilledQty": "0",
            "RemainQty": qty,
            "PriceType": payload.get("PriceType", "0"),
            "OffsetFlag": payload.get("OffsetFlag", "O"),
            "HedgeFlag": payload.get("HedgeFlag", "S"),
            "LocalRef": payload.get("LocalRef"),
        }
        local_ref = payload.get("LocalRef")
        with self._lock:
            self._orders[sdk_order_id] = raw
            if local_ref:
                self._client_map[str(local_ref)] = sdk_order_id

        threading.Thread(
            target=self._simulate_fill,
            args=(sdk_order_id, local_ref, qty, payload),
            daemon=True,
        ).start()

        return {
            "success": True,
            "OrderID": sdk_order_id,
            "OrderStatus": "0",
            "Msg": "Simulated THS 接受委托",
            "raw": raw,
        }

    def _simulate_fill(self, sdk_order_id: str, local_ref, qty_str: str, payload: dict) -> None:
        time.sleep(0.15)
        qty = Decimal(str(qty_str))
        partial = (qty * Decimal("0.5")).quantize(Decimal("1"))
        if partial <= 0:
            partial = qty
        symbol = payload.get("Symbol", "")
        side = payload.get("Side", "B")
        price = payload.get("Price", "10.05")

        self._emit_trade(sdk_order_id, local_ref, partial, price, symbol, side)
        self._emit_order(sdk_order_id, local_ref, "1", partial, qty - partial)

        if qty > partial:
            time.sleep(0.15)
            rest = qty - partial
            self._emit_trade(sdk_order_id, local_ref, rest, price, symbol, side)
            self._emit_order(sdk_order_id, local_ref, "2", qty, Decimal("0"))
        else:
            self._emit_order(sdk_order_id, local_ref, "2", qty, Decimal("0"))

    def _emit_trade(
        self,
        sdk_order_id: str,
        local_ref,
        qty: Decimal,
        price,
        symbol: str,
        side: str,
    ) -> None:
        trade_id = f"THST_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        with self._lock:
            if trade_id in self._trades_seen:
                return
            self._trades_seen.add(trade_id)
            raw = {
                "TradeID": trade_id,
                "OrderID": sdk_order_id,
                "LocalRef": local_ref,
                "Symbol": symbol,
                "Side": side,
                "Price": str(price),
                "Qty": str(qty),
                "Fee": "0.00",
                "TradeTime": datetime.now(timezone.utc).isoformat(),
            }
            self._trades.append(raw)
        if self._on_trade:
            self._on_trade(raw)

    def _emit_order(
        self,
        sdk_order_id: str,
        local_ref,
        status_code: str,
        filled: Decimal,
        remaining: Decimal,
    ) -> None:
        with self._lock:
            order = self._orders.get(sdk_order_id)
            if order:
                order["OrderStatus"] = status_code
                order["FilledQty"] = str(filled)
                order["RemainQty"] = str(remaining)
                raw = dict(order)
            else:
                raw = {
                    "OrderID": sdk_order_id,
                    "OrderStatus": status_code,
                    "FilledQty": str(filled),
                    "RemainQty": str(remaining),
                    "LocalRef": local_ref,
                }
        if self._on_order:
            # 模拟真实 SDK：回调通常不带 LocalRef
            cb_payload = {k: v for k, v in raw.items() if k != "LocalRef"}
            self._on_order(cb_payload)

    def cancel_order(self, payload: dict) -> dict:
        self._ensure_connected()
        sdk_order_id = payload.get("OrderID")
        if not sdk_order_id:
            raise SDKOrderRejected("缺少 OrderID")
        with self._lock:
            order = self._orders.get(sdk_order_id)
            if not order:
                raise SDKOrderRejected(f"未找到订单 {sdk_order_id}")
            order["OrderStatus"] = "3"
        if self._on_order:
            self._on_order(
                {
                    "OrderID": sdk_order_id,
                    "OrderStatus": "3",
                    "FilledQty": order.get("FilledQty", "0"),
                    "RemainQty": "0",
                }
            )
        return {
            "success": True,
            "OrderID": sdk_order_id,
            "OrderStatus": "3",
            "Msg": "Simulated THS 撤单成功",
        }

    def inject_next_order_fail(self) -> None:
        self._inject_fail = True

    def set_order_unknown_status(self, sdk_order_id: str, status_code: str = "9") -> None:
        """测试辅助：设置无法映射的 SDK 状态码。"""
        with self._lock:
            order = self._orders.get(sdk_order_id)
            if order:
                order["OrderStatus"] = status_code

    def lookup_client_order_id(self, sdk_order_id: str) -> str | None:
        with self._lock:
            for cid, oid in self._client_map.items():
                if oid == sdk_order_id:
                    return cid
        return None
