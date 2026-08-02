import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class WsConnection:
    """维护单个 WebSocket 连接及其订阅主题。"""

    def __init__(self, ws: WebSocket, topics: set[str] | None = None):
        self.ws = ws
        self.topics: set[str] = set(topics or [])

    def subscribe(self, topics: list[str]) -> None:
        self.topics.update(topics)

    def unsubscribe(self, topics: list[str]) -> None:
        self.topics.difference_update(topics)

    def is_subscribed(self, topic: str) -> bool:
        return topic in self.topics


class WsHub:
    """进程内 WebSocket 广播 Hub，支持主题过滤。"""

    def __init__(self):
        # WebSocket -> WsConnection
        self._connections: dict[WebSocket, WsConnection] = {}
        # 使用线程锁而非 asyncio.Lock，避免跨事件循环/线程广播时绑定到不同 loop
        self._lock = threading.Lock()

    async def connect(self, ws: WebSocket, topics: list[str] | None = None) -> None:
        await ws.accept()
        with self._lock:
            self._connections[ws] = WsConnection(ws, set(topics or []))

    async def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self._connections.pop(ws, None)

    def subscribe(self, ws: WebSocket, topics: list[str]) -> None:
        with self._lock:
            conn = self._connections.get(ws)
            if conn is not None:
                conn.subscribe(topics)

    def unsubscribe(self, ws: WebSocket, topics: list[str]) -> None:
        with self._lock:
            conn = self._connections.get(ws)
            if conn is not None:
                conn.unsubscribe(topics)

    async def broadcast(self, topic: str, data: dict[str, Any], correlation_id: str = "") -> None:
        envelope = {
            "topic": topic,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "data": data,
            "correlation_id": correlation_id,
        }
        text = json.dumps(envelope, default=str)
        with self._lock:
            connections = list(self._connections.values())
        dead: list[WebSocket] = []
        for conn in connections:
            if not conn.is_subscribed(topic):
                continue
            try:
                await conn.ws.send_text(text)
            except Exception:
                dead.append(conn.ws)
        if dead:
            with self._lock:
                for ws in dead:
                    self._connections.pop(ws, None)

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)


ws_hub = WsHub()


def broadcast_sync(topic: str, data: dict, correlation_id: str = "") -> None:
    """从同步线程（如 SDK 回调）安全广播。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_hub.broadcast(topic, data, correlation_id=correlation_id))
    except RuntimeError:
        asyncio.run(ws_hub.broadcast(topic, data, correlation_id=correlation_id))
