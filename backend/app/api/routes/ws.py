import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.ws_hub import ws_hub

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws_hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket 连接异常关闭", exc_info=True)
    finally:
        await ws_hub.disconnect(ws)
