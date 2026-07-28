"""数据保留清理与 audit_logs 只追加保护。"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.models.audit_log import AuditLog
from app.db.models.market_snapshot import MarketSnapshot
from app.db.models.system_event import SystemEvent
from app.repositories.system_config_repo import SystemConfigRepository
from app.schemas.enums import Market, Severity
from app.services.audit_service import AuditService
from app.workers.retention import run_retention_cleanup


@pytest.mark.integration
def test_retention_cleanup_deletes_old_rows_and_audits(db):
    now = datetime.now(timezone.utc)
    db.add(
        MarketSnapshot(
            market=Market.STOCK,
            symbol="600000.SH",
            last_price=Decimal("10"),
            change_rate=Decimal("0"),
            volume=Decimal("1"),
            quote_time=now - timedelta(days=400),
        )
    )
    db.add(
        MarketSnapshot(
            market=Market.STOCK,
            symbol="600000.SH",
            last_price=Decimal("11"),
            change_rate=Decimal("0"),
            volume=Decimal("1"),
            quote_time=now - timedelta(days=1),
        )
    )
    db.add(
        SystemEvent(
            module="system",
            event_code="OLD_ERROR",
            message="old",
            severity=Severity.ERROR,
            event_time=now - timedelta(days=200),
        )
    )
    db.add(
        SystemEvent(
            module="system",
            event_code="OLD_CRITICAL",
            message="keep",
            severity=Severity.CRITICAL,
            event_time=now - timedelta(days=200),
        )
    )
    db.commit()

    summary = run_retention_cleanup(db, correlation_id="test_retention")
    assert summary["snapshots_deleted"] >= 1
    assert summary["events_deleted"] >= 1

    remaining_snaps = db.query(MarketSnapshot).count()
    assert remaining_snaps == 1
    critical = (
        db.query(SystemEvent).filter(SystemEvent.event_code == "OLD_CRITICAL").count()
    )
    assert critical == 1
    assert db.query(SystemEvent).filter(SystemEvent.event_code == "OLD_ERROR").count() == 0

    audits = (
        db.query(AuditLog)
        .filter(AuditLog.action == "data_retention_cleanup")
        .count()
    )
    assert audits >= 1


@pytest.mark.integration
def test_audit_logs_reject_update_and_delete(db):
    AuditService(db, correlation_id="test_append").log(
        action="append_only_probe",
        module="test",
        result="success",
    )
    db.commit()
    row = db.query(AuditLog).filter(AuditLog.action == "append_only_probe").one()

    with pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE audit_logs SET reason = 'hack' WHERE id = :id"),
            {"id": row.id},
        )
        db.commit()
    db.rollback()

    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": row.id})
        db.commit()
    db.rollback()

    assert db.query(AuditLog).filter(AuditLog.id == row.id).count() == 1


@pytest.mark.integration
def test_updated_at_trigger_on_native_sql(db):
    SystemConfigRepository(db).upsert(
        config_key="trigger_probe",
        value="v1",
        description="probe",
    )
    db.commit()
    row = SystemConfigRepository(db).get_by_key("trigger_probe")
    before = row.updated_at

    db.execute(
        text("UPDATE system_configs SET config_value = 'v2' WHERE config_key = 'trigger_probe'")
    )
    db.commit()
    db.refresh(row)
    assert row.config_value == "v2"
    assert row.updated_at >= before
