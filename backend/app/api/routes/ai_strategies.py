"""AI 策略定义生成 API 路由。

POST /api/ai/strategies/generate — 自然语言 → definition JSON（不自动落库）。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import ok
from app.services.ai_strategy_service import AiStrategyService

router = APIRouter(tags=["ai"])


class GenerateStrategyBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000, description="自然语言策略描述")
    market: str | None = Field(default=None, description="stock 或 futures，可选")
    interval: str | None = Field(default=None, description="K线周期偏好，可选")


@router.post("/ai/strategies/generate")
def generate_strategy_from_prompt(
    body: GenerateStrategyBody,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = AiStrategyService(db, correlation_id=correlation_id)
    result = svc.generate(body.prompt, market=body.market, interval=body.interval)
    db.commit()
    return ok(result, correlation_id=correlation_id)
