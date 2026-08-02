"""Tushare Pro 行情适配器。

依赖 tushare 包；未安装或未配置 token 时抛出 SDKNotConfigured。
"""

import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from app.core.time import market_time_as_utc
from app.schemas.enums import Market
from app.sdk.base import SDKAuthFailed, SDKConnectionFailed, SDKNotConfigured, SDKResponseInvalid
from app.sdk.market_data.base import MarketDataAdapter
from app.sdk.models import KlineBar, QuoteSnapshot
from app.sdk.normalization import percentage_points_to_ratio


class TushareProAdapter(MarketDataAdapter):
    """Tushare Pro 数据接口适配器。

    支持功能：
    - 股票/期货快照（daily_basic / futures_daily 等）
    - 历史 K 线（pro.daily / pro.min）
    - 基于轮询的订阅推送
    """

    name = "tushare_pro"

    def __init__(self, *, market: Market, config: dict | None = None):
        super().__init__(market=market, config=config)
        self._token = ""
        self._pro = None
        self._subscribed: set[str] = set()
        self._quote_thread: threading.Thread | None = None
        self._quote_stop = threading.Event()
        self._lock = threading.Lock()
        self._poll_seconds = float(self.config.get("tushare_poll_seconds", 10.0))

    def connect(self) -> dict:
        try:
            import tushare as ts
        except ImportError as exc:
            raise SDKNotConfigured("tushare 包未安装") from exc

        self._token = self._require_config("tushare_token")
        try:
            self._pro = ts.pro_api(self._token)
            # 用简单接口验证 token 是否有效
            self._pro.trade_cal(exchange="SSE", limit=1)
        except Exception as exc:
            raise SDKAuthFailed(f"Tushare Pro 鉴权失败: {exc}") from exc

        self._connected = True
        self._emit_connection_change(True)
        return {"connected": True, "provider": self.name, "latency_ms": int(self._poll_seconds * 1000)}

    def disconnect(self) -> None:
        self._quote_stop.set()
        if self._quote_thread and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=2.0)
            self._quote_thread = None
        self._connected = False
        self._emit_connection_change(False, "disconnect")

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self._ensure_connected()
        ts_code = self._to_ts_code(symbol)
        try:
            if self.market == Market.FUTURES:
                query = getattr(self._pro, "fut_daily", None) or getattr(
                    self._pro, "futures_daily"
                )
                df = query(ts_code=ts_code, limit=1)
            else:
                df = self._pro.daily(ts_code=ts_code, limit=1)
        except Exception as exc:
            raise SDKConnectionFailed(f"Tushare 获取 {symbol} 行情失败: {exc}") from exc

        if df is None or df.empty:
            raise SDKResponseInvalid(f"Tushare 返回 {symbol} 为空")
        return self._df_to_quote(df.iloc[0], symbol)

    def get_kline(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[KlineBar]:
        self._ensure_connected()
        ts_code = self._to_ts_code(symbol)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        try:
            if self.market == Market.FUTURES:
                if interval in ("1m", "5m"):
                    freq = "1min" if interval == "1m" else "5min"
                    df = self._pro.futures_min(
                        ts_code=ts_code,
                        freq=freq,
                        start_date=start_str,
                        end_date=end_str,
                    )
                else:
                    query = getattr(self._pro, "fut_daily", None) or getattr(
                        self._pro, "futures_daily"
                    )
                    df = query(ts_code=ts_code, start_date=start_str, end_date=end_str)
            else:
                if interval in ("1m", "5m"):
                    freq = "1min" if interval == "1m" else "5min"
                    df = self._pro.stk_mins(
                        ts_code=ts_code,
                        freq=freq,
                        start_date=start_str,
                        end_date=end_str,
                    )
                else:
                    df = self._pro.daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
        except Exception as exc:
            raise SDKConnectionFailed(f"Tushare 获取 {symbol} K线失败: {exc}") from exc

        return self._df_to_bars(df, symbol, interval)

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._ensure_connected()
        with self._lock:
            self._subscribed.update(symbols)
        if self._quote_thread is None or not self._quote_thread.is_alive():
            self._quote_stop.clear()
            self._quote_thread = threading.Thread(target=self._quote_loop, daemon=True)
            self._quote_thread.start()

    def unsubscribe_quotes(self, symbols: list[str]) -> None:
        with self._lock:
            for symbol in symbols:
                self._subscribed.discard(symbol)

    def _quote_loop(self) -> None:
        while not self._quote_stop.is_set() and self._connected:
            with self._lock:
                symbols = list(self._subscribed)
            for symbol in symbols:
                try:
                    snap = self.get_quote(symbol)
                    self._emit_quote(snap)
                except Exception:
                    # 单个标的失败不中断循环
                    pass
            time.sleep(self._poll_seconds)

    def _ensure_connected(self) -> None:
        if not self._connected or self._pro is None:
            raise SDKConnectionFailed("Tushare Pro 适配器未连接")

    @staticmethod
    def _to_ts_code(symbol: str) -> str:
        """转换为 Tushare ts_code，并兼容 iFinD 常见期货后缀。"""
        if "." not in symbol:
            return symbol
        bare, exchange = symbol.rsplit(".", 1)
        exchange_map = {
            "CFE": "CFX",
            "GFE": "GFEX",
        }
        return f"{bare}.{exchange_map.get(exchange.upper(), exchange.upper())}"

    @staticmethod
    def _safe_decimal(value, default: str = "0") -> Decimal:
        if pd.isna(value):
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    def _df_to_quote(self, row: pd.Series, symbol: str) -> QuoteSnapshot:
        # Tushare daily 列名：open/high/low/close/vol/amount
        return QuoteSnapshot(
            symbol=symbol,
            market=self.market,
            last_price=self._safe_decimal(row.get("close") or row.get("last")),
            change_rate=percentage_points_to_ratio(
                self._safe_decimal(row.get("pct_chg") or row.get("change_rate"))
            ),
            volume=self._safe_decimal(row.get("vol") or row.get("volume"), "0"),
            quote_time=datetime.now(timezone.utc),
            raw_payload=row.to_dict(),
        )

    def _df_to_bars(self, df: pd.DataFrame | None, symbol: str, interval: str) -> list[KlineBar]:
        if df is None or df.empty:
            return []
        bars: list[KlineBar] = []
        time_col = "trade_time" if "trade_time" in df.columns else "trade_date"
        for _, row in df.iterrows():
            try:
                bar_time = market_time_as_utc(
                    pd.to_datetime(str(row.get(time_col))).to_pydatetime()
                )
                bars.append(
                    KlineBar(
                        symbol=symbol,
                        market=self.market,
                        interval=interval,
                        bar_time=bar_time,
                        open=self._safe_decimal(row.get("open")),
                        high=self._safe_decimal(row.get("high")),
                        low=self._safe_decimal(row.get("low")),
                        close=self._safe_decimal(row.get("close")),
                        volume=self._safe_decimal(row.get("vol") or row.get("volume"), "0"),
                        raw_payload=row.to_dict(),
                    )
                )
            except Exception:
                continue
        return bars
