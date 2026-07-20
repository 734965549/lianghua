from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db
from app.api.response import BizError, ok
from app.services.ai_report_service import AiReportService

router = APIRouter(tags=["ai"])


class GenerateReportBody(BaseModel):
    range_start: datetime
    range_end: datetime
    strategy_ids: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)


class FeedbackBody(BaseModel):
    useful: bool


@router.get("/ai/reports")
def list_reports(
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    svc = AiReportService(db, correlation_id=correlation_id)
    items, total = svc.list_reports(page=page, page_size=page_size)
    return ok(
        {"items": items, "page": page, "page_size": page_size, "total": total},
        correlation_id=correlation_id,
    )


@router.get("/ai/reports/{report_id}")
def get_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = AiReportService(db, correlation_id=correlation_id)
    row = svc.get_report(report_id)
    if row is None:
        raise BizError("AI_REPORT_NOT_FOUND", f"报告不存在: {report_id}", status=404)
    return ok(row, correlation_id=correlation_id)


@router.post("/ai/reports")
def generate_report(
    body: GenerateReportBody,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    if body.range_end < body.range_start:
        raise BizError("AI_REPORT_INVALID_RANGE", "结束时间不能早于开始时间")
    svc = AiReportService(db, correlation_id=correlation_id)
    try:
        result = svc.generate(
            range_start=body.range_start,
            range_end=body.range_end,
            strategy_ids=body.strategy_ids or None,
            markets=body.markets or None,
            symbols=body.symbols or None,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise BizError("AI_REPORT_FAILED", f"报告生成失败: {exc}", retryable=True) from exc
    return ok(result, correlation_id=correlation_id)


@router.post("/ai/reports/{report_id}/feedback")
def report_feedback(
    report_id: UUID,
    body: FeedbackBody,
    db: Session = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id),
):
    svc = AiReportService(db, correlation_id=correlation_id)
    row = svc.mark_feedback(report_id, body.useful)
    if row is None:
        raise BizError("AI_REPORT_NOT_FOUND", f"报告不存在: {report_id}", status=404)
    db.commit()
    return ok(row, correlation_id=correlation_id)
