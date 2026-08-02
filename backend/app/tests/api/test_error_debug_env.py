"""缺口修复相关单测：debug 环境过滤、策略启停时间戳、风控 confirm/reason。"""

from app.api.response import fail
from app.core.config import settings
from app.sdk.base import SDKDisconnected


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


def test_adapter_disconnect_is_service_unavailable(client, monkeypatch):
    def disconnected(*_args, **_kwargs):
        raise SDKDisconnected("CF0 暂无行情")

    monkeypatch.setattr(
        "app.api.routes.quotes.market_service.get_quote",
        disconnected,
    )

    response = client.get("/api/quotes/futures/CF0")
    payload = response.json()

    assert response.status_code == 503
    assert payload["success"] is False
    assert payload["error"]["code"] == "SDK_DISCONNECTED"
    assert payload["error"]["message"] == "CF0 暂无行情"
    assert payload["error"]["retryable"] is True
