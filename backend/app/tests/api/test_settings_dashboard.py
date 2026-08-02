"""设置、仪表盘等 API 集成测试。"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.models.system_config import SystemConfig
from app.main import app
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.sdk.models import QuoteSnapshot
from app.services.market_service import market_service
from app.services.settings_service import SettingsService


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.integration
def test_get_settings(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "database" in body["data"]
    assert "stock_sdk" in body["data"]
    assert "sensitive_fields" in body["data"]
    assert "database.url" in body["data"]["sensitive_fields"]
    provider_ids = {
        item["id"] for item in body["data"]["market_data"]["providers"]
    }
    assert {"akshare", "tdx", "ifind", "tushare_pro", "rqdata", "wind", "mock"} <= provider_ids


@pytest.mark.integration
def test_update_settings_backup_dir(client):
    resp = client.put("/api/settings", json={"backup_dir": "D:/lianghua/backups"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["backup_dir"] == "D:/lianghua/backups"


@pytest.mark.integration
def test_test_database(client):
    resp = client.post("/api/settings/test-database", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["ok"] is True
    assert "server_version" in body["data"]


@pytest.mark.integration
def test_test_sdk_mock(client):
    resp = client.post("/api/settings/test-sdk", json={"market": "stock"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["ok"] is True


@pytest.mark.integration
def test_dashboard(client):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "system_status" in body["data"]
    assert "latest_alerts" in body["data"]


@pytest.mark.integration
def test_quote_health_endpoint(client):
    resp = client.get("/api/quotes/health?targets=stock:600000.SH")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["items"][0]["symbol"] == "600000.SH"
    assert body["data"]["state"] in {
        "not_monitored",
        "healthy",
        "market_closed",
        "feed_stale",
        "source_disconnected",
        "subscription_disconnected",
    }
    assert isinstance(body["data"]["items"], list)


@pytest.mark.integration
def test_system_status(client):
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "status" in body["data"]


@pytest.mark.integration
def test_logs_audit(client):
    resp = client.get("/api/logs/audit?page=1&page_size=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "items" in body["data"]


@pytest.mark.integration
def test_logs_events(client):
    resp = client.get("/api/logs/system-events?page=1&page_size=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "items" in body["data"]


@pytest.mark.integration
def test_update_settings_stock_sdk(client):
    resp = client.put(
        "/api/settings",
        json={
            "stock_sdk": {"path": "C:/ths/stock", "account": "TEST001"},
            "ai": {"provider": "openai", "model": "gpt-4o-mini"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["stock_sdk"]["path"] == "C:/ths/stock"


@pytest.mark.integration
def test_update_ai_settings_encrypts_key_and_returns_runtime_fields(client, db, monkeypatch):
    ai_keys = ["ai_provider", "ai_api_key", "ai_base_url", "ai_model"]
    db.query(SystemConfig).filter(SystemConfig.config_key.in_(ai_keys)).delete(
        synchronize_session=False
    )
    db.commit()
    monkeypatch.setattr(settings, "ai_provider", "")
    monkeypatch.setattr(settings, "ai_api_key", "")
    monkeypatch.setattr(settings, "ai_base_url", "")
    monkeypatch.setattr(settings, "ai_model", "gpt-4o-mini")

    try:
        resp = client.put(
            "/api/settings",
            json={
                "ai": {
                    "provider": "openai",
                    "api_key": "test-secret-key",
                    "base_url": "https://ai.example/v1",
                    "model": "test-model",
                }
            },
        )
        assert resp.status_code == 200
        ai = resp.json()["data"]["ai"]
        assert ai == {
            "provider": "openai",
            "base_url": "https://ai.example/v1",
            "model": "test-model",
            "configured": True,
        }

        key_row = db.query(SystemConfig).filter_by(config_key="ai_api_key").one()
        assert key_row.is_sensitive is True
        assert key_row.config_value == ""
        assert key_row.encrypted_value
        assert b"test-secret-key" not in key_row.encrypted_value
    finally:
        db.query(SystemConfig).filter(SystemConfig.config_key.in_(ai_keys)).delete(
            synchronize_session=False
        )
        db.commit()


@pytest.mark.integration
def test_ai_connection_route(client, monkeypatch):
    monkeypatch.setattr(
        SettingsService,
        "test_ai",
        lambda self, overrides=None: {
            "ok": True,
            "provider": (overrides or {}).get("provider", "openai"),
            "model": (overrides or {}).get("model", "gpt-4o-mini"),
            "model_available": True,
            "latency_ms": 12,
        },
    )

    resp = client.post(
        "/api/settings/test-ai",
        json={"ai": {"provider": "openai", "model": "gpt-4o-mini"}},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["ok"] is True


@pytest.mark.integration
def test_update_ifind_settings_encrypts_password(client, db, monkeypatch):
    market_keys = [
        "quote_provider",
        "ifind_username",
        "ifind_password",
        "ifind_poll_seconds",
    ]
    db.query(SystemConfig).filter(SystemConfig.config_key.in_(market_keys)).delete(
        synchronize_session=False
    )
    db.commit()
    monkeypatch.setattr(market_service, "reconfigure", lambda: None)
    monkeypatch.setattr(settings, "quote_provider", "mock")
    monkeypatch.setattr(settings, "ifind_username", "")
    monkeypatch.setattr(settings, "ifind_password", "")

    try:
        resp = client.put(
            "/api/settings",
            json={
                "market_data": {
                    "provider": "ifind",
                    "ifind_username": "demo-user",
                    "ifind_password": "demo-secret",
                    "ifind_poll_seconds": 5,
                }
            },
        )
        assert resp.status_code == 200
        market_data = resp.json()["data"]["market_data"]
        assert market_data["provider"] == "ifind"
        assert market_data["configured"] is True
        assert market_data["ifind_username_ref"] == "demo-user"
        assert market_data["ifind_credentials_configured"] is True
        assert "ifind_password" not in market_data

        password_row = db.query(SystemConfig).filter_by(config_key="ifind_password").one()
        assert password_row.is_sensitive is True
        assert password_row.config_value == ""
        assert password_row.encrypted_value
        assert b"demo-secret" not in password_row.encrypted_value
    finally:
        db.query(SystemConfig).filter(SystemConfig.config_key.in_(market_keys)).delete(
            synchronize_session=False
        )
        db.commit()


@pytest.mark.integration
def test_market_data_connection_route(client, monkeypatch):
    monkeypatch.setattr(
        SettingsService,
        "test_market_data",
        lambda self, overrides=None: {
            "ok": True,
            "provider": "ifind",
            "realtime": True,
            "sample_symbol": "600000.SH",
            "sample_price": "12.34",
            "quote_time": "2026-07-31T10:30:00+08:00",
            "latency_ms": 18,
        },
    )

    resp = client.post(
        "/api/settings/test-market-data",
        json={
            "market_data": {
                "provider": "ifind",
                "ifind_username": "demo",
                "ifind_password": "secret",
            }
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["provider"] == "ifind"
    assert resp.json()["data"]["realtime"] is True


@pytest.mark.integration
def test_strategies_and_signals(client):
    resp = client.get("/api/strategies")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    sig = client.get("/api/signals?page=1&page_size=5")
    assert sig.status_code == 200
    assert sig.json()["success"] is True

    klines = client.get("/api/klines?market=stock&symbol=600000.SH&interval=1m&limit=10")
    assert klines.status_code == 200
    assert klines.json()["success"] is True


@pytest.mark.integration
def test_risk_and_orders_api(client):
    risk = client.get("/api/risk/status")
    assert risk.status_code == 200
    assert risk.json()["success"] is True

    settings = client.get("/api/risk/settings")
    assert settings.status_code == 200
    assert settings.json()["success"] is True

    orders = client.get("/api/orders?page=1&page_size=5")
    assert orders.status_code == 200
    assert orders.json()["success"] is True

    trades = client.get("/api/trades?page=1&page_size=5")
    assert trades.status_code == 200
    assert trades.json()["success"] is True


@pytest.mark.integration
def test_quotes_and_positions(client, db):
    quote_time = datetime(2026, 7, 31, 6, 30, tzinfo=timezone.utc)
    repo = MarketRepository(db)
    for last_price in ("10.00", "11.00"):
        repo.insert_snapshot(
            QuoteSnapshot(
                symbol="API.DUPLICATE.TEST",
                market=Market.STOCK,
                quote_time=quote_time,
                last_price=Decimal(last_price),
                change_rate=Decimal("0.01"),
                volume=Decimal("100"),
            )
        )
        db.commit()

    quotes = client.get("/api/quotes")
    assert quotes.status_code == 200
    body = quotes.json()
    assert body["success"] is True
    items = body["data"]
    keys = [(item["market"], item["symbol"]) for item in items]
    matches = [item for item in items if item["symbol"] == "API.DUPLICATE.TEST"]
    assert len(keys) == len(set(keys))
    assert len(matches) == 1
    assert Decimal(matches[0]["last_price"]) == Decimal("11.00")

    positions = client.get("/api/positions")
    assert positions.status_code == 200
    assert positions.json()["success"] is True

    assets = client.get("/api/assets")
    assert assets.status_code == 200
    assert assets.json()["success"] is True
