"""通达信 TdxQuant 本地 HTTP 行情适配器。"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from itertools import count
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from app.schemas.enums import Market
from app.sdk.base import (
    SDKConnectionFailed,
    SDKNotConfigured,
    SDKResponseInvalid,
)
from app.sdk.market_data.base import MarketDataAdapter
from app.sdk.models import KlineBar, QuoteSnapshot

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class TdxAdapter(MarketDataAdapter):
    """连接已开启 TQ 功能的通达信客户端本地 HTTP 服务。"""

    name = "tdx"

    def __init__(self, *, market: Market, config: dict | None = None):
        super().__init__(market=market, config=config)
        self._endpoint = str(
            self.config.get("tdx_endpoint") or "http://127.0.0.1:17709/"
        ).strip()
        endpoint_host = (urlparse(self._endpoint).hostname or "").lower()
        if endpoint_host not in {"127.0.0.1", "localhost", "::1"}:
            raise SDKNotConfigured("通达信 TQ 接口仅允许连接本机回环地址")
        self._poll_seconds = max(
            1.0, float(self.config.get("tdx_poll_seconds") or 3.0)
        )
        self._client: httpx.Client | None = None
        self._request_ids = count(1)
        self._subscribed: set[str] = set()
        self._subscription_lock = threading.Lock()
        self._quote_stop = threading.Event()
        self._quote_thread: threading.Thread | None = None

    def connect(self) -> dict:
        if self._connected:
            return {
                "connected": True,
                "provider": self.name,
                "latency_ms": round(self._poll_seconds * 1000),
            }
        self._client = httpx.Client(timeout=8.0)
        try:
            self._query_market_data(
                "600000.SH",
                interval="1d",
                count_value=1,
                fields=["Close"],
            )
        except Exception:
            self._client.close()
            self._client = None
            raise
        self._connected = True
        self._emit_connection_change(True)
        return {
            "connected": True,
            "provider": self.name,
            "latency_ms": round(self._poll_seconds * 1000),
        }

    def disconnect(self) -> None:
        self._quote_stop.set()
        if self._quote_thread and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=2.0)
        self._quote_thread = None
        if self._client is not None:
            self._client.close()
        self._client = None
        self._connected = False
        self._emit_connection_change(False, "disconnect")

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self._ensure_connected()
        data = self._query_market_data(
            symbol,
            interval="1m",
            count_value=2,
            fields=["Close", "Volume", "Date", "Time"],
        )
        closes = self._values(data, "Close")
        if not closes:
            raise SDKResponseInvalid(f"通达信未返回 {symbol} 最新行情")
        current = self._safe_decimal(closes[-1])
        previous = self._safe_decimal(closes[-2]) if len(closes) > 1 else current
        change_rate = (current - previous) / previous if previous else Decimal("0")
        dates = self._values(data, "Date")
        times = self._values(data, "Time")
        return QuoteSnapshot(
            symbol=symbol,
            market=self.market,
            last_price=current,
            change_rate=change_rate,
            volume=self._safe_decimal(self._last(data, "Volume")),
            quote_time=self._parse_time(
                dates[-1] if dates else None,
                times[-1] if times else None,
            ),
            raw_payload={
                "provider": self.name,
                "endpoint": self._endpoint,
                "data": data,
            },
        )

    def get_kline(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[KlineBar]:
        self._ensure_connected()
        data = self._query_market_data(
            symbol,
            interval=interval,
            start=start,
            end=end,
            count_value=-1,
            fields=["Open", "High", "Low", "Close", "Volume", "Date", "Time"],
        )
        closes = self._values(data, "Close")
        bars: list[KlineBar] = []
        for index in range(len(closes)):
            try:
                bars.append(
                    KlineBar(
                        symbol=symbol,
                        market=self.market,
                        interval=interval,
                        bar_time=self._parse_time(
                            self._at(data, "Date", index),
                            self._at(data, "Time", index),
                        ),
                        open=self._safe_decimal(self._at(data, "Open", index)),
                        high=self._safe_decimal(self._at(data, "High", index)),
                        low=self._safe_decimal(self._at(data, "Low", index)),
                        close=self._safe_decimal(closes[index]),
                        volume=self._safe_decimal(self._at(data, "Volume", index)),
                        raw_payload={"provider": self.name},
                    )
                )
            except Exception:
                continue
        return bars

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._ensure_connected()
        with self._subscription_lock:
            self._subscribed.update(symbols)
        if self._quote_thread is None or not self._quote_thread.is_alive():
            self._quote_stop.clear()
            self._quote_thread = threading.Thread(
                target=self._quote_loop,
                name=f"tdx-quotes-{self.market.value}",
                daemon=True,
            )
            self._quote_thread.start()

    def unsubscribe_quotes(self, symbols: list[str]) -> None:
        with self._subscription_lock:
            self._subscribed.difference_update(symbols)

    def _quote_loop(self) -> None:
        while not self._quote_stop.is_set() and self._connected:
            with self._subscription_lock:
                symbols = sorted(self._subscribed)
            for symbol in symbols:
                try:
                    self._emit_quote(self.get_quote(symbol))
                except Exception:
                    continue
            self._quote_stop.wait(self._poll_seconds)

    def _query_market_data(
        self,
        symbol: str,
        *,
        interval: str,
        count_value: int,
        fields: list[str],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "field_list": fields,
            "stock_list": [symbol],
            "period": interval,
            "count": count_value,
            "dividend_type": "none",
            "fill_data": True,
        }
        if start is not None:
            params["start_time"] = self._format_time(start, interval)
        if end is not None:
            params["end_time"] = self._format_time(end, interval)
        result = self._call("get_market_data", params)
        value = result.get("Value")
        if not isinstance(value, dict):
            raise SDKResponseInvalid("通达信 get_market_data 返回缺少 Value")
        data = value.get(symbol)
        if not isinstance(data, dict):
            raise SDKResponseInvalid(f"通达信未返回 {symbol} 行情")
        symbol_error = str(data.get("ErrorId", "0"))
        if symbol_error not in {"", "0"}:
            raise SDKResponseInvalid(
                f"通达信返回 {symbol} 错误码 {symbol_error}"
            )
        return data

    def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            raise SDKConnectionFailed("通达信 TQ 本地服务尚未连接")
        try:
            response = self._client.post(
                self._endpoint,
                json={
                    "id": next(self._request_ids),
                    "method": method,
                    "params": params,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise SDKConnectionFailed(
                "无法连接通达信 TQ 本地接口；请启动支持 TQ 的通达信客户端"
            ) from exc
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise SDKResponseInvalid("通达信 TQ 返回格式异常")
        error_id = str(result.get("ErrorId", "0"))
        if error_id not in {"", "0"}:
            message = str(
                result.get("ErrorMsg")
                or result.get("ErrorInfo")
                or f"错误码 {error_id}"
            )
            raise SDKConnectionFailed(f"通达信 TQ 请求失败：{message}")
        return result

    def _ensure_connected(self) -> None:
        if not self._connected or self._client is None:
            raise SDKConnectionFailed("通达信 TQ 行情适配器未连接")

    @staticmethod
    def _values(data: dict[str, Any], field: str) -> list[Any]:
        value = data.get(field)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return list(value.values())
        return [] if value is None else [value]

    @classmethod
    def _at(cls, data: dict[str, Any], field: str, index: int) -> Any:
        values = cls._values(data, field)
        return values[index] if index < len(values) else None

    @classmethod
    def _last(cls, data: dict[str, Any], field: str) -> Any:
        values = cls._values(data, field)
        return values[-1] if values else None

    @staticmethod
    def _safe_decimal(value: Any, default: str = "0") -> Decimal:
        if value is None or value == "":
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    @staticmethod
    def _parse_time(date_value: Any, time_value: Any) -> datetime:
        if not date_value:
            return datetime.now(timezone.utc)
        date_text = str(date_value).split(".", 1)[0].zfill(8)
        time_text = str(time_value or "0").split(".", 1)[0].zfill(6)
        try:
            return datetime.strptime(
                f"{date_text}{time_text}", "%Y%m%d%H%M%S"
            ).replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            return datetime.now(timezone.utc)

    @staticmethod
    def _format_time(value: datetime, interval: str) -> str:
        return value.strftime("%Y%m%d" if interval == "1d" else "%Y%m%d%H%M%S")
