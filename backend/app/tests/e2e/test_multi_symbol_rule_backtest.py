"""端到端：多标的 + 公式因子规则策略 → 发布 → 回测 → provenance 校验。"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.trading_calendar import canonical_daily_bar_time, trading_days_between
from app.main import app
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.sdk.models import KlineBar
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION
from app.strategies.rule_validator import definition_checksum
from app.workers.data_quality import evaluate_data_quality_gate


def _close_for_index(i: int) -> Decimal:
    """前段横盘，后段抬升，使 fast_ma > slow_ma 且 spread > 0。"""
    if i < 4:
        return Decimal("10")
    return Decimal(str(10 + (i - 3) * 2))


def _insert_trading_klines(
    db,
    *,
    symbol: str,
    start: date,
    end: date,
) -> tuple[int, list[date]]:
    repo = MarketRepository(db)
    days = trading_days_between(Market.STOCK, start, end)
    bars: list[KlineBar] = []
    for i, day in enumerate(days):
        close = _close_for_index(i)
        raw_time = datetime.combine(day, time(12, 0), tzinfo=timezone.utc)
        bar_time = canonical_daily_bar_time(raw_time)
        bars.append(
            KlineBar(
                symbol=symbol,
                market=Market.STOCK,
                interval="1d",
                bar_time=bar_time,
                open=close - Decimal("0.5"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                volume=Decimal("10000"),
                raw_payload={"provider": "e2e_test"},
            )
        )
    outcome = repo.upsert_klines(bars)
    db.commit()
    return outcome["accepted"], days


def _multi_symbol_formula_definition() -> dict:
    return {
        **DEFAULT_MA_CROSS_DEFINITION,
        "parameters": {
            "fast": {"type": "integer", "default": 2, "min": 2, "max": 100},
            "slow": {"type": "integer", "default": 3, "min": 3, "max": 300},
            "quantity": {"type": "decimal", "default": "100"},
        },
        "symbols": {
            "mode": "fixed",
            "list": ["600000.SH", "600519.SH"],
            "max_concurrent": 2,
        },
        "formulas": [{"id": "spread", "expression": "@fast_ma - @slow_ma"}],
        "entry_rule": {
            "all": [
                {
                    "operator": "gt",
                    "left": {"formula": "spread"},
                    "right": {"constant": "0"},
                }
            ]
        },
        "exit_rule": {
            "any": [
                {
                    "operator": "cross_below",
                    "left": {"indicator": "fast_ma"},
                    "right": {"indicator": "slow_ma"},
                }
            ]
        },
    }


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_multi_symbol_rule_backtest_with_formula(db, reset_system_state):
    """创建多标的公式策略 → 发布 → 双标的回测 → 校验 provenance checksum。"""
    start = date(2024, 3, 1)
    end = date(2024, 3, 20)
    definition = _multi_symbol_formula_definition()
    expected_checksum = definition_checksum(definition)

    trading_days: list[date] = []
    for symbol in ("600000.SH", "600519.SH"):
        accepted, days = _insert_trading_klines(db, symbol=symbol, start=start, end=end)
        assert accepted > 0
        trading_days = days

    start_time = canonical_daily_bar_time(
        datetime.combine(trading_days[0], time(12, 0), tzinfo=timezone.utc)
    )
    end_time = canonical_daily_bar_time(
        datetime.combine(trading_days[-1], time(12, 0), tzinfo=timezone.utc)
    )

    gate = evaluate_data_quality_gate(
        db,
        targets=[(Market.STOCK, s) for s in ("600000.SH", "600519.SH")],
        interval="1d",
        start=start_time,
        end=end_time,
    )
    assert gate["ready"], gate

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/strategies",
            json={
                "name": "E2E 多标的公式策略",
                "description": "spread = fast - slow",
                "definition": definition,
            },
        )
        assert r.status_code == 200
        strategy_id = r.json()["data"]["strategy_id"]

        r = await client.post(f"/api/strategies/{strategy_id}/publish", json={})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "published"
        assert r.json()["data"]["current_version"] == 1

        r = await client.post(
            "/api/backtests",
            json={
                "strategy_id": strategy_id,
                "strategy_version": 1,
                "symbols": ["600000.SH", "600519.SH"],
                "interval": "1d",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "initial_cash": "100000",
                "parameters": {},
            },
        )
        assert r.status_code == 200, r.text
        payload = r.json()["data"]
        assert payload["status"] == "completed"
        assert payload["provenance"]["recorded"] is True
        assert payload["provenance"]["code_hash"] == f"sha256:{expected_checksum}"
        assert payload["provenance"]["strategy_version_number"] == 1
        assert payload["provenance"]["bar_count"] > 0

        trade_symbols = {t["symbol"] for t in payload.get("trades", [])}
        assert trade_symbols.issubset({"600000.SH", "600519.SH"})
        assert len(trade_symbols) >= 1

        r = await client.get(f"/api/backtests/{payload['id']}")
        assert r.status_code == 200
        stored = r.json()["data"]
        assert stored["provenance"]["code_hash"] == f"sha256:{expected_checksum}"
