import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class WsHub:
    """进程内 WebSocket 广播 Hub。"""

    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, topic: str, data: dict[str, Any], correlation_id: str = "") -> None:
        envelope = {
            "topic": topic,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "data": data,
            "correlation_id": correlation_id,
        }
        text = json.dumps(envelope, default=str)
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


ws_hub = WsHub()


def broadcast_sync(topic: str, data: dict, correlation_id: str = "") -> None:
    """从同步线程（如 SDK 回调）安全广播。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_hub.broadcast(topic, data, correlation_id=correlation_id))
    except RuntimeError:
        asyncio.run(ws_hub.broadcast(topic, data, correlation_id=correlation_id))
