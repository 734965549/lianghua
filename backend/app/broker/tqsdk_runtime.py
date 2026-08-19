"""TqSdk 单线程运行时：独占 TqApi，经命令队列对外服务。"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable

from app.broker.errors import (
    BrokerAuthenticationError,
    BrokerConfigurationError,
    BrokerLoginError,
    BrokerNativeRuntimeError,
    BrokerNotReady,
    BrokerRequestTimeout,
    BrokerSubmitOutcomeUnknown,
)
from app.broker.tqsdk_mapping import mask_account_id

logger = logging.getLogger(__name__)


@dataclass
class _Command:
    op: str
    payload: dict[str, Any] = field(default_factory=dict)
    future: Future = field(default_factory=Future)


def create_tq_api(config: dict) -> Any:
    """创建真实 TqApi；测试可注入替代工厂。"""
    try:
        from tqsdk import TqAccount, TqApi, TqAuth
    except ImportError as exc:  # pragma: no cover - 环境缺包
        raise BrokerConfigurationError(
            "未安装 tqsdk。请执行: pip install tqsdk==3.10.1"
        ) from exc

    broker_id = str(config.get("broker_id") or "").strip()
    account_id = str(config.get("account_id") or "").strip()
    password = str(config.get("password") or "")
    auth_user = str(config.get("auth_user") or "").strip()
    auth_password = str(config.get("auth_password") or "")

    if not broker_id:
        raise BrokerConfigurationError("TQSDK_BROKER_ID 未配置（期货公司标识）")
    if not account_id:
        raise BrokerConfigurationError("TQSDK_ACCOUNT_ID 未配置")
    if not password:
        raise BrokerConfigurationError("TQSDK_PASSWORD 未配置")
    if not auth_user:
        raise BrokerConfigurationError("TQSDK_AUTH_USER 未配置（天勤账号）")
    if not auth_password:
        raise BrokerConfigurationError("TQSDK_AUTH_PASSWORD 未配置（天勤密码）")

    auth = TqAuth(auth_user, auth_password)
    account = TqAccount(broker_id, account_id, password)
    logger.info(
        "TqSdk 创建 TqApi: broker_id=%s account=%s auth_user=%s",
        broker_id,
        mask_account_id(account_id),
        mask_account_id(auth_user),
    )
    return TqApi(account=account, auth=auth)


class TqSdkRuntime:
    """独占工作线程持有 TqApi，所有操作经有界队列提交。"""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_factory: Callable[[], Any] | None = None,
        on_order_change: Callable[[Any], None] | None = None,
        on_trade_change: Callable[[Any], None] | None = None,
        on_connection_change: Callable[[bool, str], None] | None = None,
    ):
        self.config = dict(config or {})
        self._api_factory = api_factory or (lambda: create_tq_api(self.config))
        self._on_order_change = on_order_change
        self._on_trade_change = on_trade_change
        self._on_connection_change = on_connection_change

        self._timeout = float(self.config.get("command_timeout_seconds", 10.0))
        queue_size = int(self.config.get("command_queue_size", 1000))
        self._commands: queue.Queue[_Command | None] = queue.Queue(maxsize=max(1, queue_size))

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._api: Any | None = None
        self._fatal: BaseException | None = None
        self._state = "init"  # init / connecting / ready / stopping / stopped / failed
        self._order_fingerprints: dict[str, tuple] = {}
        self._seen_trade_ids: set[str] = set()
        self._bootstrapped = False
        self._lock = threading.RLock()

    @property
    def state(self) -> str:
        return self._state

    def is_ready(self) -> bool:
        return self._state == "ready" and self._ready.is_set() and self._fatal is None

    def start(self, timeout: float | None = None) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self.is_ready():
                    return self.health()
                # 仍在连接中，落到下方等待
            else:
                self._stop.clear()
                self._ready.clear()
                self._fatal = None
                self._state = "connecting"
                self._thread = threading.Thread(
                    target=self._run,
                    name="tqsdk-runtime",
                    daemon=True,
                )
                self._thread.start()

        wait_s = float(timeout if timeout is not None else max(self._timeout * 3, 30.0))
        if not self._ready.wait(wait_s):
            self._state = "failed"
            raise BrokerNotReady("TqSdk 运行时启动超时")
        if self._fatal is not None:
            self._state = "failed"
            raise self._wrap_fatal(self._fatal)
        return self.health()

    def stop(self, timeout: float = 10.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                self._state = "stopped"
                return
            self._state = "stopping"
            self._stop.set()
            try:
                self._commands.put_nowait(None)
            except queue.Full:
                pass
        thread.join(timeout=timeout)
        with self._lock:
            if thread.is_alive():
                logger.warning("TqSdk 运行时线程未在超时内退出")
            self._thread = None
            self._state = "stopped"
            self._ready.clear()

    def call(self, op: str, *, timeout: float | None = None, **payload: Any) -> Any:
        if self._stop.is_set() and op not in {"health"}:
            raise BrokerNotReady("TqSdk 运行时已停止")
        if not self.is_ready() and op not in {"health"}:
            if self._fatal is not None:
                raise self._wrap_fatal(self._fatal)
            raise BrokerNotReady(f"TqSdk 运行时未就绪: state={self._state}")

        wait_s = float(timeout if timeout is not None else self._timeout)
        # 下单/撤单：给工作线程内层 wait 留出结束时间，优先返回「结果未知」而非 Future 竞态超时
        future_wait = wait_s
        if op in {"insert_order", "cancel_order"}:
            payload = {**payload, "wait_timeout": payload.get("wait_timeout", wait_s)}
            future_wait = wait_s + 2.0

        cmd = _Command(op=op, payload=payload)
        try:
            self._commands.put(cmd, timeout=1.0)
        except queue.Full as exc:
            raise BrokerNotReady("TqSdk 命令队列已满") from exc

        try:
            return cmd.future.result(timeout=future_wait)
        except TimeoutError as exc:
            # 下单/撤单超时：结果未知，禁止调用方自动重试
            if op in {"insert_order", "cancel_order"}:
                raise BrokerSubmitOutcomeUnknown(
                    f"TqSdk {op} 超时，结果未知，禁止自动重试，请查询对账"
                ) from exc
            raise BrokerRequestTimeout(f"TqSdk 命令超时: {op}") from exc

    def health(self) -> dict:
        return {
            "broker": "tqsdk",
            "runtime_state": self._state,
            "ready": self.is_ready(),
            "queue_size": self._commands.qsize(),
            "seen_trades": len(self._seen_trade_ids),
            "tracked_orders": len(self._order_fingerprints),
            "live_enabled": bool(self.config.get("live_enabled", False)),
            "account_masked": mask_account_id(str(self.config.get("account_id") or "")),
            "broker_id": str(self.config.get("broker_id") or ""),
        }

    def _run(self) -> None:
        try:
            self._api = self._api_factory()
            self._bootstrap_snapshot()
            self._state = "ready"
            self._ready.set()
            if self._on_connection_change:
                self._on_connection_change(True, "tqsdk ready")

            while not self._stop.is_set():
                self._drain_commands(max_items=32)
                api = self._api
                if api is None:
                    break
                # 短 deadline，保证命令及时处理；TqApi 要求持续 wait_update
                deadline = time.time() + 0.05
                try:
                    api.wait_update(deadline=deadline)
                except TypeError:
                    # 兼容旧签名 wait_update()
                    api.wait_update()
                except Exception as exc:
                    # wait_update 异常通常意味着连接问题；标记失败并退出
                    raise BrokerNativeRuntimeError(f"TqApi.wait_update 失败: {exc}") from exc
                self._poll_updates()
        except BaseException as exc:
            self._fatal = exc
            self._state = "failed"
            logger.exception("TqSdk 运行时失败: %s", exc)
            if self._on_connection_change:
                try:
                    self._on_connection_change(False, str(exc))
                except Exception:
                    pass
        finally:
            self._ready.set()
            self._close_api()
            if self._state != "failed":
                self._state = "stopped"
            if self._on_connection_change:
                try:
                    self._on_connection_change(False, "tqsdk stopped")
                except Exception:
                    pass

    def _bootstrap_snapshot(self) -> None:
        api = self._api
        assert api is not None
        # 触发账户/持仓/委托/成交订阅，并推进一次更新
        api.get_account()
        api.get_position()
        api.get_order()
        api.get_trade()
        deadline = time.time() + min(self._timeout, 5.0)
        try:
            api.wait_update(deadline=deadline)
        except TypeError:
            api.wait_update()
        # 初始化指纹，避免启动瞬间把历史委托/成交当新事件重复推送
        self._sync_fingerprints(initial=True)
        self._bootstrapped = True

    def _drain_commands(self, max_items: int = 32) -> None:
        for _ in range(max_items):
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                return
            if cmd is None:
                self._stop.set()
                return
            try:
                result = self._dispatch(cmd.op, cmd.payload)
            except BaseException as exc:
                cmd.future.set_exception(exc)
            else:
                cmd.future.set_result(result)

    def _dispatch(self, op: str, payload: dict[str, Any]) -> Any:
        api = self._api
        if api is None:
            raise BrokerNotReady("TqApi 未创建")

        if op == "health":
            return self.health()
        if op == "get_account":
            return api.get_account()
        if op == "get_positions":
            return api.get_position()
        if op == "get_orders":
            order_id = payload.get("order_id")
            return api.get_order(order_id) if order_id else api.get_order()
        if op == "get_trades":
            trade_id = payload.get("trade_id")
            return api.get_trade(trade_id) if trade_id else api.get_trade()
        if op == "insert_order":
            return self._insert_order(api, payload)
        if op == "cancel_order":
            return self._cancel_order(api, payload)
        if op == "raw":
            # 测试辅助
            fn = payload.get("fn")
            if not callable(fn):
                raise BrokerConfigurationError("raw 命令缺少 fn")
            return fn(api)
        raise BrokerConfigurationError(f"未知 TqSdk 命令: {op}")

    def _insert_order(self, api: Any, payload: dict[str, Any]) -> Any:
        kwargs = {
            "symbol": payload["symbol"],
            "direction": payload["direction"],
            "offset": payload["offset"],
            "volume": int(payload["volume"]),
            "limit_price": payload.get("limit_price"),
            "order_id": payload.get("order_id"),
        }
        # 去掉 None，避免覆盖默认值
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        try:
            order = api.insert_order(**kwargs)
        except Exception as exc:
            # 本地立刻失败：可视为未发出；若不确定则按未知处理
            msg = str(exc)
            if "认证" in msg or "auth" in msg.lower():
                raise BrokerAuthenticationError(f"TqSdk 报单认证失败: {exc}") from exc
            raise BrokerSubmitOutcomeUnknown(f"TqSdk 报单发送结果未知: {exc}") from exc

        order_id = str(getattr(order, "order_id", "") or kwargs.get("order_id") or "")
        deadline = time.time() + float(payload.get("wait_timeout") or self._timeout)
        while time.time() < deadline:
            try:
                api.wait_update(deadline=min(time.time() + 0.05, deadline))
            except TypeError:
                api.wait_update()
            self._poll_updates()
            status = str(getattr(order, "status", "") or "")
            # ALIVE / FINISHED / is_error 任一明确信号即可返回
            if status in {"ALIVE", "FINISHED"} or bool(getattr(order, "is_error", False)):
                return order
            # 有些实现先生成对象再在 wait_update 后填充 order_id
            if order_id and not getattr(order, "order_id", None):
                refreshed = api.get_order(order_id)
                if refreshed is not None:
                    order = refreshed
        raise BrokerSubmitOutcomeUnknown(
            f"TqSdk 报单 {order_id or payload.get('order_id')} 超时未确认，结果未知，禁止自动重试"
        )

    def _cancel_order(self, api: Any, payload: dict[str, Any]) -> Any:
        order_id = str(payload.get("order_id") or "").strip()
        if not order_id:
            raise BrokerConfigurationError("撤单缺少 order_id")
        order = api.get_order(order_id)
        if order is None:
            raise BrokerConfigurationError(f"未找到委托: {order_id}")
        try:
            api.cancel_order(order)
        except Exception as exc:
            raise BrokerSubmitOutcomeUnknown(f"TqSdk 撤单发送结果未知: {exc}") from exc

        deadline = time.time() + float(payload.get("wait_timeout") or self._timeout)
        while time.time() < deadline:
            try:
                api.wait_update(deadline=min(time.time() + 0.05, deadline))
            except TypeError:
                api.wait_update()
            self._poll_updates()
            status = str(getattr(order, "status", "") or "")
            if status == "FINISHED" or bool(getattr(order, "is_dead", False)):
                return order
        raise BrokerSubmitOutcomeUnknown(
            f"TqSdk 撤单 {order_id} 超时未确认，结果未知，需查询对账"
        )

    def _poll_updates(self) -> None:
        api = self._api
        if api is None:
            return
        try:
            orders = api.get_order()
            trades = api.get_trade()
        except Exception:
            return

        order_items = self._iter_entity(orders)
        for order_id, order in order_items:
            fp = (
                str(getattr(order, "status", "")),
                int(getattr(order, "volume_left", 0) or 0),
                int(getattr(order, "volume_orign", 0) or 0),
                bool(getattr(order, "is_error", False)),
            )
            prev = self._order_fingerprints.get(order_id)
            if prev != fp:
                self._order_fingerprints[order_id] = fp
                if self._bootstrapped and self._on_order_change:
                    try:
                        self._on_order_change(order)
                    except Exception:
                        logger.exception("TqSdk 订单回调失败")

        trade_items = self._iter_entity(trades)
        for trade_id, trade in trade_items:
            if trade_id in self._seen_trade_ids:
                continue
            self._seen_trade_ids.add(trade_id)
            if self._bootstrapped and self._on_trade_change:
                try:
                    self._on_trade_change(trade)
                except Exception:
                    logger.exception("TqSdk 成交回调失败")

    def _sync_fingerprints(self, *, initial: bool) -> None:
        api = self._api
        if api is None:
            return
        for order_id, order in self._iter_entity(api.get_order()):
            self._order_fingerprints[order_id] = (
                str(getattr(order, "status", "")),
                int(getattr(order, "volume_left", 0) or 0),
                int(getattr(order, "volume_orign", 0) or 0),
                bool(getattr(order, "is_error", False)),
            )
        for trade_id, _trade in self._iter_entity(api.get_trade()):
            self._seen_trade_ids.add(trade_id)
        if initial:
            logger.info(
                "TqSdk 初始快照: orders=%s trades=%s",
                len(self._order_fingerprints),
                len(self._seen_trade_ids),
            )

    @staticmethod
    def _iter_entity(entity: Any) -> list[tuple[str, Any]]:
        if entity is None:
            return []
        if isinstance(entity, dict):
            return [(str(k), v) for k, v in entity.items()]
        # 单个 Order/Trade 对象
        order_id = getattr(entity, "order_id", None)
        trade_id = getattr(entity, "trade_id", None)
        if trade_id is not None and order_id is None:
            return [(str(trade_id), entity)]
        if order_id is not None and not hasattr(entity, "items"):
            return [(str(order_id), entity)]
        try:
            return [(str(k), v) for k, v in entity.items()]
        except Exception:
            return []

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
            logger.debug("关闭 TqApi 异常", exc_info=True)

    @staticmethod
    def _wrap_fatal(exc: BaseException) -> BaseException:
        if isinstance(
            exc,
            (
                BrokerConfigurationError,
                BrokerAuthenticationError,
                BrokerLoginError,
                BrokerNotReady,
                BrokerNativeRuntimeError,
                BrokerSubmitOutcomeUnknown,
            ),
        ):
            return exc
        msg = str(exc)
        lower = msg.lower()
        if "认证" in msg or "auth" in lower or "appid" in lower:
            return BrokerAuthenticationError(f"TqSdk 认证/登录失败: {exc}")
        if "登录" in msg or "login" in lower:
            return BrokerLoginError(f"TqSdk 登录失败: {exc}")
        return BrokerNativeRuntimeError(f"TqSdk 运行时异常: {exc}")
