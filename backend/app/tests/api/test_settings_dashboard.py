"""设置、仪表盘等 API 集成测试。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


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
def test_quotes_and_positions(client):
    quotes = client.get("/api/quotes?market=stock")
    assert quotes.status_code == 200
    assert quotes.json()["success"] is True

    positions = client.get("/api/positions")
    assert positions.status_code == 200
    assert positions.json()["success"] is True

    assets = client.get("/api/assets")
    assert assets.status_code == 200
    assert assets.json()["success"] is True
