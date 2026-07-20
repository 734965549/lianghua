import pytest

from app.api.response import BizError
from app.schemas.enums import SystemStatus
from app.services.system_service import SystemStateService


@pytest.mark.integration
def test_valid_transition_ready_to_trading(db, reset_system_state):
    svc = SystemStateService(db, correlation_id="test_valid")
    row = svc.transition(SystemStatus.TRADING, reason="用户启动")
    db.commit()
    assert row.status == SystemStatus.TRADING
    assert row.status_reason == "用户启动"


@pytest.mark.integration
def test_valid_transition_trading_to_paused(db, reset_system_state):
    svc = SystemStateService(db, correlation_id="test_valid2")
    svc.transition(SystemStatus.TRADING, reason="启动")
    svc.transition(SystemStatus.PAUSED, reason="用户暂停")
    db.commit()
    status = svc.get_status()
    assert status["status"] == SystemStatus.PAUSED.value


@pytest.mark.integration
def test_invalid_transition_trading_to_ready(db, reset_system_state):
    svc = SystemStateService(db, correlation_id="test_invalid")
    svc.transition(SystemStatus.TRADING, reason="启动")
    with pytest.raises(BizError) as exc:
        svc.transition(SystemStatus.READY, reason="非法")
    assert exc.value.code == "RISK_INVALID_STATE_TRANSITION"


@pytest.mark.integration
def test_offline_can_recover_to_ready(db, reset_system_state):
    svc = SystemStateService(db, correlation_id="test_offline")
    svc.transition(SystemStatus.OFFLINE, reason="shutdown")
    db.commit()
    row = svc.transition(SystemStatus.READY, reason="startup recover")
    db.commit()
    assert row.status == SystemStatus.READY


@pytest.mark.integration
def test_invalid_transition_emergency_to_ready(db, reset_system_state):
    svc = SystemStateService(db, correlation_id="test_emergency")
    svc.transition(SystemStatus.EMERGENCY_STOPPED, reason="stop")
    with pytest.raises(BizError) as exc:
        svc.transition(SystemStatus.READY, reason="illegal")
    assert exc.value.code == "RISK_INVALID_STATE_TRANSITION"
