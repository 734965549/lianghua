"""缺口修复相关单测：debug 环境过滤、策略启停时间戳、风控 confirm/reason。"""

from app.api.response import fail
from app.core.config import settings


def test_fail_strips_debug_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    body = fail("X", "msg", debug="secret")
    assert body.error is not None
    assert body.error.debug is None


def test_fail_keeps_debug_in_dev(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "dev")
    body = fail("X", "msg", debug="secret")
    assert body.error is not None
    assert body.error.debug == "secret"
