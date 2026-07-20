"""strategy_service 单元与集成测试。"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.response import BizError
from app.repositories.strategy_repo import StrategyRepository, StrategyRunRepository
from app.schemas.enums import StrategyRunStatus, SystemStatus
from app.services.strategy_service import strategy_service
from app.services.system_service import SystemStateService
from app.strategies.registry import import_samples


@pytest.fixture(autouse=True)
def _reset_running():
    strategy_service._running.clear()
    yield
    strategy_service._running.clear()


@pytest.mark.unit
def test_list_strategies_includes_running_flag(db):
    import_samples()
    strategy_service.ensure_definitions(db)
    db.commit()
    items = strategy_service.list_strategies(db)
    assert any(i["strategy_id"] == "ma_cross" for i in items)
    ma = next(i for i in items if i["strategy_id"] == "ma_cross")
    assert ma["running"] is False
    assert "parameters_schema" in ma


@pytest.mark.unit
def test_get_strategy_not_found(db):
    import_samples()
    with pytest.raises(BizError) as exc:
        strategy_service.get_strategy(db, "nonexistent_strategy")
    assert exc.value.code == "STRATEGY_NOT_FOUND"


@pytest.mark.unit
def test_update_parameters(db):
    import_samples()
    strategy_service.ensure_definitions(db)
    db.commit()
    result = strategy_service.update_parameters(
        db,
        "ma_cross",
        {"symbols": ["600000.SH"], "fast": 3, "slow": 15, "interval": "1m", "quantity": "200"},
        correlation_id="test_update_params",
    )
    db.commit()
    assert result["parameters"]["fast"] == 3
    assert result["parameters"]["slow"] == 15


@pytest.mark.integration
def test_start_stop_strategy(db, reset_system_state):
    import_samples()
    strategy_service.ensure_definitions(db)
    system = SystemStateService(db, correlation_id="test_start_stop")
    system.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    started = strategy_service.start(
        db,
        "ma_cross",
        symbols=["600000.SH"],
        confirm=True,
        correlation_id="test_start_stop",
    )
    db.commit()
    assert started["status"] == "running"
    assert "run_id" in started
    assert "ma_cross" in strategy_service._running

    run = StrategyRunRepository(db).get_active_run("ma_cross")
    assert run is not None
    assert run.status == StrategyRunStatus.RUNNING

    stopped = strategy_service.stop(db, "ma_cross", reason="测试停止", correlation_id="test_start_stop")
    db.commit()
    assert stopped["status"] == "stopped"
    assert "ma_cross" not in strategy_service._running


@pytest.mark.integration
def test_start_requires_confirm(db, reset_system_state):
    import_samples()
    strategy_service.ensure_definitions(db)
    system = SystemStateService(db, correlation_id="test_confirm")
    system.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    with pytest.raises(BizError) as exc:
        strategy_service.start(db, "ma_cross", confirm=False, correlation_id="test_confirm")
    assert exc.value.code == "STRATEGY_CONFIRM_REQUIRED"


@pytest.mark.integration
def test_start_blocked_when_system_stopped(db, reset_system_state):
    import_samples()
    strategy_service.ensure_definitions(db)
    system = SystemStateService(db, correlation_id="test_blocked")
    system.transition(SystemStatus.EMERGENCY_STOPPED, reason="test")
    db.commit()

    with pytest.raises(BizError) as exc:
        strategy_service.start(db, "ma_cross", confirm=True, correlation_id="test_blocked")
    assert exc.value.code == "RISK_SYSTEM_STOPPED"


@pytest.mark.unit
def test_ensure_definitions_idempotent(db):
    import_samples()
    strategy_service.ensure_definitions(db)
    db.commit()
    count_before = len(StrategyRepository(db).list_all())
    strategy_service.ensure_definitions(db)
    db.commit()
    assert len(StrategyRepository(db).list_all()) == count_before
