"""run_mode 参数校验。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.strategy_service import strategy_service


@pytest.fixture(autouse=True)
def _reset_running():
    strategy_service._running.clear()
    yield
    strategy_service._running.clear()


@pytest.mark.asyncio
async def test_start_rejects_invalid_run_mode(db, reset_system_state):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/strategies/ma_cross/start",
            json={
                "confirm": True,
                "run_mode": "invalid",
                "symbols": ["600000.SH"],
                "parameters": {
                    "symbols": ["600000.SH"],
                    "fast": 2,
                    "slow": 3,
                    "interval": "1m",
                    "quantity": "100",
                },
            },
        )
        assert r.status_code != 200 or r.json()["success"] is False


@pytest.mark.asyncio
async def test_start_returns_run_mode(db, reset_system_state):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/strategies/ma_cross/start",
            json={
                "confirm": True,
                "run_mode": "paper",
                "symbols": ["600000.SH"],
                "parameters": {
                    "symbols": ["600000.SH"],
                    "fast": 2,
                    "slow": 3,
                    "interval": "1m",
                    "quantity": "100",
                },
            },
        )
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert r.json()["data"]["run_mode"] == "paper"

        await client.post(
            f"/api/strategies/ma_cross/stop",
            json={"reason": "test cleanup"},
        )
