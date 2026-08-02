from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.core.config import settings
from app.services.system_service import SystemStateService

router = APIRouter(tags=["system"])


@router.get("/system/status")
def system_status(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = SystemStateService(db, correlation_id=correlation_id)
    payload = svc.get_status()
    # 将 WebSocket 鉴权令牌下发给前端；未配置时为空字符串（开发环境不鉴权）
    payload["ws_token"] = settings.ws_token
    return ok(payload, correlation_id=correlation_id)
