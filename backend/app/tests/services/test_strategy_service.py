"""strategy_service 单元与集成测试。"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.response import BizError
from app.repositories.strategy_repo import StrategyRepository, StrategyRunRepository
from app.schemas.enums import Market, StrategyRunStatus, SystemStatus
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


@pytest.mark.integration
def test_strategy_error_auto_stop(db, reset_system_state, monkeypatch):
    """连续异常达阈值后写 system_events 并从运行列表移除。"""
    from app.db.models.system_event import SystemEvent
    from app.repositories.system_config_repo import SystemConfigRepository
    from app.sdk.models import QuoteSnapshot

    import_samples()
    strategy_service.ensure_definitions(db)
    SystemConfigRepository(db).upsert(
        config_key="strategy_error_limit",
        value="2",
        description="测试用策略异常阈值",
    )
    system = SystemStateService(db, correlation_id="test_err")
    system.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    strategy_service.start(
        db,
        "ma_cross",
        symbols=["600000.SH"],
        confirm=True,
        correlation_id="test_err",
    )
    db.commit()
    assert "ma_cross" in strategy_service._running

    running = strategy_service._running["ma_cross"]

    def boom_quote(quote):
        raise RuntimeError("boom")

    monkeypatch.setattr(running.instance, "on_quote", boom_quote)

    quote = QuoteSnapshot(
        symbol="600000.SH",
        market=Market.STOCK,
        last_price=Decimal("10"),
        change_rate=Decimal("0"),
        volume=Decimal("100"),
        quote_time=datetime.now(timezone.utc),
    )
    strategy_service.dispatch_quote(quote)
    strategy_service.dispatch_quote(quote)

    assert "ma_cross" not in strategy_service._running
    db.expire_all()
    events = (
        db.query(SystemEvent)
        .filter(SystemEvent.event_code.in_(["STRATEGY_ERROR", "STRATEGY_AUTO_STOPPED"]))
        .all()
    )
    assert any(e.event_code == "STRATEGY_ERROR" for e in events)
    assert any(e.event_code == "STRATEGY_AUTO_STOPPED" for e in events)
    run = StrategyRunRepository(db).list_runs(strategy_id="ma_cross", limit=1)[0][0]
    assert run.status == StrategyRunStatus.FAILED


@pytest.mark.unit
def test_ensure_definitions_idempotent(db):
    import_samples()
    strategy_service.ensure_definitions(db)
    db.commit()
    count_before = len(StrategyRepository(db).list_all())
    strategy_service.ensure_definitions(db)
    db.commit()
    assert len(StrategyRepository(db).list_all()) == count_before
