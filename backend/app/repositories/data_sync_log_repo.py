import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.data_sync_log import DataSyncLog
from app.repositories.base import BaseRepository


class DataSyncLogRepository(BaseRepository[DataSyncLog]):
    model = DataSyncLog

    def create_task(
        self,
        *,
        task_type: str,
        symbols: list[str],
        intervals: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> DataSyncLog:
        row = DataSyncLog(
            task_type=task_type,
            status="pending",
            symbols=symbols,
            intervals=intervals,
            start_date=start_date,
            end_date=end_date,
            progress={"done": 0, "total": len(symbols) * max(len(intervals), 1), "items": {}},
        )
        return self.add(row)

    def mark_running(self, task_id: uuid.UUID) -> DataSyncLog | None:
        row = self.get(task_id)
        if row is None:
            return None
        row.status = "running"
        row.started_at = datetime.now(timezone.utc)
        self.db.flush()
        return row

    def update_progress(self, task_id: uuid.UUID, progress: dict) -> DataSyncLog | None:
        row = self.get(task_id)
        if row is None:
            return None
        row.progress = progress
        self.db.flush()
        return row

    def mark_done(self, task_id: uuid.UUID) -> DataSyncLog | None:
        row = self.get(task_id)
        if row is None:
            return None
        row.status = "done"
        row.finished_at = datetime.now(timezone.utc)
        self.db.flush()
        return row

    def mark_failed(self, task_id: uuid.UUID, error: str) -> DataSyncLog | None:
        row = self.get(task_id)
        if row is None:
            return None
        row.status = "failed"
        row.error_message = error
        row.finished_at = datetime.now(timezone.utc)
        self.db.flush()
        return row

    def mark_cancelled(self, task_id: uuid.UUID, reason: str) -> DataSyncLog | None:
        row = self.get(task_id)
        if row is None:
            return None
        row.status = "cancelled"
        row.error_message = reason
        row.finished_at = datetime.now(timezone.utc)
        self.db.flush()
        return row

    def recover_orphans(self, reason: str = "服务重启，未完成任务已恢复为失败") -> list[uuid.UUID]:
        rows = (
            self.db.query(DataSyncLog)
            .filter(DataSyncLog.status.in_(["pending", "running", "cancelling"]))
            .all()
        )
        recovered: list[uuid.UUID] = []
        for row in rows:
            row.status = "failed"
            row.error_message = reason
            row.finished_at = datetime.now(timezone.utc)
            progress = dict(row.progress or {})
            progress.update({"status": "failed", "error": reason})
            row.progress = progress
            recovered.append(row.id)
        self.db.flush()
        return recovered

    def list_recent(self, limit: int = 20) -> list[DataSyncLog]:
        return (
            self.db.query(DataSyncLog)
            .order_by(DataSyncLog.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_latest_running(self) -> DataSyncLog | None:
        return (
            self.db.query(DataSyncLog)
            .filter(DataSyncLog.status.in_(["pending", "running"]))
            .order_by(DataSyncLog.created_at.desc())
            .first()
        )
