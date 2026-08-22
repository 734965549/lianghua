"""TqSdk 独立期货行情适配器。

与 TqSdkBroker 分离：此处仅需快期账号（TqAuth），不要求期货资金账户。
所有 TqApi 调用必须在本模块工作线程内完成。
"""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.broker.tqsdk_mapping import to_tq_quote_symbol
from app.schemas.enums import Market
from app.sdk.base import SDKConnectionFailed, SDKNotConfigured, SDKResponseInvalid
from app.sdk.market_data.base import MarketDataAdapter
from app.sdk.models import KlineBar, QuoteSnapshot

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "60m": 3600,
    "1d": 86400,
    "day": 86400,
}
_MAX_KLINE_BARS = 8000
_QUOTE_WAIT_TIMEOUT = 8.0


@dataclass
class _Command:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


def create_tq_quote_api(config: dict) -> Any:
    """仅用快期账号创建行情 TqApi，不绑定期货资金账户。"""
    try:
        from tqsdk import TqApi, TqAuth
    except ImportError as exc:  # pragma: no cover
        raise SDKNotConfigured(
            "未安装 tqsdk。请执行: pip install tqsdk==3.10.1"
        ) from exc

    auth_user = str(config.get("tqsdk_auth_user") or config.get("auth_user") or "").strip()
    auth_password = str(
        config.get("tqsdk_auth_password") or config.get("auth_password") or ""
    )
    if not auth_user:
        raise SDKNotConfigured("缺少快期账号：LIANGHUA_TQSDK_AUTH_USER")
    if not auth_password:
        raise SDKNotConfigured("缺少快期密码：LIANGHUA_TQSDK_AUTH_PASSWORD")
    return TqApi(auth=TqAuth(auth_user, auth_password))


def _is_nan(value: Any) -> bool:
    if value is None:
        return True
    try:
        if isinstance(value, float) and math.isnan(value):
            return True
    except Exception:
        pass
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "null"}


def _as_decimal(value: Any) -> Decimal | None:
    if _is_nan(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "" or _is_nan(value):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        # TqSdk datetime 常为纳秒或毫秒时间戳
        number = float(value)
        if number > 1e14:
            number /= 1e9
        elif number > 1e11:
            number /= 1e3
        try:
            return datetime.fromtimestamp(number, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text[:26], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def quote_from_tq(
    *,
    project_symbol: str,
    market: Market,
    tq_symbol: str,
    quote_obj: Any,
) -> QuoteSnapshot | None:
    """将 TqSdk Quote 转为普通 QuoteSnapshot；无效行情返回 None。"""
    last_price = _as_decimal(getattr(quote_obj, "last_price", None))
    if last_price is None or last_price <= 0:
        return None
    quote_time = _as_datetime(getattr(quote_obj, "datetime", None))
    if quote_time is None:
        return None

    pre_close = _as_decimal(getattr(quote_obj, "pre_close", None))
    pre_settlement = _as_decimal(getattr(quote_obj, "pre_settlement", None))
    basis = pre_close if pre_close and pre_close > 0 else pre_settlement
    change_rate = Decimal("0")
    if basis and basis > 0:
        change_rate = (last_price - basis) / basis

    volume = _as_decimal(getattr(quote_obj, "volume", None)) or Decimal("0")
    bid_price = _as_decimal(getattr(quote_obj, "bid_price1", None))
    ask_price = _as_decimal(getattr(quote_obj, "ask_price1", None))
    bid_volume = _as_decimal(getattr(quote_obj, "bid_volume1", None))
    ask_volume = _as_decimal(getattr(quote_obj, "ask_volume1", None))

    underlying = getattr(quote_obj, "underlying_symbol", None)
    raw_payload = {
        "provider": "tqsdk",
        "tq_symbol": tq_symbol,
        "exchange_id": getattr(quote_obj, "exchange_id", None),
        "instrument_id": getattr(quote_obj, "instrument_id", None),
        "pre_close": str(pre_close) if pre_close is not None else None,
        "pre_settlement": str(pre_settlement) if pre_settlement is not None else None,
        "open": str(_as_decimal(getattr(quote_obj, "open", None)) or "") or None,
        "high": str(_as_decimal(getattr(quote_obj, "highest", None)) or "") or None,
        "low": str(_as_decimal(getattr(quote_obj, "lowest", None)) or "") or None,
        "open_interest": str(
            _as_decimal(getattr(quote_obj, "open_interest", None)) or ""
        )
        or None,
        "upper_limit": str(
            _as_decimal(getattr(quote_obj, "upper_limit", None)) or ""
        )
        or None,
        "lower_limit": str(
            _as_decimal(getattr(quote_obj, "lower_limit", None)) or ""
        )
        or None,
        "underlying_symbol": str(underlying) if underlying else None,
        "ins_class": getattr(quote_obj, "ins_class", None),
    }
    return QuoteSnapshot(
        symbol=project_symbol,
        market=market,
        last_price=last_price,
        change_rate=change_rate,
        volume=volume,
        bid_price=bid_price,
        ask_price=ask_price,
        bid_volume=bid_volume,
        ask_volume=ask_volume,
        quote_time=quote_time,
        raw_payload=raw_payload,
    )


def _quote_fingerprint(snap: QuoteSnapshot) -> tuple:
    return (
        str(snap.last_price),
        str(snap.volume),
        snap.quote_time.isoformat(),
        str(snap.bid_price),
        str(snap.ask_price),
        str(snap.bid_volume),
        str(snap.ask_volume),
    )


class _TqSdkQuoteRuntime:
    """单线程 TqApi 行情运行时。"""

    def __init__(
        self,
        config: dict,
        *,
        market: Market,
        api_factory: Callable[[dict], Any] | None = None,
        on_quote: Callable[[QuoteSnapshot], None] | None = None,
        on_connection_change: Callable[[bool, str], None] | None = None,
    ):
        self._config = dict(config)
        self._market = market
        self._api_factory = api_factory or (lambda cfg: create_tq_quote_api(cfg))
        self._on_quote = on_quote
        self._on_connection_change = on_connection_change
        self._commands: queue.Queue[_Command | None] = queue.Queue(
            maxsize=int(config.get("tqsdk_command_queue_size") or 1000)
        )
        self._timeout = float(config.get("tqsdk_command_timeout_seconds") or 10.0)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._api: Any = None
        self._fatal: BaseException | None = None
        self._state = "idle"
        self._reconnect_count = 0
        self._last_error = ""
        self._last_quote_at: datetime | None = None
        # project_symbol -> tq_symbol / quote ref / fingerprint
        self._project_to_tq: dict[str, str] = {}
        self._tq_to_project: dict[str, str] = {}
        self._quote_refs: dict[str, Any] = {}
        self._latest: dict[str, QuoteSnapshot] = {}
        self._fingerprints: dict[str, tuple] = {}
        self._thread_id: int | None = None

    @property
    def state(self) -> str:
        return self._state

    def start(self) -> dict:
        if self._thread and self._thread.is_alive() and self._state == "ready":
            return self.health()
        if self._thread and self._thread.is_alive():
            # 线程已在重连，等待回到 ready
            deadline = time.time() + max(self._timeout, 15.0)
            while time.time() < deadline:
                if self._state == "ready" and self._api is not None:
                    return self.health()
                if self._state == "failed":
                    break
                time.sleep(0.05)
            raise SDKConnectionFailed(
                f"TqSdk 行情未就绪: state={self._state}"
            )
        self._stop.clear()
        self._ready.clear()
        self._fatal = None
        self._state = "starting"
        self._thread = threading.Thread(
            target=self._run,
            name="tqsdk-market-data",
            daemon=True,
        )
        self._thread.start()
        deadline = time.time() + max(self._timeout, 15.0)
        while time.time() < deadline:
            self._ready.wait(timeout=0.2)
            if self._fatal is not None and self._state == "failed":
                self.stop()
                raise SDKConnectionFailed(
                    f"TqSdk 行情连接失败: {self._fatal}"
                ) from self._fatal
            if self._state == "ready" and self._api is not None:
                return self.health()
            if not self._thread.is_alive():
                break
        self.stop()
        raise SDKConnectionFailed(
            f"TqSdk 行情线程启动超时: state={self._state}"
        )

    def stop(self) -> None:
        self._stop.set()
        try:
            self._commands.put_nowait(None)
        except queue.Full:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None
        self._api = None
        self._state = "stopped"

    def call(self, name: str, **args: Any) -> Any:
        if self._thread_id is not None and threading.get_ident() == self._thread_id:
            raise RuntimeError("禁止在 TqSdk 行情工作线程内同步 call()")
        if not self._thread or not self._thread.is_alive():
            raise SDKConnectionFailed("TqSdk 行情线程未运行")
        wait_timeout = self._timeout
        if self._state == "reconnecting":
            # 给退避重连留出窗口，避免短暂断线导致业务侧误判超时
            wait_timeout = max(
                wait_timeout,
                float(self._config.get("tqsdk_reconnect_max_seconds") or 60.0) + 5.0,
            )
        cmd = _Command(name=name, args=args)
        self._commands.put(cmd, timeout=wait_timeout)
        if not cmd.event.wait(timeout=wait_timeout):
            raise SDKConnectionFailed(f"TqSdk 行情命令超时: {name}")
        if cmd.error is not None:
            raise cmd.error
        return cmd.result

    def health(self) -> dict:
        return {
            "connected": self._state == "ready" and self._api is not None,
            "provider": "tqsdk",
            "state": self._state,
            "subscribed": sorted(self._project_to_tq.keys()),
            "reconnect_count": self._reconnect_count,
            "last_error": self._last_error,
            "last_quote_at": self._last_quote_at.isoformat() if self._last_quote_at else None,
        }

    def _run(self) -> None:
        self._thread_id = threading.get_ident()
        backoff = 1.0
        max_backoff = float(self._config.get("tqsdk_reconnect_max_seconds") or 60.0)
        ever_ready = False
        try:
            while not self._stop.is_set():
                try:
                    self._api = self._api_factory(self._config)
                    self._restore_subscriptions()
                    self._state = "ready"
                    self._fatal = None
                    self._ready.set()
                    reason = (
                        "tqsdk market reconnected"
                        if ever_ready
                        else "tqsdk market ready"
                    )
                    if self._on_connection_change:
                        self._on_connection_change(True, reason)
                    ever_ready = True
                    backoff = 1.0

                    while not self._stop.is_set():
                        self._drain_commands(max_items=64)
                        api = self._api
                        if api is None:
                            break
                        deadline = time.time() + 0.05
                        try:
                            api.wait_update(deadline=deadline)
                        except TypeError:
                            api.wait_update()
                        self._poll_quotes()
                except BaseException as exc:
                    if isinstance(exc, (SystemExit, KeyboardInterrupt)):
                        raise
                    self._last_error = str(exc)
                    logger.exception("TqSdk 行情会话异常: %s", exc)
                    self._close_api()
                    self._quote_refs.clear()
                    if self._stop.is_set():
                        break
                    self._reconnect_count += 1
                    self._state = "reconnecting" if ever_ready else "starting"
                    if ever_ready and self._on_connection_change:
                        try:
                            self._on_connection_change(False, str(exc))
                        except Exception:
                            pass
                    logger.warning(
                        "TqSdk 行情将在 %.1fs 后重连 (attempt=%s error=%s)",
                        backoff,
                        self._reconnect_count,
                        self._last_error,
                    )
                    self._stop.wait(backoff)
                    backoff = min(max_backoff, max(1.0, backoff * 2))
        finally:
            self._ready.set()
            self._close_api()
            if not self._stop.is_set() and not ever_ready:
                self._state = "failed"
            elif self._state != "failed":
                self._state = "stopped"
            if self._on_connection_change:
                try:
                    self._on_connection_change(False, "tqsdk market stopped")
                except Exception:
                    pass

    def _drain_commands(self, *, max_items: int) -> None:
        for _ in range(max_items):
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                return
            if cmd is None:
                self._stop.set()
                return
            try:
                cmd.result = self._dispatch(cmd.name, cmd.args)
            except BaseException as exc:
                cmd.error = exc
            finally:
                cmd.event.set()

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        if name == "subscribe":
            return self._subscribe(list(args.get("symbols") or []))
        if name == "unsubscribe":
            return self._unsubscribe(list(args.get("symbols") or []))
        if name == "get_quote":
            return self._get_quote(str(args["symbol"]))
        if name == "get_kline":
            return self._get_kline(
                str(args["symbol"]),
                str(args["interval"]),
                args.get("start"),
                args.get("end"),
            )
        if name == "get_tick_trades":
            return self._get_tick_trades(
                str(args["symbol"]),
                int(args.get("limit") or 30),
            )
        if name == "health":
            return self.health()
        raise ValueError(f"未知 TqSdk 行情命令: {name}")

    def _restore_subscriptions(self) -> None:
        """重连后按已订阅项目代码重新 get_quote，恢复引用。"""
        symbols = list(self._project_to_tq.keys())
        self._quote_refs.clear()
        self._fingerprints.clear()
        if symbols:
            self._subscribe(symbols)

    def _subscribe(self, symbols: list[str]) -> list[str]:
        api = self._require_api()
        accepted: list[str] = []
        for symbol in symbols:
            project = str(symbol or "").strip()
            if not project:
                continue
            tq_symbol = to_tq_quote_symbol(project)
            quote_ref = api.get_quote(tq_symbol)
            self._project_to_tq[project] = tq_symbol
            self._tq_to_project[tq_symbol] = project
            self._quote_refs[project] = quote_ref
            accepted.append(project)
            snap = quote_from_tq(
                project_symbol=project,
                market=self._market,
                tq_symbol=tq_symbol,
                quote_obj=quote_ref,
            )
            if snap is not None:
                self._store_and_maybe_emit(project, snap, force=True)
        return accepted

    def _unsubscribe(self, symbols: list[str]) -> list[str]:
        removed: list[str] = []
        for symbol in symbols:
            project = str(symbol or "").strip()
            tq_symbol = self._project_to_tq.pop(project, None)
            self._quote_refs.pop(project, None)
            self._latest.pop(project, None)
            self._fingerprints.pop(project, None)
            if tq_symbol:
                self._tq_to_project.pop(tq_symbol, None)
                removed.append(project)
        return removed

    def _get_quote(self, symbol: str) -> QuoteSnapshot:
        project = str(symbol or "").strip()
        if project not in self._quote_refs:
            self._subscribe([project])
        cached = self._latest.get(project)
        if cached is not None:
            return cached
        # 等待第一帧有效行情
        deadline = time.time() + _QUOTE_WAIT_TIMEOUT
        api = self._require_api()
        while time.time() < deadline:
            try:
                api.wait_update(deadline=min(time.time() + 0.2, deadline))
            except TypeError:
                api.wait_update()
            self._poll_quotes()
            cached = self._latest.get(project)
            if cached is not None:
                return cached
        raise SDKResponseInvalid(f"TqSdk 尚未收到 {project} 的有效行情")

    def _get_kline(
        self,
        symbol: str,
        interval: str,
        start: datetime | None,
        end: datetime | None,
    ) -> list[KlineBar]:
        api = self._require_api()
        seconds = _INTERVAL_SECONDS.get(str(interval).strip().lower())
        if seconds is None:
            raise SDKNotConfigured(f"TqSdk 暂不支持 K 线周期: {interval}")
        project = str(symbol or "").strip()
        tq_symbol = to_tq_quote_symbol(project)
        data_length = 200
        if start is not None and end is not None and end > start:
            span = (end - start).total_seconds()
            data_length = max(2, min(_MAX_KLINE_BARS, int(span / seconds) + 2))
        serial = api.get_kline_serial(tq_symbol, seconds, data_length=data_length)
        # 推动一次更新，尽量填满序列
        try:
            api.wait_update(deadline=time.time() + 0.5)
        except TypeError:
            api.wait_update()
        bars: list[KlineBar] = []
        try:
            length = len(serial)
        except TypeError:
            length = int(getattr(serial, "shape", [0])[0] or 0)
        for index in range(length):
            try:
                row = serial.iloc[index]
            except Exception:
                continue
            bar_time = _as_datetime(row.get("datetime") if hasattr(row, "get") else row["datetime"])
            open_px = _as_decimal(row["open"] if "open" in row else None)
            high_px = _as_decimal(row["high"] if "high" in row else None)
            low_px = _as_decimal(row["low"] if "low" in row else None)
            close_px = _as_decimal(row["close"] if "close" in row else None)
            volume = _as_decimal(row["volume"] if "volume" in row else None) or Decimal("0")
            if bar_time is None or open_px is None or high_px is None or low_px is None or close_px is None:
                continue
            if start is not None and bar_time < start:
                continue
            if end is not None and bar_time > end:
                continue
            bars.append(
                KlineBar(
                    symbol=project,
                    market=self._market,
                    interval=interval,
                    bar_time=bar_time,
                    open=open_px,
                    high=high_px,
                    low=low_px,
                    close=close_px,
                    volume=volume,
                    raw_payload={"provider": "tqsdk", "tq_symbol": tq_symbol},
                )
            )
        return bars

    def _get_tick_trades(self, symbol: str, limit: int) -> list[dict]:
        """从 TqSdk tick 序列提取近期成交；最新在前，字段对齐前端。"""
        api = self._require_api()
        project = str(symbol or "").strip()
        tq_symbol = to_tq_quote_symbol(project)
        want = max(1, min(200, int(limit)))
        data_length = max(want + 5, min(1000, want * 2))
        serial = api.get_tick_serial(tq_symbol, data_length=data_length)
        try:
            api.wait_update(deadline=time.time() + 0.8)
        except TypeError:
            api.wait_update()

        try:
            length = len(serial)
        except TypeError:
            length = int(getattr(serial, "shape", [0])[0] or 0)

        rows: list[dict] = []
        prev_volume: Decimal | None = None
        for index in range(length):
            try:
                row = serial.iloc[index]
            except Exception:
                continue
            last_price = _as_decimal(
                row["last_price"] if "last_price" in row else None
            )
            if last_price is None or last_price <= 0:
                if prev_volume is None:
                    cum = _as_decimal(row["volume"] if "volume" in row else None)
                    if cum is not None:
                        prev_volume = cum
                continue
            cum_volume = _as_decimal(row["volume"] if "volume" in row else None)
            trade_volume = Decimal("0")
            if cum_volume is not None:
                if prev_volume is not None and cum_volume > prev_volume:
                    trade_volume = cum_volume - prev_volume
                prev_volume = cum_volume

            bid = _as_decimal(row["bid_price1"] if "bid_price1" in row else None)
            ask = _as_decimal(row["ask_price1"] if "ask_price1" in row else None)
            direction = "neutral"
            if ask is not None and last_price >= ask:
                direction = "buy"
            elif bid is not None and last_price <= bid:
                direction = "sell"

            tick_time = _as_datetime(
                row["datetime"] if "datetime" in row else None
            )
            time_text = ""
            if tick_time is not None:
                # 前端逐笔统一用本地时分秒
                local = tick_time.astimezone()
                time_text = local.strftime("%H:%M:%S")
            rows.append(
                {
                    "time": time_text,
                    "price": str(last_price),
                    "volume": str(trade_volume),
                    "direction": direction,
                }
            )

        # 最新在前
        rows.reverse()
        return rows[:want]

    def _poll_quotes(self) -> None:
        api = self._api
        if api is None:
            return
        for project, quote_ref in list(self._quote_refs.items()):
            changed = True
            is_changing = getattr(api, "is_changing", None)
            if callable(is_changing):
                try:
                    changed = bool(is_changing(quote_ref))
                except Exception:
                    changed = True
            if not changed:
                continue
            tq_symbol = self._project_to_tq.get(project, "")
            snap = quote_from_tq(
                project_symbol=project,
                market=self._market,
                tq_symbol=tq_symbol,
                quote_obj=quote_ref,
            )
            if snap is None:
                continue
            self._store_and_maybe_emit(project, snap, force=False)

    def _store_and_maybe_emit(
        self, project: str, snap: QuoteSnapshot, *, force: bool
    ) -> None:
        fingerprint = _quote_fingerprint(snap)
        if not force and self._fingerprints.get(project) == fingerprint:
            return
        self._fingerprints[project] = fingerprint
        self._latest[project] = snap
        self._last_quote_at = datetime.now(timezone.utc)
        if self._on_quote:
            self._on_quote(snap)

    def _require_api(self) -> Any:
        if self._api is None:
            raise SDKConnectionFailed("TqSdk 行情 API 未连接")
        return self._api

    def _close_api(self) -> None:
        api = self._api
        self._api = None
        if api is None:
            return
        try:
            close = getattr(api, "close", None)
            if callable(close):
                close()
        except Exception:
            logger.debug("关闭 TqSdk 行情 API 异常", exc_info=True)


class TqSdkMarketDataAdapter(MarketDataAdapter):
    """天勤免费实时期货行情适配器。"""

    name = "tqsdk"

    def __init__(
        self,
        *,
        market: Market,
        config: dict | None = None,
        runtime_factory: Callable[..., _TqSdkQuoteRuntime] | None = None,
        api_factory: Callable[[dict], Any] | None = None,
    ):
        if market != Market.FUTURES:
            raise ValueError("TqSdk 行情仅支持期货市场（Market.FUTURES）")
        super().__init__(market=market, config=config)
        self._api_factory = api_factory
        factory = runtime_factory or _TqSdkQuoteRuntime
        self._runtime = factory(
            self.config,
            market=market,
            api_factory=api_factory,
            on_quote=self._emit_quote,
            on_connection_change=self._emit_connection_change,
        )

    def connect(self) -> dict:
        if self._connected and self._runtime.state == "ready":
            return self._runtime.health()
        # 提前校验配置，避免启动空线程
        auth_user = str(
            self.config.get("tqsdk_auth_user") or self.config.get("auth_user") or ""
        ).strip()
        auth_password = str(
            self.config.get("tqsdk_auth_password")
            or self.config.get("auth_password")
            or ""
        )
        if not auth_user or not auth_password:
            raise SDKNotConfigured("TqSdk 行情需要快期账号密码（无需期货资金账户）")
        health = self._runtime.start()
        self._connected = True
        return health

    def disconnect(self) -> None:
        self._runtime.stop()
        self._connected = False
        self._emit_connection_change(False, "disconnect")

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        self._ensure_connected()
        return self._runtime.call("get_quote", symbol=symbol)

    def get_kline(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[KlineBar]:
        self._ensure_connected()
        return self._runtime.call(
            "get_kline",
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
        )

    def get_tick_trades(self, symbol: str, limit: int = 30) -> list[dict]:
        self._ensure_connected()
        return self._runtime.call(
            "get_tick_trades",
            symbol=symbol,
            limit=limit,
        )

    def subscribe_quotes(self, symbols: list[str]) -> None:
        self._ensure_connected()
        self._runtime.call("subscribe", symbols=list(symbols))

    def unsubscribe_quotes(self, symbols: list[str]) -> None:
        if not self._connected:
            return
        try:
            self._runtime.call("unsubscribe", symbols=list(symbols))
        except SDKConnectionFailed:
            return

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise SDKConnectionFailed("TqSdk 行情适配器未连接")
        # 重连窗口内线程仍存活，允许 call 排队等到恢复
        if self._runtime.state not in {"ready", "reconnecting"}:
            raise SDKConnectionFailed(
                f"TqSdk 行情适配器未就绪: state={self._runtime.state}"
            )
