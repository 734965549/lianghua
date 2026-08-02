import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.api.ws_hub import ws_hub
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class WSError(Exception):
    def __init__(self, code: int, reason: str):
        self.code = code
        self.reason = reason


def _check_auth(ws: WebSocket) -> None:
    """校验 WebSocket 连接令牌；未配置 ws_token 时开发环境放行。"""
    token = settings.ws_token
    if not token:
        return
    query_token = ws.query_params.get("token", "")
    if query_token != token:
        raise WSError(status.WS_1008_POLICY_VIOLATION, "WebSocket token 无效")


def _parse_topics(payload: str) -> list[str]:
    try:
        msg = json.loads(payload)
    except Exception as exc:
        raise ValueError("消息必须是 JSON") from exc
    if not isinstance(msg, dict):
        raise ValueError("消息必须是 JSON 对象")
    action = msg.get("action")
    topics = msg.get("topics", [])
    if action not in ("subscribe", "unsubscribe"):
        raise ValueError("action 必须是 subscribe 或 unsubscribe")
    if isinstance(topics, str):
        topics = [topics]
    if not isinstance(topics, list) or not all(isinstance(t, str) for t in topics):
        raise ValueError("topics 必须是字符串列表")
    return action, topics


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    try:
        _check_auth(ws)
    except WSError as exc:
        await ws.close(code=exc.code, reason=exc.reason)
        return

    # 默认订阅系统状态，前端按需再订阅行情/订单/成交等主题
    initial_topics = ["system.status"]
    await ws_hub.connect(ws, topics=initial_topics)
    try:
        while True:
            text = await ws.receive_text()
            try:
                action, topics = _parse_topics(text)
            except ValueError as exc:
                await ws.send_text(json.dumps({"error": str(exc)}))
                continue
            if action == "subscribe":
                ws_hub.subscribe(ws, topics)
                await ws.send_text(json.dumps({"subscribed": topics}))
            else:
                ws_hub.unsubscribe(ws, topics)
                await ws.send_text(json.dumps({"unsubscribed": topics}))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket 连接异常关闭", exc_info=True)
    finally:
        await ws_hub.disconnect(ws)
