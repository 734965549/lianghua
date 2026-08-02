"""同花顺 iFinD 实时行情适配器。"""

from __future__ import annotations

import importlib
import re
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from app.schemas.enums import Market
from app.sdk.base import (
    SDKAuthFailed,
    SDKConnectionFailed,
    SDKNotConfigured,
    SDKResponseInvalid,
)
from app.sdk.market_data.base import MarketDataAdapter
from app.sdk.models import KlineBar, QuoteSnapshot
from app.sdk.normalization import percentage_points_to_ratio

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
REALTIME_INDICATORS = "latest;changeRatio;volume;bid1;ask1"
KLINE_INDICATORS = "open;high;low;close;volume"
STOCK_REPORT_FIELDS = "p03291_f001:Y,p03291_f002:Y,p03291_f003:Y,p03291_f004:Y"
SECURITY_LIST_FIELDS = "p00001_f001:Y,p00001_f002:Y,p00001_f005:Y,p00001_f007:Y"
FUTURES_EXCHANGES = ("CFFEX", "SHFE", "INE", "DCE", "CZCE", "GFEX")
FUTURES_SUFFIX = {
    "CFFEX": "CFE",
    "SHFE": "SHF",
    "INE": "INE",
    "DCE": "DCE",
    "CZCE": "ZCE",
    "GFEX": "GFE",
}
CODE_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:\.[A-Za-z]+)?$")


class IFindAdapter(MarketDataAdapter):
    """通过官方 iFinDPy 包轮询 iFinD 实时行情。

    iFinD 登录态在进程内共享；股票和期货适配器使用同一账号会话。
    """

    name = "ifind"

    _api_lock = threading.RLock()
    _session_refs = 0
    _session_username = ""
    _api_module = None

    def __init__(self, *, market: Market, config: dict | None = None):
        super().__init__(market=market, config=config)
        self._username = ""
        self._password = ""
        self._session_acquired = False
        self._subscribed: set[str] = set()
        self._quote_thread: threading.Thread | None = None
        self._quote_stop = threading.Event()
        self._subscription_lock = threading.Lock()
        self._poll_seconds = max(1.0, float(self.config.get("ifind_poll_seconds", 3.0)))

    @classmethod
    def component_installed(cls) -> bool:
        try:
            importlib.import_module("iFinDPy")
            return True
        except (ImportError, OSError):
            return False

    @classmethod
    def _load_api(cls):
        if cls._api_module is not None:
            return cls._api_module
        try:
            cls._api_module = importlib.import_module("iFinDPy")
        except ImportError as exc:
            raise SDKNotConfigured(
                "iFinDAPI 未安装，请在后端虚拟环境执行 pip install iFinDAPI"
            ) from exc
        except OSError as exc:
            raise SDKNotConfigured(f"iFinDAPI 本地组件加载失败: {exc}") from exc
        return cls._api_module

    def connect(self) -> dict:
        if self._connected:
            return {
                "connected": True,
                "provider": self.name,
                "latency_ms": round(self._poll_seconds * 1000),
            }

        self._username = self._require_config("ifind_username").strip()
        self._password = self._require_config("ifind_password")
        api = self._load_api()

        with self._api_lock:
            if self.__class__._session_refs:
                if self.__class__._session_username != self._username:
                    raise SDKAuthFailed("当前进程已有其他 iFinD 账号登录，请先切换行情源")
            else:
                try:
                    result = int(api.THS_iFinDLogin(self._username, self._password))
                except Exception as exc:
                    raise SDKConnectionFailed(f"iFinD 登录调用失败: {exc}") from exc
                if result not in {0, -201}:
                    message = "用户名或密码错误" if result == -2 else f"登录错误码 {result}"
                    raise SDKAuthFailed(f"iFinD 鉴权失败：{message}", raw_code=str(result))
                self.__class__._session_username = self._username

            self.__class__._session_refs += 1
            self._session_acquired = True

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

        with self._api_lock:
            if self._session_acquired:
                self.__class__._session_refs = max(0, self.__class__._session_refs - 1)
                self._session_acquired = False
                if self.__class__._session_refs == 0 and self.__class__._api_module is not None:
                    try:
                        self.__class__._api_module.THS_iFinDLogout()
                    except Exception:
                        pass
                    self.__class__._session_username = ""

        self._connected = False
        self._emit_connection_change(False, "disconnect")

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        quotes = self._query_quotes([symbol])
        if not quotes:
            raise SDKResponseInvalid(f"iFinD 未返回 {symbol} 实时行情")
        return quotes[0]

    def list_instruments(self) -> list[dict[str, Any]]:
        """从 iFinD 同步当前股票或期货合约目录。"""
        self._ensure_connected()
        api = self._load_api()
        if self.market == Market.STOCK:
            today = datetime.now(SHANGHAI_TZ).strftime("%Y%m%d")
            with self._api_lock:
                result = api.THS_DR(
                    "p03291",
                    f"date={today};blockname=001005010;iv_type=allcontract",
                    STOCK_REPORT_FIELDS,
                )
            self._raise_for_result(result, "全 A 股标的目录")
            return self._dataframe_to_instruments(result.data, market=Market.STOCK)

        records: list[dict[str, Any]] = []
        errors: list[str] = []
        for exchange in FUTURES_EXCHANGES:
            try:
                with self._api_lock:
                    result = api.THS_DR(
                        "p00001",
                        f"sclx={exchange}",
                        SECURITY_LIST_FIELDS,
                    )
                self._raise_for_result(result, f"{exchange} 期货合约目录")
                records.extend(
                    self._dataframe_to_instruments(
                        result.data,
                        market=Market.FUTURES,
                        exchange_hint=exchange,
                    )
                )
            except Exception as exc:
                errors.append(f"{exchange}: {exc}")
        unique = {item["symbol"]: item for item in records}
        if not unique:
            raise SDKResponseInvalid(
                "iFinD 未返回期货合约目录"
                + (f"（{'；'.join(errors)}）" if errors else "")
            )
        return sorted(unique.values(), key=lambda item: item["symbol"])

    def get_kline(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[KlineBar]:
        self._ensure_connected()
        api = self._load_api()
        start_local = self._format_datetime(start, with_time=interval != "1d")
        end_local = self._format_datetime(end, with_time=interval != "1d")

        try:
            with self._api_lock:
                if interval in {"1m", "5m"}:
                    minutes = "1" if interval == "1m" else "5"
                    result = api.THS_HF(
                        symbol,
                        KLINE_INDICATORS,
                        f"CPS:0,MaxPoints:50000,Fill:Previous,Interval:{minutes}",
                        start_local,
                        end_local,
                    )
                else:
                    result = api.THS_HQ(
                        symbol,
                        KLINE_INDICATORS,
                        "Period:D;CPS:0;Fill:Previous",
                        start_local,
                        end_local,
                    )
        except Exception as exc:
            raise SDKConnectionFailed(f"iFinD 获取 {symbol} K 线失败: {exc}") from exc

        self._raise_for_result(result, f"{symbol} K 线")
        return self._dataframe_to_bars(result.data, symbol, interval)

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._ensure_connected()
        with self._subscription_lock:
            self._subscribed.update(symbols)
        if self._quote_thread is None or not self._quote_thread.is_alive():
            self._quote_stop.clear()
            self._quote_thread = threading.Thread(
                target=self._quote_loop,
                name=f"ifind-quotes-{self.market.value}",
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
            for offset in range(0, len(symbols), 50):
                try:
                    for quote in self._query_quotes(symbols[offset : offset + 50]):
                        self._emit_quote(quote)
                except Exception:
                    # 单批失败不终止订阅线程，下一个轮询周期继续尝试。
                    continue
            self._quote_stop.wait(self._poll_seconds)

    def _query_quotes(self, symbols: list[str]) -> list[QuoteSnapshot]:
        self._ensure_connected()
        if not symbols:
            return []
        api = self._load_api()
        try:
            with self._api_lock:
                result = api.THS_RQ(",".join(symbols), REALTIME_INDICATORS)
        except Exception as exc:
            raise SDKConnectionFailed(f"iFinD 实时行情调用失败: {exc}") from exc

        self._raise_for_result(result, "实时行情")
        return self._dataframe_to_quotes(result, symbols)

    @staticmethod
    def _raise_for_result(result, label: str) -> None:
        if result is None:
            raise SDKResponseInvalid(f"iFinD {label}返回为空")
        error_code = int(getattr(result, "errorcode", -1))
        if error_code != 0:
            message = str(getattr(result, "errmsg", "") or "未知错误")
            raise SDKConnectionFailed(
                f"iFinD {label}失败: {message}",
                raw_code=str(error_code),
                raw_message=message,
            )
        data = getattr(result, "data", None)
        if data is None or not isinstance(data, pd.DataFrame) or data.empty:
            raise SDKResponseInvalid(f"iFinD {label}没有数据")

    def _dataframe_to_quotes(self, result, requested_symbols: list[str]) -> list[QuoteSnapshot]:
        df = result.data
        columns = {str(col).strip().lower(): col for col in df.columns}
        code_col = columns.get("thscode") or columns.get("code")
        time_col = columns.get("time") or columns.get("datetime")
        price_col = columns.get("latest") or columns.get("new")
        change_col = columns.get("changeratio") or columns.get("change_rate")
        volume_col = columns.get("volume") or columns.get("latestvolume")
        bid_col = columns.get("bid1") or columns.get("bidprice1")
        ask_col = columns.get("ask1") or columns.get("askprice1")

        quotes: list[QuoteSnapshot] = []
        result_codes = list(getattr(result, "thscode", []) or [])
        result_times = list(getattr(result, "time", []) or [])
        for index, (_, row) in enumerate(df.iterrows()):
            symbol = str(row.get(code_col) if code_col else "").strip()
            if not symbol:
                symbol = result_codes[index] if index < len(result_codes) else ""
            if not symbol and len(requested_symbols) == 1:
                symbol = requested_symbols[0]
            if not symbol:
                continue

            raw_time = row.get(time_col) if time_col else None
            if raw_time is None and index < len(result_times):
                raw_time = result_times[index]
            quotes.append(
                QuoteSnapshot(
                    symbol=symbol,
                    market=self.market,
                    last_price=self._safe_decimal(row.get(price_col) if price_col else None),
                    change_rate=percentage_points_to_ratio(
                        self._safe_decimal(
                            row.get(change_col) if change_col else None
                        )
                    ),
                    volume=self._safe_decimal(row.get(volume_col) if volume_col else None),
                    bid_price=self._safe_decimal(
                        row.get(bid_col) if bid_col else None
                    ),
                    ask_price=self._safe_decimal(
                        row.get(ask_col) if ask_col else None
                    ),
                    quote_time=self._parse_time(raw_time),
                    raw_payload=self._safe_payload(row.to_dict()),
                )
            )
        return quotes

    @classmethod
    def _dataframe_to_instruments(
        cls,
        df: pd.DataFrame,
        *,
        market: Market,
        exchange_hint: str = "",
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            values = [str(value).strip() for value in row.tolist() if not pd.isna(value)]
            symbol = cls._find_instrument_code(values, market, exchange_hint)
            if not symbol:
                continue
            name = cls._find_instrument_name(values, symbol)
            exchange = cls._exchange_from_symbol(symbol, exchange_hint)
            records.append(
                {
                    "symbol": symbol,
                    "market": market.value,
                    "name": name or symbol,
                    "exchange": exchange,
                    "raw_payload": cls._safe_payload(row.to_dict()),
                }
            )
        return list({item["symbol"]: item for item in records}.values())

    @staticmethod
    def _find_instrument_code(
        values: list[str],
        market: Market,
        exchange_hint: str,
    ) -> str:
        suffixes = (
            {"SH", "SZ", "BJ"}
            if market == Market.STOCK
            else {"CFE", "CFX", "SHF", "INE", "DCE", "ZCE", "CZC", "GFEX", "GFE"}
        )
        for value in values:
            candidate = value.strip().upper()
            if "." in candidate:
                body, suffix = candidate.rsplit(".", 1)
                if body and suffix in suffixes and CODE_PATTERN.fullmatch(candidate):
                    return candidate
        if market == Market.FUTURES and exchange_hint:
            suffix = FUTURES_SUFFIX.get(exchange_hint.upper(), exchange_hint.upper())
            for value in values:
                candidate = value.strip().upper()
                if (
                    CODE_PATTERN.fullmatch(candidate)
                    and any(char.isalpha() for char in candidate)
                    and any(char.isdigit() for char in candidate)
                    and len(candidate) <= 16
                ):
                    return f"{candidate}.{suffix}"
        return ""

    @staticmethod
    def _find_instrument_name(values: list[str], symbol: str) -> str:
        ignored = {symbol, symbol.split(".", 1)[0]}
        for value in values:
            candidate = value.strip()
            if candidate in ignored or not candidate:
                continue
            if any("\u4e00" <= char <= "\u9fff" for char in candidate):
                return candidate[:128]
        return ""

    @staticmethod
    def _exchange_from_symbol(symbol: str, exchange_hint: str = "") -> str:
        suffix = symbol.rsplit(".", 1)[-1].upper() if "." in symbol else ""
        return {
            "SH": "SSE",
            "SZ": "SZSE",
            "BJ": "BSE",
            "CFE": "CFFEX",
            "CFX": "CFFEX",
            "SHF": "SHFE",
            "INE": "INE",
            "DCE": "DCE",
            "ZCE": "CZCE",
            "CZC": "CZCE",
            "GFEX": "GFEX",
            "GFE": "GFEX",
        }.get(suffix, exchange_hint.upper())

    def _dataframe_to_bars(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
    ) -> list[KlineBar]:
        columns = {str(col).strip().lower(): col for col in df.columns}
        time_col = columns.get("time") or columns.get("datetime") or columns.get("date")
        bars: list[KlineBar] = []
        for _, row in df.iterrows():
            try:
                bars.append(
                    KlineBar(
                        symbol=symbol,
                        market=self.market,
                        interval=interval,
                        bar_time=self._parse_time(row.get(time_col) if time_col else None),
                        open=self._safe_decimal(row.get(columns.get("open"))),
                        high=self._safe_decimal(row.get(columns.get("high"))),
                        low=self._safe_decimal(row.get(columns.get("low"))),
                        close=self._safe_decimal(row.get(columns.get("close"))),
                        volume=self._safe_decimal(row.get(columns.get("volume"))),
                        raw_payload=self._safe_payload(row.to_dict()),
                    )
                )
            except Exception:
                continue
        return bars

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise SDKConnectionFailed("iFinD 行情适配器未连接")

    @staticmethod
    def _safe_decimal(value: Any, default: str = "0") -> Decimal:
        if value is None or pd.isna(value):
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if value is None or value == "":
            return datetime.now(timezone.utc)
        parsed = pd.to_datetime(value).to_pydatetime()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
        return parsed

    @staticmethod
    def _format_datetime(value: datetime, *, with_time: bool) -> str:
        if value.tzinfo is not None:
            value = value.astimezone(SHANGHAI_TZ)
        return value.strftime("%Y-%m-%d %H:%M:%S" if with_time else "%Y-%m-%d")

    @staticmethod
    def _safe_payload(payload: dict) -> dict:
        result: dict[str, Any] = {}
        for key, value in payload.items():
            if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
                result[str(key)] = None
            elif isinstance(value, (str, int, float, bool)):
                result[str(key)] = value
            else:
                result[str(key)] = str(value)
        return result
