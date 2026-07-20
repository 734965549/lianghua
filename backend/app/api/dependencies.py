import uuid

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db


def get_correlation_id(request: Request) -> str:
    """每请求生成唯一 correlation_id，挂到 request.state。"""
    if not hasattr(request.state, "correlation_id"):
        request.state.correlation_id = f"req_{uuid.uuid4().hex[:16]}"
    return request.state.correlation_id


DbDep = Depends(get_db)
CidDep = Depends(get_correlation_id)
