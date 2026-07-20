from datetime import datetime
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models.ai_report import AiReport
from app.repositories.base import BaseRepository


class AiReportRepository(BaseRepository[AiReport]):
    model = AiReport

    def add_report(
        self,
        *,
        range_start: datetime,
        range_end: datetime,
        scope: dict,
        metrics: dict,
        content: str,
        content_format: str = "markdown",
        model_name: str = "rule_based",
        generated_at: datetime,
        metadata: dict | None = None,
    ) -> AiReport:
        row = AiReport(
            range_start=range_start,
            range_end=range_end,
            scope=scope,
            metrics=metrics,
            content=content,
            content_format=content_format,
            model_name=model_name,
            generated_at=generated_at,
            metadata_=metadata or {},
        )
        return self.add(row)

    def get_by_id(self, report_id: UUID) -> AiReport | None:
        return self.db.get(AiReport, report_id)

    def list_reports(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[AiReport], int]:
        q = self.db.query(AiReport)
        total = q.count()
        rows = q.order_by(desc(AiReport.generated_at)).offset(offset).limit(limit).all()
        return rows, total

    def update_metadata(self, report_id: UUID, patch: dict) -> AiReport | None:
        row = self.get_by_id(report_id)
        if row is None:
            return None
        meta = dict(row.metadata_ or {})
        meta.update(patch)
        row.metadata_ = meta
        self.db.flush()
        return row
