"""AI 策略生成服务测试。"""

import json
from unittest.mock import MagicMock

import pytest

from app.api.response import BizError
from app.schemas.error_codes import ErrorCode
from app.services.ai_strategy_service import (
    AiStrategyService,
    extract_json_object,
    normalize_definition,
)
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION
from app.strategies.rule_validator import RuleValidator


def test_extract_json_object_plain():
    payload = {"name": "测试", "definition": {"schema_version": 1}}
    assert extract_json_object(json.dumps(payload)) == payload


def test_extract_json_object_markdown_fence():
    text = '说明\n```json\n{"name": "均线", "definition": {"schema_version": 1}}\n```'
    result = extract_json_object(text)
    assert result["name"] == "均线"


def test_extract_json_object_embedded():
    text = '前缀 {"name": "x", "definition": {"schema_version": 1}} 后缀'
    result = extract_json_object(text)
    assert result["name"] == "x"


def test_normalize_definition_fills_defaults():
    base = {"schema_version": 1, "market": "stock", "interval": "1d"}
    out = normalize_definition(base)
    assert out["formulas"] == []
    assert out["symbols"]["mode"] == "runtime"
    assert "execution" in out


def test_generate_without_ai_client_raises(db):
    svc = AiStrategyService(db)
    svc.ai_client = None
    with pytest.raises(BizError) as exc:
        svc.generate("双均线策略")
    assert exc.value.code == ErrorCode.AI_STRATEGY_NOT_CONFIGURED


def test_generate_empty_prompt_raises(db):
    svc = AiStrategyService(db)
    svc.ai_client = MagicMock()
    with pytest.raises(BizError) as exc:
        svc.generate("   ")
    assert exc.value.code == ErrorCode.AI_STRATEGY_PROMPT_EMPTY


def test_generate_success(db, monkeypatch):
    svc = AiStrategyService(db)
    svc.ai_client = MagicMock()
    svc.model_name = "mock-ai"

    ai_payload = {
        "name": "双均线金叉",
        "description": "快线上穿慢线买入",
        "definition": DEFAULT_MA_CROSS_DEFINITION,
    }

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=json.dumps(ai_payload)))]
    svc.ai_client.chat.completions.create.return_value = fake_resp

    result = svc.generate("日线双均线，5日上穿20日买入，下穿卖出")
    assert result["name"] == "双均线金叉"
    assert result["validation"]["valid"] is True
    assert result["model_name"] == "mock-ai"
    assert result["definition"]["schema_version"] == 1


def test_generate_invalid_output_raises(db):
    svc = AiStrategyService(db)
    svc.ai_client = MagicMock()
    svc.model_name = "mock-ai"

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content='{"name": "无定义"}'))]
    svc.ai_client.chat.completions.create.return_value = fake_resp

    with pytest.raises(BizError) as exc:
        svc.generate("随便描述")
    assert exc.value.code == ErrorCode.AI_STRATEGY_INVALID_OUTPUT


def test_generate_retries_on_validation_error(db):
    svc = AiStrategyService(db)
    svc.ai_client = MagicMock()
    svc.model_name = "mock-ai"

    bad_def = {"schema_version": 1, "market": "invalid", "interval": "1d"}
    good_payload = {
        "name": "修正后",
        "description": "修正",
        "definition": DEFAULT_MA_CROSS_DEFINITION,
    }

    first_resp = MagicMock()
    first_resp.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({"name": "错", "description": "", "definition": bad_def})
            )
        )
    ]
    second_resp = MagicMock()
    second_resp.choices = [MagicMock(message=MagicMock(content=json.dumps(good_payload)))]
    svc.ai_client.chat.completions.create.side_effect = [first_resp, second_resp]

    result = svc.generate("双均线")
    assert result["name"] == "修正后"
    assert result["validation"]["valid"] is True
    assert svc.ai_client.chat.completions.create.call_count == 2


def test_default_ma_cross_passes_validator():
    errors = RuleValidator().validate(DEFAULT_MA_CROSS_DEFINITION)
    assert errors == []
