"""QMT（迅投）真实交易 Broker 适配器。

QMT 通常通过本地 xtquant 包与客户端通信；本实现同时支持：
1. 直接导入 xtquant.xttrader / xtquant.xtdata（本地已安装）
2. JSON-RPC 桥接（当 QMT 客户端运行在本机其他进程时）
3. 未配置时安全降级为 SDKNotConfigured
"""

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

import httpx

from app.broker.base import Broker
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType
from app.sdk.base import SDKAuthFailed, SDKNotConfigured, SDKConnectionFailed, SDKOrderRejected
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


class QMTBroker(Broker):
    """QMT Broker 适配器。"""

    name = "qmt"
    market = Market.STOCK

    def __init__(self, config: dict | None = None):
        super().__init__()
        self.config = config or {}
        self._connected = False
        self._client_key = self.config.get("qmt_client_key", "")
        self._account_id = self.config.get("qmt_account_id", "")
        self._path = self.config.get("qmt_path", "")
        self._rpc_url = self.config.get("qmt_rpc_url", "")
        self._xt_trader = None
        self._poll_seconds = float(self.config.get("qmt_poll_seconds", 1.0))
        self._lock = threading.Lock()
        self._orders: dict[str, dict] = {}
        self._trades: list[TradeSnapshot] = []
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None

    def connect(self) -> dict:
        if self._rpc_url:
            return self._connect_rpc()
        return self._connect_native()

    def _connect_native(self) -> dict:
        try:
            from xtquant.xttrader import XtQuantTrader
        except ImportError as exc:
            raise SDKNotConfigured("xtquant 包未安装，无法直连 QMT") from exc

        if not self._path or not self._client_key:
            raise SDKNotConfigured("QMT 本地连接需要配置 qmt_path 与 qmt_client_key")

        try:
            self._xt_trader = XtQuantTrader(self._path, self._client_key)
            # 简单连接验证
            self._xt_trader.start()
            connect_result = self._xt_trader.connect()
            if connect_result != 0:
                raise SDKConnectionFailed(f"QMT 连接失败，返回码: {connect_result}")
        except Exception as exc:
            raise SDKConnectionFailed(f"QMT 连接异常: {exc}") from exc

        self._connected = True
        self._start_polling()
        self._emit_connection_change(True)
        return {"connected": True, "broker": self.name, "account_id": self._account_id}

    def _connect_rpc(self) -> dict:
        try:
            resp = httpx.get(f"{self._rpc_url}/health", timeout=5.0)
            resp.raise_for_status()
        except Exception as exc:
            raise SDKConnectionFailed(f"QMT RPC 连接失败: {exc}") from exc

        self._connected = True
        self._start_polling()
        self._emit_connection_change(True)
        return {"connected": True, "broker": self.name, "mode": "rpc", "account_id": self._account_id}

    def disconnect(self) -> None:
        self._stop_polling()
        if self._xt_trader is not None:
            try:
                self._xt_trader.disconnect()
            except Exception:
                pass
        self._connected = False
        self._emit_connection_change(False, "disconnect")

    def is_connected(self) -> bool:
        return self._connected

    def get_account(self) -> AccountSnapshot:
        self._ensure_connected()
        if self._rpc_url:
            data = self._rpc_call("get_account", {"account_id": self._account_id})
            return AccountSnapshot.model_validate(data)

        # native: xtquant 查询总资产
        from xtquant.xttrader import XtQuantTrader
        total = Decimal(str(self._xt_trader.query_stock_asset(self._account_id).m_dBalance))
        return AccountSnapshot(
            account_id=uuid.uuid4(),
            account_no=self._account_id,
            total_asset=total,
            available_cash=Decimal(str(self._xt_trader.query_stock_asset(self._account_id).m_dAvailableCash)),
            frozen_cash=Decimal("0"),
            market_value=Decimal(str(self._xt_trader.query_stock_asset(self._account_id).m_dMarketValue)),
            pnl=Decimal("0"),
            snapshot_time=datetime.now(timezone.utc),
        )

    def get_positions(self) -> list[PositionSnapshot]:
        self._ensure_connected()
        if self._rpc_url:
            rows = self._rpc_call("get_positions", {"account_id": self._account_id})
            return [PositionSnapshot.model_validate(r) for r in rows]

        try:
            from xtquant.xttrader import XtQuantTrader
            positions = self._xt_trader.query_stock_positions(self._account_id)
        except Exception as exc:
            raise SDKConnectionFailed(f"QMT 查询持仓失败: {exc}") from exc

        out: list[PositionSnapshot] = []
        for pos in positions:
            out.append(
                PositionSnapshot(
                    account_id=uuid.uuid4(),
                    symbol=str(pos.stock_code),
                    market=self.market,
                    direction="net",
                    quantity=Decimal(str(pos.volume)),
                    available_quantity=Decimal(str(pos.can_use_volume)),
                    avg_cost=Decimal(str(pos.open_price)),
                    market_value=Decimal(str(pos.market_value)),
                    pnl=Decimal(str(pos.floating_profit)),
                    snapshot_time=datetime.now(timezone.utc),
                )
            )
        return out

    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        self._ensure_connected()
        order_type = 50 if request.price_type == PriceType.MARKET else 23  # QMT 常用枚举
        price = float(request.price) if request.price else 0.0
        qty = int(request.quantity)

        if self._rpc_url:
            data = self._rpc_call(
                "place_order",
                {
                    "account_id": self._account_id,
                    "stock_code": request.symbol,
                    "order_type": order_type,
                    "order_volume": qty,
                    "price": price,
                    "client_order_id": request.client_order_id,
                },
            )
            return PlaceOrderResult.model_validate(data)

        try:
            from xtquant.xttrader import XtQuantTrader
            seq = self._xt_trader.order_stock(
                self._account_id,
                request.symbol,
                23 if request.side == OrderSide.BUY else 24,
                order_type,
                qty,
                price,
                request.client_order_id,
                "",
                "",
            )
        except Exception as exc:
            raise SDKOrderRejected(f"QMT 下单失败: {exc}") from exc

        return PlaceOrderResult(
            success=True,
            client_order_id=request.client_order_id,
            sdk_order_id=str(seq),
            status=OrderStatus.SUBMITTED,
            message="QMT 已接受委托",
        )

    def cancel_order(self, request: CancelOrderRequest) -> CancelOrderResult:
        self._ensure_connected()
        if self._rpc_url:
            data = self._rpc_call(
                "cancel_order",
                {
                    "account_id": self._account_id,
                    "sdk_order_id": request.sdk_order_id,
                    "client_order_id": request.client_order_id,
                },
            )
            return CancelOrderResult.model_validate(data)

        try:
            from xtquant.xttrader import XtQuantTrader
            self._xt_trader.cancel_order_stock(self._account_id, request.sdk_order_id)
        except Exception as exc:
            raise SDKOrderRejected(f"QMT 撤单失败: {exc}") from exc

        return CancelOrderResult(
            success=True,
            client_order_id=request.client_order_id,
            sdk_order_id=request.sdk_order_id,
            status=OrderStatus.CANCELLED,
            message="QMT 撤单已提交",
        )

    def query_orders(self, request: OrderQuery | None = None) -> list[OrderSnapshot]:
        self._ensure_connected()
        if self._rpc_url:
            rows = self._rpc_call("query_orders", {"account_id": self._account_id})
            return [OrderSnapshot.model_validate(r) for r in rows]
        return []

    def query_trades(self, request: TradeQuery | None = None) -> list[TradeSnapshot]:
        self._ensure_connected()
        if self._rpc_url:
            rows = self._rpc_call("query_trades", {"account_id": self._account_id})
            return [TradeSnapshot.model_validate(r) for r in rows]
        return []

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise SDKConnectionFailed("QMT 未连接")

    def _rpc_call(self, method: str, params: dict) -> dict | list:
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": str(uuid.uuid4())}
        try:
            resp = httpx.post(f"{self._rpc_url}/rpc", json=payload, timeout=10.0)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            raise SDKConnectionFailed(f"QMT RPC 调用失败: {exc}") from exc

        if "error" in body and body["error"]:
            raise SDKOrderRejected(f"QMT RPC 错误: {body['error']}")
        return body.get("result", {})

    def _start_polling(self) -> None:
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _stop_polling(self) -> None:
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set() and self._connected:
            try:
                if self._rpc_url:
                    self._sync_rpc_orders()
            except Exception:
                pass
            time.sleep(self._poll_seconds)

    def _sync_rpc_orders(self) -> None:
        """RPC 模式下轮询订单/成交状态。"""
        orders = self.query_orders()
        for o in orders:
            self._orders[o.client_order_id or o.sdk_order_id] = o
        trades = self.query_trades()
        for t in trades:
            if t not in self._trades:
                self._trades.append(t)
                if self._on_trade_update:
                    self._on_trade_update(
                        TradeUpdateEvent(
                            sdk_trade_id=t.sdk_trade_id,
                            client_order_id=t.client_order_id,
                            sdk_order_id=t.sdk_order_id,
                            symbol=t.symbol,
                            market=t.market or self.market,
                            side=t.side,
                            price=t.price,
                            quantity=t.quantity,
                            trade_time=t.trade_time or datetime.now(timezone.utc),
                        )
                    )

    def _emit_connection_change(self, connected: bool, reason: str = "") -> None:
        if self._on_connection_change:
            self._on_connection_change(
                ConnectionEvent(
                    market=self.market,
                    connected=connected,
                    reason=reason,
                    event_time=datetime.now(timezone.utc),
                )
            )
