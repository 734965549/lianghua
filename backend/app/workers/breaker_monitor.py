"""熔断条件周期检查任务。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.services.risk_service import RiskService

logger = logging.getLogger(__name__)


def check_breaker_conditions(db: Session) -> str | None:
    """每周期检查熔断条件，命中则触发。返回触发原因或 None。"""
    svc = RiskService(db, correlation_id="breaker_monitor")
    reason = svc.check_breaker_conditions()
    if reason:
        db.commit()
        logger.warning("熔断监控触发: %s", reason)
    return reason
