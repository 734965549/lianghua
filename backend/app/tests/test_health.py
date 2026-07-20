import pytest


@pytest.mark.unit
def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["api"] == "ok"
    assert "correlation_id" in body
    assert body["correlation_id"]


@pytest.mark.unit
def test_not_found_unified_response(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "SYS_NOT_FOUND"
    assert "correlation_id" in body
