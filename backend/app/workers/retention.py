"""数据保留策略：行情快照 1 年、系统异常日志 180 天，归档后写审计。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.system_config_repo import SystemConfigRepository
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_RETENTION_DAYS = 365
DEFAULT_SYSTEM_EVENT_RETENTION_DAYS = 180


def _int_config(repo: SystemConfigRepository, key: str, default: int) -> int:
    raw = (repo.get_value(key, "") or "").strip()
    if not raw:
        return default
    try:
        return max(int(raw), 1)
    except ValueError:
        logger.warning("无效配置 %s=%r，使用默认 %s", key, raw, default)
        return default


def run_retention_cleanup(db: Session, *, correlation_id: str = "retention") -> dict:
    """清理过期行情快照与非 critical 系统事件，并写审计日志。"""
    repo = SystemConfigRepository(db)
    snapshot_days = _int_config(repo, "market_snapshot_retention_days", DEFAULT_SNAPSHOT_RETENTION_DAYS)
    event_days = _int_config(repo, "system_event_retention_days", DEFAULT_SYSTEM_EVENT_RETENTION_DAYS)

    now = datetime.now(timezone.utc)
    snapshot_cutoff = now - timedelta(days=snapshot_days)
    event_cutoff = now - timedelta(days=event_days)

    snapshots_deleted = db.execute(
        text("DELETE FROM market_snapshots WHERE quote_time < :cutoff"),
        {"cutoff": snapshot_cutoff},
    ).rowcount

    events_deleted = db.execute(
        text(
            """
            DELETE FROM system_events
            WHERE event_time < :cutoff
              AND severity <> 'critical'
            """
        ),
        {"cutoff": event_cutoff},
    ).rowcount

    summary = {
        "snapshots_deleted": int(snapshots_deleted or 0),
        "events_deleted": int(events_deleted or 0),
        "snapshot_retention_days": snapshot_days,
        "event_retention_days": event_days,
        "snapshot_cutoff": snapshot_cutoff.isoformat(),
        "event_cutoff": event_cutoff.isoformat(),
    }

    AuditService(db, correlation_id=correlation_id).log(
        action="data_retention_cleanup",
        module="system",
        object_type="retention",
        object_id="market_snapshots+system_events",
        result="success",
        reason="定时数据归档清理",
        request_summary=summary,
    )
    db.commit()
    logger.info(
        "数据保留清理完成 snapshots=%s events=%s",
        summary["snapshots_deleted"],
        summary["events_deleted"],
    )
    return summary
