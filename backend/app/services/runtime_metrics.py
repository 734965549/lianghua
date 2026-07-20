"""进程内运行时指标：连续下单失败、SDK 断线起点、待同步订单队列。"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_consecutive_order_fail = 0
_sdk_disconnect_since: datetime | None = None
_sync_queue: set[str] = set()  # client_order_id


def record_order_submit_result(success: bool) -> int:
    global _consecutive_order_fail
    with _lock:
        if success:
            _consecutive_order_fail = 0
        else:
            _consecutive_order_fail += 1
        return _consecutive_order_fail


def get_consecutive_order_fail() -> int:
    with _lock:
        return _consecutive_order_fail


def reset_consecutive_order_fail() -> None:
    global _consecutive_order_fail
    with _lock:
        _consecutive_order_fail = 0


def mark_sdk_disconnected() -> None:
    global _sdk_disconnect_since
    with _lock:
        if _sdk_disconnect_since is None:
            _sdk_disconnect_since = datetime.now(timezone.utc)


def mark_sdk_connected() -> None:
    global _sdk_disconnect_since
    with _lock:
        _sdk_disconnect_since = None


def get_sdk_disconnect_since() -> datetime | None:
    with _lock:
        return _sdk_disconnect_since


def enqueue_order_sync(client_order_id: str) -> None:
    with _lock:
        _sync_queue.add(client_order_id)


def enqueue_orders_sync(client_order_ids: list[str]) -> None:
    with _lock:
        _sync_queue.update(client_order_ids)


def dequeue_order_sync(client_order_id: str) -> None:
    with _lock:
        _sync_queue.discard(client_order_id)


def list_sync_queue() -> list[str]:
    with _lock:
        return list(_sync_queue)


def clear_sync_queue() -> None:
    with _lock:
        _sync_queue.clear()


def reset_all_for_tests() -> None:
    """测试辅助：清空全部运行时指标。"""
    global _consecutive_order_fail, _sdk_disconnect_since
    with _lock:
        _consecutive_order_fail = 0
        _sdk_disconnect_since = None
        _sync_queue.clear()
