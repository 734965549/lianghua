"""RQData 行情适配器。

依赖 rqdatac 包；未安装或未配置账户时抛出 SDKNotConfigured。
RQData 同时覆盖股票、期货、期权等资产类别，使用统一接口。
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


class RQDataAdapter(MarketDataAdapter):
    """RQData 统一行情适配器。"""

    name = "rqdata"

    def __init__(self, *, market: Market, config: dict | None = None):
        super().__init__(market=market, config=config)
        self._username = ""
        self._password = ""
        self._rq = None
        self._subscribed: set[str] = set()
        self._quote_thread: threading.Thread | None = None
        self._quote_stop = threading.Event()
        self._lock = threading.Lock()
        self._poll_seconds = float(self.config.get("rqdata_poll_seconds", 5.0))

    def connect(self) -> dict:
        try:
            import rqdatac as rq
        except ImportError as exc:
            raise SDKNotConfigured("rqdatac 包未安装") from exc

        self._username = self._require_config("rqdata_username")
        self._password = self._require_config("rqdata_password")
        try:
            rq.init(self._username, self._password)
        except Exception as exc:
            raise SDKAuthFailed(f"RQData 鉴权失败: {exc}") from exc

        self._rq = rq
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
        order_book_id = self._to_rq_symbol(symbol)
        try:
            df = self._rq.get_price(
                order_book_id,
                frequency="1m",
                fields=["open", "high", "low", "close", "volume"],
                count=1,
            )
        except Exception as exc:
            raise SDKConnectionFailed(f"RQData 获取 {symbol} 行情失败: {exc}") from exc

        if df is None or df.empty:
            raise SDKResponseInvalid(f"RQData 返回 {symbol} 为空")
        row = df.iloc[-1]
        return QuoteSnapshot(
            symbol=symbol,
            market=self.market,
            last_price=self._safe_decimal(row.get("close")),
            change_rate=Decimal("0"),
            volume=self._safe_decimal(row.get("volume"), "0"),
            quote_time=datetime.now(timezone.utc),
            raw_payload=row.to_dict(),
        )

    def get_kline(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[KlineBar]:
        self._ensure_connected()
        order_book_id = self._to_rq_symbol(symbol)
        freq_map = {"1m": "1m", "5m": "5m", "1d": "1d"}
        freq = freq_map.get(interval, "1m")
        try:
            df = self._rq.get_price(
                order_book_id,
                start_date=start,
                end_date=end,
                frequency=freq,
                fields=["open", "high", "low", "close", "volume"],
            )
        except Exception as exc:
            raise SDKConnectionFailed(f"RQData 获取 {symbol} K线失败: {exc}") from exc

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
                    pass
            time.sleep(self._poll_seconds)

    def _ensure_connected(self) -> None:
        if not self._connected or self._rq is None:
            raise SDKConnectionFailed("RQData 适配器未连接")

    def _to_rq_symbol(self, symbol: str) -> str:
        """将 600519.SH 映射为 RQData 的 order_book_id。

        股票：600519.XSHE / 600000.XSHG
        期货：沿用 symbol（如 RB2501）
        """
        if self.market == Market.FUTURES:
            return symbol
        bare, exchange = symbol, ""
        if "." in symbol:
            bare, exchange = symbol.split(".", 1)
        exchange_map = {"SH": "XSHG", "SZ": "XSHE", "BJ": "XSHE"}
        return f"{bare}.{exchange_map.get(exchange, 'XSHE')}"

    @staticmethod
    def _safe_decimal(value, default: str = "0") -> Decimal:
        if pd.isna(value):
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    def _df_to_bars(self, df: pd.DataFrame | None, symbol: str, interval: str) -> list[KlineBar]:
        if df is None or df.empty:
            return []
        bars: list[KlineBar] = []
        for ts, row in df.iterrows():
            try:
                bar_time = market_time_as_utc(pd.to_datetime(ts).to_pydatetime())
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
                        volume=self._safe_decimal(row.get("volume"), "0"),
                        raw_payload=row.to_dict(),
                    )
                )
            except Exception:
                continue
        return bars
