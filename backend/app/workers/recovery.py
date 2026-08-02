"""启动恢复：保持熔断状态、排队未完结订单、策略标记待确认。"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.order_repo import OrderRepository
from app.repositories.data_sync_log_repo import DataSyncLogRepository
from app.repositories.risk_repo import RiskRepository
from app.repositories.strategy_repo import StrategyRunRepository
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Severity, StrategyRunStatus, SystemStatus
from app.services import runtime_metrics
from app.services.system_service import SystemStateService

logger = logging.getLogger(__name__)


def _check_migration_version(db: Session) -> str | None:
    try:
        row = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
        return row[0] if row else None
    except Exception:
        logger.warning("无法读取 alembic_version", exc_info=True)
        return None


def recover_on_startup(db: Session, *, correlation_id: str = "startup") -> dict:
    """应用启动恢复流程。

    1. 检查迁移版本
    2. 加载系统/风控配置
    3. 读系统状态：circuit_breaker / emergency_stopped 保持不解除
    4. 未完结订单加入同步队列
    5. 上次运行中的策略标记 pending_confirm，不自动启动
    """
    migration = _check_migration_version(db)
    RiskRepository(db).ensure_config()

    system = SystemStateService(db, correlation_id=correlation_id)
    system.startup_ready()
    status = system.get_status()

    open_orders = OrderRepository(db).list_open_orders(limit=500)
    client_ids = [o.client_order_id for o in open_orders]
    runtime_metrics.enqueue_orders_sync(client_ids)

    run_repo = StrategyRunRepository(db)
    running_rows = (
        db.query(run_repo.model)
        .filter(run_repo.model.status == StrategyRunStatus.RUNNING)
        .all()
    )
    pending_strategies: list[str] = []
    for row in running_rows:
        run_repo.finish_run(
            row.id,
            status=StrategyRunStatus.PENDING_CONFIRM,
            reason="进程重启，需前端确认后重新启动",
        )
        pending_strategies.append(row.strategy_id)

    orphan_data_tasks = DataSyncLogRepository(db).recover_orphans()

    events = SystemEventRepository(db)
    events.add(
        module="system",
        event_code="STARTUP_RECOVERY",
        message="启动恢复完成",
        severity=Severity.INFO,
        payload={
            "migration": migration,
            "system_status": status["status"],
            "open_orders_queued": len(client_ids),
            "pending_confirm_strategies": pending_strategies,
            "orphan_data_tasks_recovered": [str(task_id) for task_id in orphan_data_tasks],
            "breaker_preserved": status["status"]
            in {
                SystemStatus.CIRCUIT_BREAKER.value,
                SystemStatus.EMERGENCY_STOPPED.value,
            },
        },
    )

    result = {
        "migration": migration,
        "system_status": status["status"],
        "open_orders_queued": client_ids,
        "pending_confirm_strategies": pending_strategies,
        "orphan_data_tasks_recovered": [str(task_id) for task_id in orphan_data_tasks],
    }
    logger.info(
        "启动恢复完成 status=%s queued=%d pending_strategies=%s",
        status["status"],
        len(client_ids),
        pending_strategies,
    )
    return result
