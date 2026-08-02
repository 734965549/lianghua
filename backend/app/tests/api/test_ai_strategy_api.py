"""AI 策略生成 API 测试。"""

import json
from unittest.mock import MagicMock

from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION


def test_ai_strategy_generate_api(client, db, monkeypatch):
    from app.services.ai_strategy_service import AiStrategyService

    svc = AiStrategyService(db)
    svc.ai_client = MagicMock()
    svc.model_name = "mock-ai"

    payload = {
        "name": "RSI 策略",
        "description": "超卖买入",
        "definition": DEFAULT_MA_CROSS_DEFINITION,
    }
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    svc.ai_client.chat.completions.create.return_value = fake_resp

    monkeypatch.setattr(
        "app.api.routes.ai_strategies.AiStrategyService",
        lambda db, correlation_id="": svc,
    )

    r = client.post(
        "/api/ai/strategies/generate",
        json={"prompt": "RSI低于30买入，高于70卖出"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["name"] == "RSI 策略"
    assert data["validation"]["valid"] is True


def test_ai_strategy_generate_not_configured(client, monkeypatch):
    from app.services.ai_strategy_service import AiStrategyService

    svc = AiStrategyService.__new__(AiStrategyService)
    svc.ai_client = None

    monkeypatch.setattr(
        "app.api.routes.ai_strategies.AiStrategyService",
        lambda db, correlation_id="": svc,
    )

    r = client.post(
        "/api/ai/strategies/generate",
        json={"prompt": "双均线策略"},
    )
    assert r.status_code != 200 or r.json()["success"] is False
