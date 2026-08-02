"""策略构建 API 与版本管理测试。"""

from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION
from app.strategies.rule_validator import RuleValidator, definition_checksum


def test_definition_checksum_stable():
    h1 = definition_checksum(DEFAULT_MA_CROSS_DEFINITION)
    h2 = definition_checksum(DEFAULT_MA_CROSS_DEFINITION)
    assert h1 == h2
    assert len(h1) == 64


def test_max_indicators_limit():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "indicators": [
            {"id": f"i{n}", "type": "sma", "source": "close", "period": 5}
            for n in range(21)
        ],
    }
    errors = RuleValidator().validate(definition)
    assert any("20" in e for e in errors)
