"""AKShare 行情适配器：真实行情 + 程序内模拟撮合。"""

import random
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import akshare as ak
import pandas as pd

from app.schemas.enums import Market, OrderSide, OrderStatus
from app.sdk.base import SDKDisconnected, SDKOrderRejected, TradingAdapter
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
    coerce_order_query,
    coerce_order_snapshots,
    coerce_trade_query,
    coerce_trade_snapshots,
)


class AkshareAdapter(TradingAdapter):
    """真实行情（AKShare）+ 模拟撮合。"""

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
        self._trades: list[TradeSnapshot] = []
        self._positions: dict[str, PositionSnapshot] = {}
        self._quote_thread: threading.Thread | None = None
        self._quote_stop = threading.Event()
        self._poll_seconds = float(self.config.get("akshare_poll_seconds", 10.0))
        self._lock = threading.Lock()

    # ---- 生命周期 ----
    def connect(self) -> AdapterStatus:
        self._connected = True
        # 后台线程拉取全市场快照，避免阻塞启动（akshare 下载需约 2 分钟）
        threading.Thread(target=self._initial_refresh, daemon=True).start()
        if self._on_connection_change:
            self._on_connection_change(
                ConnectionEvent(
                    market=self.market,
                    connected=True,
                    event_time=datetime.now(timezone.utc),
                )
            )
        return AdapterStatus(
            connected=True,
            account_no="AKSHARE_SIM",
            latency_ms=int(self._poll_seconds * 1000),
        )

    def _initial_refresh(self) -> None:
        """后台线程：首次拉取全市场快照，建立 _latest_quotes 缓存。"""
        if self.market == Market.FUTURES:
            self._refresh_futures_snapshot()
        else:
            self._refresh_spot_snapshot()

    def disconnect(self) -> None:
        self._quote_stop.set()
        if self._quote_thread and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=2.0)
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

    # ---- 行情（真实）----
    def _refresh_spot_snapshot(self) -> None:
        """拉取全市场实时快照（新浪财经），更新 _latest_quotes 缓存。"""
        try:
            df = ak.stock_zh_a_spot()
        except Exception:
            return  # 源站波动时保留旧缓存
        
        if df is None or df.empty:
            return
        
        # 先在无锁状态下构建 batch，减少锁持有时间
        batch: dict[str, QuoteSnapshot] = {}
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).strip()
            if not code:
                continue
            symbol = self._normalize_symbol(code)
            
            last_price = self._safe_decimal(row.get("最新价"), "0")
            change_rate = self._safe_decimal(row.get("涨跌幅"), "0")
            volume = self._safe_decimal(row.get("成交量"), "0")
            
            batch[symbol] = QuoteSnapshot(
                symbol=symbol,
                market=self.market,
                last_price=last_price,
                change_rate=change_rate,
                volume=volume,
                quote_time=datetime.now(timezone.utc),
            )
        
        with self._lock:
            self._latest_quotes.update(batch)

    def _refresh_futures_snapshot(self) -> None:
        """拉取期货实时行情（新浪）。"""
        try:
            df = ak.futures_zh_spot()
        except Exception:
            return
        if df is None or df.empty:
            return
        batch: dict[str, QuoteSnapshot] = {}
        for _, row in df.iterrows():
            symbol = str(row.get("symbol", "") or row.get("代码", "")).strip()
            if not symbol:
                continue
            last_price = self._safe_decimal(row.get("current_price") or row.get("最新价"), "0")
            change_rate = self._safe_decimal(row.get("changepercent") or row.get("涨跌幅"), "0")
            volume = self._safe_decimal(row.get("volume") or row.get("成交量"), "0")
            batch[symbol] = QuoteSnapshot(
                symbol=symbol,
                market=self.market,
                last_price=last_price,
                change_rate=change_rate,
                volume=volume,
                quote_time=datetime.now(timezone.utc),
            )
        with self._lock:
            self._latest_quotes.update(batch)

    @staticmethod
    def _normalize_symbol(code: str) -> str:
        """6 位代码 -> 带后缀标准代码，如 600000 -> 600000.SH。
        
        北交所（8/4 开头）暂不支持，如需支持请映射为 .BJ。
        """
        if "." in code:
            return code
        if code.startswith(("60", "68", "11", "13")):
            return f"{code}.SH"
        return f"{code}.SZ"

    @staticmethod
    def _safe_decimal(value, default: str = "0") -> Decimal:
        """安全转换为 Decimal，处理 NaN 和异常值。"""
        if pd.isna(value):
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self._ensure_connected()
        with self._lock:
            if symbol in self._latest_quotes:
                return self._latest_quotes[symbol]
        # 缓存未命中时单点查询（按需补）
        raise SDKDisconnected(f"AKShare 暂无 {symbol} 快照")

    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        self._ensure_connected()
        if self.market == Market.FUTURES:
            return self._get_futures_kline(symbol, interval, start, end)
        return self._get_stock_kline(symbol, interval, start, end)

    def _get_stock_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        bare = symbol.split(".")[0]
        adjust = self.config.get("akshare_adjust", "qfq")

        if interval == "1d":
            if bare.startswith(("60", "68", "11", "13")):
                sina_symbol = f"sh{bare}"
            else:
                sina_symbol = f"sz{bare}"
            try:
                df = ak.stock_zh_a_daily(
                    symbol=sina_symbol,
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust=adjust,
                )
            except Exception:
                return []
            return self._df_to_bars(df, symbol, interval, date_col="date")

        if interval in ("1m", "5m"):
            period_map = {"1m": "1", "5m": "5"}
            try:
                df = ak.stock_zh_a_hist_min_em(
                    symbol=bare,
                    start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
                    period=period_map[interval],
                    adjust=adjust,
                )
            except Exception:
                return []
            return self._df_to_bars(df, symbol, interval, date_col="时间")

        return []

    def _get_futures_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        if interval == "1d":
            try:
                df = ak.futures_zh_daily_sina(symbol=symbol)
            except Exception:
                return []
            if df is None or df.empty:
                return []
            bars = self._df_to_bars(df, symbol, interval, date_col="date")
            return [b for b in bars if start <= b.bar_time <= end]

        if interval in ("1m", "5m"):
            period_map = {"1m": "1", "5m": "5"}
            try:
                df = ak.futures_zh_minute_sina(symbol=symbol, period=period_map[interval])
            except Exception:
                return []
            if df is None or df.empty:
                return []
            bars = self._df_to_bars(df, symbol, interval, date_col="datetime")
            return [b for b in bars if start <= b.bar_time <= end]

        return []

    def _df_to_bars(self, df, symbol: str, interval: str, *, date_col: str) -> list[KlineBar]:
        if df is None or df.empty:
            return []
        bars: list[KlineBar] = []
        col_map = {
            "open": ["open", "开盘", "Open"],
            "high": ["high", "最高", "High"],
            "low": ["low", "最低", "Low"],
            "close": ["close", "收盘", "Close"],
            "volume": ["volume", "成交量", "Volume"],
        }

        def pick(row, keys):
            for k in keys:
                if k in row.index:
                    return row.get(k)
            return None

        for _, row in df.iterrows():
            try:
                bar_time = pd.to_datetime(str(row.get(date_col)))
                if bar_time.tzinfo is None:
                    bar_time = bar_time.replace(tzinfo=timezone.utc)
                bars.append(
                    KlineBar(
                        symbol=symbol,
                        market=self.market,
                        interval=interval,
                        bar_time=bar_time.to_pydatetime(),
                        open=self._safe_decimal(pick(row, col_map["open"])),
                        high=self._safe_decimal(pick(row, col_map["high"])),
                        low=self._safe_decimal(pick(row, col_map["low"])),
                        close=self._safe_decimal(pick(row, col_map["close"])),
                        volume=self._safe_decimal(pick(row, col_map["volume"]), "0"),
                    )
                )
            except Exception:
                continue
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
        """行情推送循环，定期刷新全市场快照并推送订阅标的。"""
        while not self._quote_stop.is_set() and self._connected:
            if self.market == Market.FUTURES:
                self._refresh_futures_snapshot()
            else:
                self._refresh_spot_snapshot()
            with self._lock:
                snaps = [
                    self._latest_quotes[s]
                    for s in self._subscribed
                    if s in self._latest_quotes
                ]
            for snap in snaps:
                if self._on_quote_update:
                    self._on_quote_update(snap)
            time.sleep(self._poll_seconds)

    # ---- 账户/持仓（模拟）----
    def get_account(self) -> AccountSnapshot:
        self._ensure_connected()
        return AccountSnapshot(
            account_id=uuid4(),
            account_no="AKSHARE_SIM",
            total_asset=Decimal("1000000"),
            available_cash=Decimal("800000"),
            frozen_cash=Decimal("50000"),
            market_value=Decimal("150000"),
            pnl=Decimal("0"),
            snapshot_time=datetime.now(timezone.utc),
        )

    def get_positions(self) -> list:
        with self._lock:
            return list(self._positions.values())

    # ---- 交易（模拟撮合，用真实价）----
    def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        self._ensure_connected()
        
        sdk_order_id = f"AK_{int(time.time() * 1000)}_{random.randint(100, 999)}"
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

        # 异步模拟撮合
        threading.Thread(
            target=self._simulate_fill,
            args=(
                request.client_order_id,
                sdk_order_id,
                request.quantity,
                request.symbol,
                request.side,
                request,
            ),
            daemon=True,
        ).start()

        return PlaceOrderResult(
            success=True,
            client_order_id=request.client_order_id,
            sdk_order_id=sdk_order_id,
            status=OrderStatus.SUBMITTED,
            message="AKShare 模拟接受委托",
        )

    def _simulate_fill(
        self,
        client_order_id: str,
        sdk_order_id: str,
        quantity: Decimal,
        symbol: str,
        side: OrderSide,
        request: PlaceOrderRequest,
    ) -> None:
        """模拟撮合，使用真实行情价格。"""
        time.sleep(0.2)
        
        # 获取真实最新价作为成交价
        try:
            snap = self.get_quote(symbol)
            fill_price = snap.last_price
        except Exception:
            # 无法获取行情时降级为委托价
            fill_price = request.price if request.price and request.price > 0 else Decimal("10.00")
        
        # 分两次成交
        partial = (quantity * Decimal("0.5")).quantize(Decimal("1"))
        if partial <= 0:
            partial = quantity
        
        self._emit_trade(sdk_order_id, client_order_id, partial, fill_price, symbol, side)
        self._emit_order_update(
            client_order_id, sdk_order_id, OrderStatus.PARTIALLY_FILLED, partial, quantity - partial
        )
        
        if quantity > partial:
            time.sleep(0.2)
            rest = quantity - partial
            # 第二次成交价格略有变动
            fill_price2 = fill_price + Decimal("0.01")
            self._emit_trade(sdk_order_id, client_order_id, rest, fill_price2, symbol, side)
            self._emit_order_update(
                client_order_id, sdk_order_id, OrderStatus.FILLED, quantity, Decimal("0")
            )
        else:
            self._emit_order_update(
                client_order_id, sdk_order_id, OrderStatus.FILLED, quantity, Decimal("0")
            )

    def _emit_trade(
        self,
        sdk_order_id: str,
        client_order_id: str,
        qty: Decimal,
        price: Decimal,
        symbol: str,
        side: OrderSide,
    ) -> None:
        """发送成交回报，同步更新持仓。"""
        sdk_trade_id = f"AKT_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        with self._lock:
            if sdk_trade_id in self._trades_seen:
                return
            self._trades_seen.add(sdk_trade_id)
            snap = TradeSnapshot(
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
            self._trades.append(snap)

            # 更新持仓
            key = symbol
            if key in self._positions:
                pos = self._positions[key]
                if side == OrderSide.BUY:
                    new_qty = pos.quantity + qty
                    new_cost = (pos.avg_cost * pos.quantity + price * qty) / new_qty if new_qty > 0 else Decimal("0")
                    new_pnl = pos.pnl
                else:
                    new_qty = pos.quantity - qty
                    new_cost = pos.avg_cost
                    new_pnl = pos.pnl + (price - pos.avg_cost) * qty
                if new_qty <= 0:
                    del self._positions[key]
                else:
                    self._positions[key] = PositionSnapshot(
                        account_id=pos.account_id,
                        symbol=symbol,
                        market=self.market,
                        direction="net",
                        quantity=new_qty,
                        available_quantity=new_qty,
                        avg_cost=new_cost,
                        market_value=new_qty * price,
                        pnl=new_pnl,
                        snapshot_time=datetime.now(timezone.utc),
                    )
            elif side == OrderSide.BUY:
                self._positions[key] = PositionSnapshot(
                    account_id=uuid4(),
                    symbol=symbol,
                    market=self.market,
                    direction="net",
                    quantity=qty,
                    available_quantity=qty,
                    avg_cost=price,
                    market_value=qty * price,
                    pnl=Decimal("0"),
                    snapshot_time=datetime.now(timezone.utc),
                )
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
        """发送订单更新。"""
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
        self._ensure_connected()
        with self._lock:
            order = self._orders.get(request.client_order_id)
            if not order:
                raise SDKOrderRejected(f"AKShare 未找到订单 {request.client_order_id}")
            order["status"] = OrderStatus.CANCELLED
            sdk_order_id = order.get("sdk_order_id") or request.sdk_order_id
        return CancelOrderResult(
            success=True,
            client_order_id=request.client_order_id,
            sdk_order_id=sdk_order_id,
            status=OrderStatus.CANCELLED,
            message="AKShare 模拟撤单成功",
        )

    def query_orders(self, filters: OrderQuery | dict | None = None) -> list[OrderSnapshot]:
        _ = coerce_order_query(filters)
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
                        "symbol": order.get("symbol"),
                        "market": self.market,
                    }
                )
            return coerce_order_snapshots(rows)

    def query_trades(self, filters: TradeQuery | dict | None = None) -> list[TradeSnapshot]:
        q = coerce_trade_query(filters)
        with self._lock:
            rows = list(self._trades)
        if q.client_order_id:
            rows = [t for t in rows if t.client_order_id == q.client_order_id]
        if q.sdk_order_id:
            rows = [t for t in rows if t.sdk_order_id == q.sdk_order_id]
        if q.symbol:
            rows = [t for t in rows if t.symbol == q.symbol]
        if q.sdk_trade_id:
            rows = [t for t in rows if t.sdk_trade_id == q.sdk_trade_id]
        return coerce_trade_snapshots(rows)

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise SDKDisconnected("AKShare 适配器未连接")
