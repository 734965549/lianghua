"""Wind 行情适配器。

依赖 WindPy 包；未安装或未配置时抛出 SDKNotConfigured。
Wind 终端通常通过本地 COM/DCOM 接口提供数据，适合机构环境。
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


class WindAdapter(MarketDataAdapter):
    """Wind 终端行情适配器。"""

    name = "wind"

    def __init__(self, *, market: Market, config: dict | None = None):
        super().__init__(market=market, config=config)
        self._w = None
        self._subscribed: set[str] = set()
        self._quote_thread: threading.Thread | None = None
        self._quote_stop = threading.Event()
        self._lock = threading.Lock()
        self._poll_seconds = float(self.config.get("wind_poll_seconds", 5.0))

    def connect(self) -> dict:
        try:
            from WindPy import w
        except ImportError as exc:
            raise SDKNotConfigured("WindPy 包未安装") from exc

        try:
            ret = w.start()
            if ret.ErrorCode != 0:
                raise SDKAuthFailed(f"Wind 启动失败: {ret.Data}")
        except Exception as exc:
            raise SDKAuthFailed(f"Wind 连接失败: {exc}") from exc

        self._w = w
        self._connected = True
        self._emit_connection_change(True)
        return {"connected": True, "provider": self.name, "latency_ms": int(self._poll_seconds * 1000)}

    def disconnect(self) -> None:
        self._quote_stop.set()
        if self._quote_thread and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=2.0)
            self._quote_thread = None
        if self._w is not None:
            try:
                self._w.stop()
            except Exception:
                pass
        self._connected = False
        self._emit_connection_change(False, "disconnect")

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self._ensure_connected()
        wind_code = self._to_wind_code(symbol)
        try:
            resp = self._w.wsq(wind_code, "rt_last,rt_pct_chg,rt_vol")
        except Exception as exc:
            raise SDKConnectionFailed(f"Wind 获取 {symbol} 行情失败: {exc}") from exc

        if resp.ErrorCode != 0 or not resp.Data:
            raise SDKResponseInvalid(f"Wind 返回 {symbol} 异常: {resp.Data}")
        data = resp.Data
        return QuoteSnapshot(
            symbol=symbol,
            market=self.market,
            last_price=self._safe_decimal(data[0][0] if len(data) > 0 else None),
            change_rate=percentage_points_to_ratio(
                self._safe_decimal(data[1][0] if len(data) > 1 else None)
            ),
            volume=self._safe_decimal(data[2][0] if len(data) > 2 else None, "0"),
            quote_time=datetime.now(timezone.utc),
            raw_payload={"wind_code": wind_code, "data": data},
        )

    def get_kline(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[KlineBar]:
        self._ensure_connected()
        wind_code = self._to_wind_code(symbol)
        # Wind 接口：bars 用 "bar_size=1" 表示分钟，"bar_size=240" 表示日线等
        bar_size = {"1m": 1, "5m": 5, "1d": 240}.get(interval, 1)
        start_str = start.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end.strftime("%Y-%m-%d %H:%M:%S")
        try:
            resp = self._w.wsi(wind_code, "open,high,low,close,volume", start_str, end_str, f"BarSize={bar_size}")
        except Exception as exc:
            raise SDKConnectionFailed(f"Wind 获取 {symbol} K线失败: {exc}") from exc

        if resp.ErrorCode != 0 or resp.Data is None:
            raise SDKResponseInvalid(f"Wind 返回 {symbol} K线异常: {resp.Data}")
        return self._wind_resp_to_bars(resp, symbol, interval)

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
        if not self._connected or self._w is None:
            raise SDKConnectionFailed("Wind 适配器未连接")

    def _to_wind_code(self, symbol: str) -> str:
        """将 600519.SH 映射为 Wind Code。

        股票：600519.SH
        期货：RB2501.SHF 等
        """
        if self.market == Market.FUTURES:
            # 简单映射，实际需按品种处理交易所后缀
            return symbol
        return symbol

    @staticmethod
    def _safe_decimal(value, default: str = "0") -> Decimal:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    def _wind_resp_to_bars(self, resp, symbol: str, interval: str) -> list[KlineBar]:
        """解析 Wind wsi/wsd 返回为 KlineBar。"""
        if not resp.Times or not resp.Data:
            return []
        times = resp.Times
        fields = resp.Fields
        data = resp.Data
        field_index = {f: i for i, f in enumerate(fields)}
        bars: list[KlineBar] = []
        for i, ts in enumerate(times):
            try:
                bar_time = market_time_as_utc(pd.to_datetime(ts).to_pydatetime())
                bars.append(
                    KlineBar(
                        symbol=symbol,
                        market=self.market,
                        interval=interval,
                        bar_time=bar_time,
                        open=self._safe_decimal(data[field_index.get("OPEN", 0)][i]),
                        high=self._safe_decimal(data[field_index.get("HIGH", 1)][i]),
                        low=self._safe_decimal(data[field_index.get("LOW", 2)][i]),
                        close=self._safe_decimal(data[field_index.get("CLOSE", 3)][i]),
                        volume=self._safe_decimal(data[field_index.get("VOLUME", 4)][i], "0"),
                    )
                )
            except Exception:
                continue
        return bars
