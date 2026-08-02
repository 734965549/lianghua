"""AKShare 行情适配器：真实行情 + 程序内模拟撮合。"""

import logging
import math
import random
import re
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pandas as pd

from app.core.domestic_futures import FUTURES_NAME_BY_SYMBOL, domestic_futures_records
from app.core.time import as_market_time, market_time_as_utc
from app.schemas.enums import Market, OrderSide, OrderStatus
from app.sdk.base import SDKDisconnected, SDKNotConfigured, SDKOrderRejected, TradingAdapter
from app.sdk.matching import limit_safe_fill_price
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
from app.sdk.normalization import percentage_points_to_ratio

# 模块级占位，便于单元测试 mock；未安装时保持 None，首次调用时延迟导入
ak = None
logger = logging.getLogger(__name__)


class AkshareAdapter(TradingAdapter):
    """真实行情（AKShare）+ 模拟撮合。"""

    name = "akshare"

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
        self._background_sync_enabled = bool(
            self.config.get("akshare_background_sync", True)
        )
        self._full_sync_seconds = max(
            self._poll_seconds,
            float(self.config.get("akshare_full_sync_seconds", 60.0)),
        )
        self._request_timeout = max(
            1.0, float(self.config.get("akshare_request_timeout", 8.0))
        )
        self._max_retries = max(
            0, int(self.config.get("akshare_max_retries", 2))
        )
        self._retry_backoff = max(
            0.0, float(self.config.get("akshare_retry_backoff", 0.6))
        )
        self._rate_limit_seconds = max(
            0.0, float(self.config.get("akshare_rate_limit_seconds", 0.25))
        )
        self._batch_pause_seconds = max(
            0.0, float(self.config.get("akshare_batch_pause_seconds", 0.15))
        )
        self._batch_size = min(
            80, max(20, int(self.config.get("akshare_batch_size", 80)))
        )
        self._catalog_wait_seconds = max(
            1.0, float(self.config.get("akshare_catalog_wait_seconds", 120.0))
        )
        self._spot_total_pages = 1
        self._spot_sync_done = threading.Event()
        self._sync_thread: threading.Thread | None = None
        self._sync_stop = threading.Event()
        self._network_lock = threading.Lock()
        self._futures_refresh_lock = threading.Lock()
        self._last_futures_refresh_at = 0.0
        self._next_request_at = 0.0
        self._last_refresh_error: str | None = None
        self._http_client = self._build_http_client()
        self._lock = threading.Lock()

    # ---- 生命周期 ----
    def connect(self) -> AdapterStatus:
        if self._http_client.is_closed:
            self._http_client = self._build_http_client()
        self._connected = True
        self._quote_stop.clear()
        self._sync_stop.clear()
        if self._background_sync_enabled and self.market == Market.STOCK:
            self._start_background_sync()
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

    def _build_http_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(self._request_timeout),
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                ),
            },
        )

    def _start_background_sync(self) -> None:
        """只启动一个全市场后台同步任务。"""
        if self._sync_thread and self._sync_thread.is_alive():
            return
        self._sync_stop.clear()
        self._sync_thread = threading.Thread(
            target=self._background_sync_loop,
            name=f"akshare-full-sync-{self.market.value}",
            daemon=True,
        )
        self._sync_thread.start()

    def _background_sync_loop(self) -> None:
        """按固定周期分页同步全市场，失败后保留已有缓存。"""
        while not self._sync_stop.is_set() and self._connected:
            self._refresh_spot_snapshot()
            if self._sync_stop.wait(self._full_sync_seconds):
                break

    def disconnect(self) -> None:
        self._quote_stop.set()
        self._sync_stop.set()
        if self._quote_thread and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=2.0)
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=self._request_timeout + 1.0)
        self._connected = False
        self._http_client.close()
        if self._on_connection_change:
            self._on_connection_change(
                ConnectionEvent(
                    market=self.market,
                    connected=False,
                    reason="disconnect",
                    event_time=datetime.now(timezone.utc),
                )
            )

    def _ak(self):
        """延迟导入 akshare；未安装时抛出 SDKNotConfigured。"""
        global ak
        if ak is not None:
            return ak
        try:
            import akshare
        except ImportError as exc:
            raise SDKNotConfigured("akshare 包未安装") from exc
        ak = akshare
        return ak

    def list_instruments(self) -> list[dict]:
        """从 AKShare 公共数据源读取当前股票或期货标的目录。"""
        if self.market == Market.STOCK:
            if not self._spot_sync_done.wait(self._catalog_wait_seconds):
                raise SDKDisconnected(
                    "AKShare 全市场分页同步尚未完成，保留现有标的目录"
                )
            with self._lock:
                snapshots = list(self._latest_quotes.values())
            records = []
            for snapshot in snapshots:
                symbol = self._normalize_symbol(snapshot.symbol)
                records.append(
                    {
                        "symbol": symbol,
                        "market": self.market.value,
                        "name": str(
                            (snapshot.raw_payload or {}).get("name") or symbol
                        ).strip(),
                        "exchange": (
                            "SSE"
                            if symbol.endswith(".SH")
                            else "BSE"
                            if symbol.endswith(".BJ")
                            else "SZSE"
                        ),
                        "raw_payload": {"provider": self.name},
                    }
                )
            return records

        records = domestic_futures_records()
        for record in records:
            record["raw_payload"] = {
                "provider": self.name,
                "catalog": "domestic-main-continuous",
            }
        return records

    # ---- 行情（真实）----
    def _refresh_spot_snapshot(self) -> None:
        """分页同步全市场；每页完成后立即更新缓存。"""
        page = 1
        while not self._sync_stop.is_set() and self._connected:
            try:
                rows, total_pages = self._fetch_spot_page(page)
            except Exception as exc:
                self._last_refresh_error = str(exc)
                logger.warning(
                    "AKShare 全市场同步第 %s 页失败，保留已有缓存：%s",
                    page,
                    exc,
                )
                return

            if not rows:
                return
            self._update_spot_batch(rows)
            self._last_refresh_error = None
            if page >= total_pages:
                self._spot_sync_done.set()
                return

            page += 1
            if self._sync_stop.wait(self._batch_pause_seconds):
                return

    def _fetch_spot_page(self, page: int) -> tuple[list[dict], int]:
        """读取一页沪深京 A 股行情，返回数据与总页数。"""
        if page == 1:
            total_payload = self._request_json(
                (
                    "http://vip.stock.finance.sina.com.cn/quotes_service/api/"
                    "json_v2.php/Market_Center.getHQNodeStockCount"
                ),
                params={"node": "hs_a"},
            )
            try:
                total = int(total_payload)
            except (TypeError, ValueError) as exc:
                raise SDKDisconnected("AKShare 全市场总数响应异常") from exc
            self._spot_total_pages = max(
                1, math.ceil(total / self._batch_size)
            )

        payload = self._request_json(
            (
                "http://vip.stock.finance.sina.com.cn/quotes_service/api/"
                "json_v2.php/Market_Center.getHQNodeData"
            ),
            params={
                "page": str(page),
                "num": str(self._batch_size),
                "sort": "symbol",
                "asc": "1",
                "node": "hs_a",
                "symbol": "",
                "_s_r_a": "page",
            },
        )
        if not isinstance(payload, list):
            raise SDKDisconnected("AKShare 全市场分页响应异常")
        rows = [row for row in payload if isinstance(row, dict)]
        return rows, self._spot_total_pages

    def _update_spot_batch(self, rows: list[dict]) -> None:
        """将一页源站字段转换后原子写入缓存。"""
        batch: dict[str, QuoteSnapshot] = {}
        quote_time = datetime.now(timezone.utc)
        for row in rows:
            code = str(
                row.get("code") or row.get("f12") or row.get("代码") or ""
            ).strip()
            if not re.fullmatch(r"\d{6}", code):
                continue
            symbol = self._normalize_symbol(code)
            batch[symbol] = QuoteSnapshot(
                symbol=symbol,
                market=self.market,
                last_price=self._safe_decimal(
                    row.get("trade")
                    if "trade" in row
                    else row.get("f2")
                    if "f2" in row
                    else row.get("最新价"),
                    "0",
                ),
                change_rate=percentage_points_to_ratio(
                    self._safe_decimal(
                        row.get("changepercent")
                        if "changepercent" in row
                        else row.get("f3")
                        if "f3" in row
                        else row.get("涨跌幅"),
                        "0",
                    )
                ),
                volume=self._safe_decimal(
                    row.get("volume")
                    if "volume" in row
                    else row.get("f5")
                    if "f5" in row
                    else row.get("成交量"),
                    "0",
                ),
                quote_time=quote_time,
                raw_payload={
                    "provider": self.name,
                    "source": "sina",
                    "name": row.get("name") or row.get("f14") or row.get("名称"),
                },
            )
        if not batch:
            return
        with self._lock:
            self._latest_quotes.update(batch)

    def _request_json(self, url: str, *, params: dict):
        """带超时、重试、指数退避和进程内节流的 JSON 请求。"""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with self._network_lock:
                    delay = self._next_request_at - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    try:
                        response = self._http_client.get(url, params=params)
                    finally:
                        self._next_request_at = (
                            time.monotonic() + self._rate_limit_seconds
                        )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                backoff = self._retry_backoff * (2**attempt)
                if self._sync_stop.wait(backoff):
                    break

        detail = type(last_error).__name__ if last_error else "unknown"
        raise SDKDisconnected(
            f"AKShare 源站请求失败（{detail}，已重试 {self._max_retries} 次）"
        ) from last_error

    def _request_text(
        self,
        url: str,
        *,
        params: dict,
        headers: dict[str, str] | None = None,
        encoding: str = "utf-8",
    ) -> str:
        """使用与股票同步相同的超时、重试和限流策略读取文本响应。"""

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with self._network_lock:
                    delay = self._next_request_at - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    try:
                        response = self._http_client.get(
                            url,
                            params=params,
                            headers=headers,
                        )
                    finally:
                        self._next_request_at = (
                            time.monotonic() + self._rate_limit_seconds
                        )
                response.raise_for_status()
                return response.content.decode(encoding, errors="ignore")
            except (httpx.HTTPError, UnicodeError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                backoff = self._retry_backoff * (2**attempt)
                if self._sync_stop.wait(backoff):
                    break

        detail = type(last_error).__name__ if last_error else "unknown"
        raise SDKDisconnected(
            f"AKShare 期货源站请求失败（{detail}，已重试 {self._max_retries} 次）"
        ) from last_error

    def _fetch_stock_quote(self, symbol: str) -> QuoteSnapshot:
        """轻量读取单只股票，不触发全市场下载。"""
        bare = symbol.split(".")[0]
        market_code = "1" if bare.startswith(("60", "68", "11", "13")) else "0"
        payload = self._request_json(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "fltt": "2",
                "invt": "2",
                "secid": f"{market_code}.{bare}",
                "fields": "f12,f14,f19,f20,f39,f40,f43,f47,f169,f170",
            },
        )
        data = payload.get("data")
        if not isinstance(data, dict) or data.get("f43") in (None, "-"):
            raise SDKDisconnected(f"AKShare 暂无 {symbol} 的单股行情")

        normalized = self._normalize_symbol(str(data.get("f12") or bare))
        snapshot = QuoteSnapshot(
            symbol=normalized,
            market=self.market,
            last_price=self._safe_decimal(data.get("f43"), "0"),
            change_rate=percentage_points_to_ratio(
                self._safe_decimal(data.get("f170"), "0")
            ),
            volume=self._safe_decimal(data.get("f47"), "0"),
            bid_price=self._optional_decimal(data.get("f19")),
            ask_price=self._optional_decimal(data.get("f39")),
            bid_volume=self._optional_decimal(data.get("f20"), multiplier=100),
            ask_volume=self._optional_decimal(data.get("f40"), multiplier=100),
            quote_time=datetime.now(timezone.utc),
            raw_payload={
                "provider": self.name,
                "source": "eastmoney",
                "name": data.get("f14"),
                "change": data.get("f169"),
            },
        )
        with self._lock:
            self._latest_quotes[normalized] = snapshot
        return snapshot

    def _refresh_futures_snapshot(
        self,
        symbols: list[str] | None = None,
        *,
        force: bool = False,
    ) -> None:
        """按订阅品种批量拉取新浪期货行情，不再请求 AKShare 的默认示例合约。"""

        if symbols is None:
            with self._lock:
                symbols = list(self._subscribed)
        requested = sorted(
            {
                self._normalize_futures_symbol(symbol)
                for symbol in symbols
                if str(symbol or "").strip()
            }
        )
        if not requested:
            return

        # get_quote 与订阅线程可能同时触发刷新，只允许一个批次访问源站。
        with self._futures_refresh_lock:
            if not force:
                with self._lock:
                    if all(symbol in self._latest_quotes for symbol in requested):
                        return
                cooldown = min(2.0, max(0.25, self._poll_seconds))
                if time.monotonic() - self._last_futures_refresh_at < cooldown:
                    return
            try:
                text = self._request_text(
                    "https://hq.sinajs.cn/",
                    params={"list": ",".join(f"nf_{symbol}" for symbol in requested)},
                    headers={
                        "Accept": "*/*",
                        "Referer": "https://vip.stock.finance.sina.com.cn/",
                    },
                    encoding="gbk",
                )
                batch = self._parse_futures_response(text, requested)
            except SDKDisconnected as exc:
                self._last_refresh_error = str(exc)
                logger.warning("AKShare 期货行情刷新失败，保留已有缓存：%s", exc)
                return
            finally:
                self._last_futures_refresh_at = time.monotonic()

            if not batch:
                self._last_refresh_error = "期货源站返回空行情"
                return
            self._last_refresh_error = None
            with self._lock:
                self._latest_quotes.update(batch)

    def _parse_futures_response(
        self,
        text: str,
        requested: list[str],
    ) -> dict[str, QuoteSnapshot]:
        """解析新浪 ``hq_str_nf_*`` 行情；代码取响应变量名，避免误用中文名称。"""

        requested_set = set(requested)
        cffex_products = {"IF", "IH", "IC", "IM", "TS", "TF", "TL", "T"}
        batch: dict[str, QuoteSnapshot] = {}
        quote_time = datetime.now(timezone.utc)
        for raw_line in text.split(";"):
            matched = re.search(
                r"hq_str_nf_([A-Za-z0-9]+)\s*=\s*\"(.*)\"",
                raw_line.strip(),
            )
            if not matched:
                continue
            symbol = matched.group(1).upper()
            if symbol not in requested_set:
                continue
            fields = matched.group(2).split(",")
            product_match = re.match(r"[A-Z]+", symbol)
            is_cffex = bool(
                product_match and product_match.group(0) in cffex_products
            )
            price_index = 3 if is_cffex else 8
            volume_index = 4 if is_cffex else 14
            if len(fields) <= max(price_index, volume_index):
                continue

            last_price = self._safe_decimal(fields[price_index], "0")
            volume = self._safe_decimal(fields[volume_index], "0")
            change_rate = Decimal("0")
            bid_price = ask_price = None
            bid_volume = ask_volume = None
            if not is_cffex:
                previous_settle = self._safe_decimal(fields[10], "0")
                if previous_settle:
                    change_rate = (last_price - previous_settle) / previous_settle
                bid_price = self._optional_decimal(fields[6])
                ask_price = self._optional_decimal(fields[7])
                bid_volume = self._optional_decimal(fields[11])
                ask_volume = self._optional_decimal(fields[12])

            batch[symbol] = QuoteSnapshot(
                symbol=symbol,
                market=self.market,
                last_price=last_price,
                change_rate=change_rate,
                volume=volume,
                bid_price=bid_price,
                ask_price=ask_price,
                bid_volume=bid_volume,
                ask_volume=ask_volume,
                quote_time=quote_time,
                raw_payload={
                    "provider": self.name,
                    "source": "sina-futures",
                    "name": FUTURES_NAME_BY_SYMBOL.get(symbol, symbol),
                },
            )
        return batch

    @staticmethod
    def _normalize_symbol(code: str) -> str:
        """统一裸代码、交易所前缀和后缀格式，如 bj920000 -> 920000.BJ。"""
        normalized = str(code or "").strip().upper()
        prefixed = re.fullmatch(r"(SH|SZ|BJ)(\d{6})(?:\.(?:SH|SZ|BJ))?", normalized)
        if prefixed:
            return f"{prefixed.group(2)}.{prefixed.group(1)}"
        suffixed = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", normalized)
        if suffixed:
            return normalized
        if normalized.startswith(("8", "4", "9")):
            return f"{normalized}.BJ"
        if normalized.startswith(("60", "68", "11", "13")):
            return f"{normalized}.SH"
        return f"{normalized}.SZ"

    @staticmethod
    def _normalize_futures_symbol(code: str) -> str:
        """将 RB0、rb0.SHFE 等期货写法统一为新浪可识别的裸代码。"""

        return str(code or "").strip().upper().split(".", 1)[0]

    @staticmethod
    def _safe_decimal(value, default: str = "0") -> Decimal:
        """安全转换为 Decimal，处理 NaN 和异常值。"""
        if pd.isna(value):
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    @classmethod
    def _optional_decimal(
        cls, value, *, multiplier: int = 1
    ) -> Decimal | None:
        if value in (None, "", "-") or pd.isna(value):
            return None
        try:
            return cls._safe_decimal(value) * multiplier
        except Exception:
            return None

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self._ensure_connected()
        symbol = (
            self._normalize_symbol(symbol)
            if self.market == Market.STOCK
            else self._normalize_futures_symbol(symbol)
        )
        with self._lock:
            if symbol in self._latest_quotes:
                return self._latest_quotes[symbol]
        if self.market == Market.STOCK:
            if (
                self._background_sync_enabled
                and self._sync_thread
                and self._sync_thread.is_alive()
                and not self._spot_sync_done.is_set()
            ):
                raise SDKDisconnected(
                    f"AKShare 全市场行情同步中，{symbol} 尚未进入当前批次"
                )
            return self._fetch_stock_quote(symbol)

        with self._lock:
            requested = list(self._subscribed | {symbol})
        self._refresh_futures_snapshot(requested)
        with self._lock:
            if symbol in self._latest_quotes:
                return self._latest_quotes[symbol]
        raise SDKDisconnected(
            f"AKShare 暂无 {symbol} 快照，请确认代码正确且网络可达"
        )

    def get_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        self._ensure_connected()
        if self.market == Market.FUTURES:
            return self._get_futures_kline(symbol, interval, start, end)
        return self._get_stock_kline(symbol, interval, start, end)

    def _get_stock_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        bare = symbol.split(".")[0]
        adjust = self.config.get("akshare_adjust", "qfq")
        local_start = as_market_time(start)
        local_end = as_market_time(end)

        if interval == "1d":
            if bare.startswith(("60", "68", "11", "13")):
                sina_symbol = f"sh{bare}"
            else:
                sina_symbol = f"sz{bare}"
            try:
                df = self._ak().stock_zh_a_daily(
                    symbol=sina_symbol,
                    start_date=local_start.strftime("%Y%m%d"),
                    end_date=local_end.strftime("%Y%m%d"),
                    adjust=adjust,
                )
            except Exception:
                return []
            return self._df_to_bars(df, symbol, interval, date_col="date")

        if interval in ("1m", "5m"):
            period_map = {"1m": "1", "5m": "5"}
            sina_symbol = (
                f"sh{bare}"
                if bare.startswith(("60", "68", "11", "13"))
                else f"sz{bare}"
            )
            df = None
            try:
                df = self._ak().stock_zh_a_minute(
                    symbol=sina_symbol,
                    period=period_map[interval],
                    adjust=adjust,
                )
            except Exception:
                logger.warning(
                    "Sina 分钟 K 线不可用，回退 Eastmoney: %s %s",
                    symbol,
                    interval,
                )
            if df is not None and not df.empty:
                bars = self._df_to_bars(df, symbol, interval, date_col="day")
                return [bar for bar in bars if start <= bar.bar_time <= end]

            try:
                df = self._ak().stock_zh_a_hist_min_em(
                    symbol=bare,
                    start_date=local_start.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date=local_end.strftime("%Y-%m-%d %H:%M:%S"),
                    period=period_map[interval],
                    adjust=adjust,
                )
            except Exception:
                logger.warning(
                    "Eastmoney 分钟 K 线回退失败: %s %s",
                    symbol,
                    interval,
                    exc_info=True,
                )
                return []
            return self._df_to_bars(df, symbol, interval, date_col="时间")

        return []

    def _get_futures_kline(self, symbol: str, interval: str, start, end) -> list[KlineBar]:
        if interval == "1d":
            try:
                df = self._ak().futures_zh_daily_sina(symbol=symbol)
            except Exception:
                return []
            if df is None or df.empty:
                return []
            bars = self._df_to_bars(df, symbol, interval, date_col="date")
            return [b for b in bars if start <= b.bar_time <= end]

        if interval in ("1m", "5m"):
            period_map = {"1m": "1", "5m": "5"}
            try:
                df = self._ak().futures_zh_minute_sina(symbol=symbol, period=period_map[interval])
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
                bar_time = market_time_as_utc(
                    pd.to_datetime(str(row.get(date_col))).to_pydatetime()
                )
                bars.append(
                    KlineBar(
                        symbol=symbol,
                        market=self.market,
                        interval=interval,
                        bar_time=bar_time,
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
        normalized = [
            self._normalize_symbol(symbol)
            if self.market == Market.STOCK
            else self._normalize_futures_symbol(symbol)
            for symbol in symbols
        ]
        with self._lock:
            self._subscribed.update(normalized)
        if self._quote_thread is None or not self._quote_thread.is_alive():
            self._quote_stop.clear()
            self._quote_thread = threading.Thread(target=self._quote_loop, daemon=True)
            self._quote_thread.start()

    def _quote_loop(self) -> None:
        """推送缓存行情；缺失标的仅做单标的轻量补拉。"""
        while not self._quote_stop.is_set() and self._connected:
            if self.market == Market.FUTURES:
                with self._lock:
                    futures_symbols = list(self._subscribed)
                self._refresh_futures_snapshot(futures_symbols, force=True)
            with self._lock:
                missing = [
                    symbol
                    for symbol in self._subscribed
                    if symbol not in self._latest_quotes
                ]

            if self.market == Market.STOCK:
                for symbol in missing:
                    if self._quote_stop.is_set():
                        break
                    try:
                        self._fetch_stock_quote(symbol)
                    except SDKDisconnected:
                        continue

            with self._lock:
                snaps = [
                    self._latest_quotes[s]
                    for s in self._subscribed
                    if s in self._latest_quotes
                ]
            for snap in snaps:
                if self._on_quote_update:
                    self._on_quote_update(snap)
            self._quote_stop.wait(self._poll_seconds)

    # ---- 账户/持仓（模拟）----
    def get_account(self) -> AccountSnapshot:
        self._ensure_connected()
        with self._lock:
            market_value = sum(
                (position.market_value for position in self._positions.values()),
                Decimal("0"),
            )
        total_asset = Decimal("1000000")
        return AccountSnapshot(
            account_id=uuid4(),
            account_no="AKSHARE_SIM",
            total_asset=total_asset,
            available_cash=max(Decimal("0"), total_asset - market_value),
            frozen_cash=Decimal("0"),
            market_value=market_value,
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
            fill_price = limit_safe_fill_price(request, snap.last_price)
        except Exception:
            # 无法获取行情时降级为委托价
            fill_price = request.price if request.price and request.price > 0 else Decimal("10.00")
            fill_price = limit_safe_fill_price(request, fill_price)
        
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
            fill_price2 = limit_safe_fill_price(
                request, fill_price + Decimal("0.01")
            )
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
