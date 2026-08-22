"""TqSdk 免费账号真实行情冒烟（默认跳过，配置快期账号后手动跑）。

用法：
  cd backend
  .\\.venv\\Scripts\\python.exe -m pytest app/tests/sdk/test_tqsdk_market_data_smoke.py -m integration -q
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.schemas.enums import Market
from app.sdk.market_data.tqsdk_adapter import TqSdkMarketDataAdapter


def _auth_ready() -> bool:
    user = str(
        os.getenv("LIANGHUA_TQSDK_AUTH_USER") or settings.tqsdk_auth_user or ""
    ).strip()
    password = str(
        os.getenv("LIANGHUA_TQSDK_AUTH_PASSWORD") or settings.tqsdk_auth_password or ""
    )
    return bool(user and password)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _auth_ready(), reason="未配置 LIANGHUA_TQSDK_AUTH_USER/PASSWORD"),
]


@pytest.fixture
def live_adapter():
    adapter = TqSdkMarketDataAdapter(
        market=Market.FUTURES,
        config={
            "tqsdk_auth_user": settings.tqsdk_auth_user
            or os.getenv("LIANGHUA_TQSDK_AUTH_USER"),
            "tqsdk_auth_password": settings.tqsdk_auth_password
            or os.getenv("LIANGHUA_TQSDK_AUTH_PASSWORD"),
            "tqsdk_command_timeout_seconds": 30,
            "tqsdk_reconnect_max_seconds": 30,
        },
    )
    health = adapter.connect()
    assert health.get("connected") is True
    yield adapter
    adapter.disconnect()


def test_live_get_quote_rb0(live_adapter):
    snap = live_adapter.get_quote("RB0")
    assert snap.symbol == "RB0"
    assert snap.last_price > 0
    assert snap.raw_payload is not None
    assert snap.raw_payload.get("provider") == "tqsdk"
    assert str(snap.raw_payload.get("tq_symbol") or "").startswith("KQ.m@")


def test_live_subscribe_emits_quote(live_adapter):
    import time

    emitted = []
    live_adapter.on_quote_update(emitted.append)
    live_adapter.subscribe_quotes(["RB0"])
    deadline = time.time() + 20
    while time.time() < deadline and not emitted:
        time.sleep(0.2)
    assert emitted, "20s 内未收到 RB0 行情推送（若非交易时段可能延迟）"
    assert emitted[0].symbol == "RB0"
    assert emitted[0].last_price > 0


def test_live_kline_and_ticks(live_adapter):
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=6)
    bars = live_adapter.get_kline("RB0", "1m", start, end)
    assert isinstance(bars, list)
    # 非交易时段也可能有历史滚动序列
    if bars:
        assert bars[-1].close > 0
        assert bars[-1].symbol == "RB0"

    ticks = live_adapter.get_tick_trades("RB0", limit=20)
    assert isinstance(ticks, list)
    if ticks:
        assert set(ticks[0]) >= {"time", "price", "volume", "direction"}
        assert float(ticks[0]["price"]) > 0
