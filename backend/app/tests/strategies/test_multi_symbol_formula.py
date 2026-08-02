"""多标的、公式因子测试。"""

from app.strategies.formula_evaluator import evaluate_expression, tokenize, TokKind
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION
from app.strategies.rule_validator import RuleValidator


def test_symbols_fixed_validation():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "symbols": {"mode": "fixed", "list": ["600000.SH", "600519.SH"], "max_concurrent": 2},
    }
    assert RuleValidator().validate(definition) == []


def test_symbols_runtime_validation():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
        "symbols": {"mode": "runtime", "list": [], "max_concurrent": 5},
    }
    assert RuleValidator().validate(definition) == []


def test_formula_validation():
    definition = {
        **DEFAULT_MA_CROSS_DEFINITION,
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
    errors = RuleValidator().validate(definition)
    assert errors == []


def test_formula_tokenize():
    tokens = tokenize("@fast_ma - @slow_ma * 2")
    kinds = [t.kind for t in tokens if t.kind != TokKind.EOF]
    assert TokKind.REF in kinds
    assert TokKind.MINUS in kinds


def test_formula_evaluate():
    resolver = lambda ref: {"@fast_ma": 12, "@slow_ma": 10}.get(ref)
    result = evaluate_expression("@fast_ma - @slow_ma", resolver)
    assert result == 2
