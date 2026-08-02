from decimal import Decimal
from typing import Any

from app.strategies.indicators.base import Indicator, _safe_decimal
from app.strategies.rule_schema import OHLCV_SOURCES


class RuleEvaluator:
    """执行规则 DSL 条件树（结构化 AST，禁止 eval）。"""

    def __init__(
        self,
        *,
        indicators: dict[str, Indicator],
        parameters: dict,
        bar_fields: dict[str, Decimal],
        formula_values: dict[str, Decimal | None] | None = None,
        formula_prev_values: dict[str, Decimal | None] | None = None,
        rolling_fields: dict[str, Decimal | None] | None = None,
        has_position: bool = False,
        bars_since_signal: int = 0,
    ):
        self._indicators = indicators
        self._parameters = parameters
        self._bar_fields = bar_fields
        self._formula_values = formula_values or {}
        self._formula_prev_values = formula_prev_values or {}
        self._rolling_fields = rolling_fields or {}
        self._has_position = has_position
        self._bars_since_signal = bars_since_signal

    def evaluate(self, node: dict | None) -> bool:
        if node is None:
            return False
        if "all" in node:
            return all(
                self.evaluate(item) if self._is_group(item) else self._eval_condition(item)
                for item in node["all"]
            )
        if "any" in node:
            return any(
                self.evaluate(item) if self._is_group(item) else self._eval_condition(item)
                for item in node["any"]
            )
        if "not" in node:
            inner = node["not"]
            if self._is_group(inner):
                return not self.evaluate(inner)
            return not self._eval_condition(inner)
        if "operator" in node:
            return self._eval_condition(node)
        return False

    def _is_group(self, node: Any) -> bool:
        return isinstance(node, dict) and ("all" in node or "any" in node or "not" in node)

    def _eval_condition(self, cond: dict) -> bool:
        op = cond.get("operator")
        if op == "has_position":
            return self._has_position
        if op == "no_position":
            return not self._has_position
        if op == "bar_since_gte":
            bars = cond.get("bars")
            if not isinstance(bars, int) or bars < 0:
                bars_spec = cond.get("right")
                if isinstance(bars_spec, dict) and "constant" in bars_spec:
                    try:
                        bars = int(Decimal(str(bars_spec["constant"])))
                    except (ValueError, TypeError):
                        return False
                else:
                    return False
            return self._bars_since_signal >= bars
        if op == "rising":
            operand = cond.get("operand") or cond.get("left")
            curr, prev = self._resolve_pair(operand)
            return curr is not None and prev is not None and curr > prev
        if op == "falling":
            operand = cond.get("operand") or cond.get("left")
            curr, prev = self._resolve_pair(operand)
            return curr is not None and prev is not None and curr < prev
        if op in {"percent_change_gte", "percent_change_lte"}:
            operand = cond.get("operand") or cond.get("left")
            threshold = self._resolve_value(cond.get("right"))
            curr, prev = self._resolve_pair(operand)
            if curr is None or prev is None or prev == 0 or threshold is None:
                return False
            pct = (curr - prev) / abs(prev) * Decimal("100")
            if op == "percent_change_gte":
                return pct >= threshold
            return pct <= -abs(threshold)
        if op == "between":
            target = cond.get("target") or cond.get("left")
            low = self._resolve_value(cond.get("low"))
            high = self._resolve_value(cond.get("high"))
            val = self._resolve_value(target)
            if val is None or low is None or high is None:
                return False
            return low <= val <= high
        if op == "cross_above":
            left_curr, left_prev = self._resolve_pair(cond.get("left"))
            right_curr, right_prev = self._resolve_pair(cond.get("right"))
            if None in (left_curr, left_prev, right_curr, right_prev):
                return False
            return left_prev <= right_prev and left_curr > right_curr
        if op == "cross_below":
            left_curr, left_prev = self._resolve_pair(cond.get("left"))
            right_curr, right_prev = self._resolve_pair(cond.get("right"))
            if None in (left_curr, left_prev, right_curr, right_prev):
                return False
            return left_prev >= right_prev and left_curr < right_curr

        left = self._resolve_value(cond.get("left"))
        right = self._resolve_value(cond.get("right"))
        if left is None or right is None:
            return False
        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        if op == "lte":
            return left <= right
        if op == "eq":
            return left == right
        return False

    def _rolling_key(self, field: str, lookback: int) -> str:
        return f"{field}:{lookback}"

    def _resolve_pair(self, operand: dict | None) -> tuple[Decimal | None, Decimal | None]:
        if operand is None:
            return None, None
        if "formula" in operand:
            fid = operand["formula"]
            return _safe_decimal(self._formula_values.get(fid)), _safe_decimal(
                self._formula_prev_values.get(fid)
            )
        if "indicator" in operand:
            ind = self._indicators.get(operand["indicator"])
            if ind is None:
                return None, None
            output = operand.get("output", "value")
            return _safe_decimal(ind.get_output(output)), _safe_decimal(ind.get_prev_output(output))
        if "field" in operand:
            field = operand["field"]
            lookback = operand.get("lookback")
            if lookback is not None:
                key = self._rolling_key(field, int(lookback))
                val = _safe_decimal(self._rolling_fields.get(key))
                prev_key = f"_prev_{key}"
                return val, _safe_decimal(self._rolling_fields.get(prev_key))
            curr = _safe_decimal(self._bar_fields.get(field))
            prev = _safe_decimal(self._bar_fields.get(f"_prev_{field}"))
            return curr, prev
        val = self._resolve_value(operand)
        return val, val

    def _resolve_value(self, operand: dict | None) -> Decimal | None:
        if operand is None:
            return None
        if "formula" in operand:
            return _safe_decimal(self._formula_values.get(operand["formula"]))
        if "indicator" in operand:
            ind = self._indicators.get(operand["indicator"])
            if ind is None:
                return None
            output = operand.get("output", "value")
            return _safe_decimal(ind.get_output(output))
        if "field" in operand:
            field = operand["field"]
            lookback = operand.get("lookback")
            if lookback is not None:
                key = self._rolling_key(field, int(lookback))
                return _safe_decimal(self._rolling_fields.get(key))
            if field not in OHLCV_SOURCES:
                return None
            return _safe_decimal(self._bar_fields.get(field))
        if "constant" in operand:
            return _safe_decimal(operand["constant"])
        if "parameter" in operand:
            return _safe_decimal(self._parameters.get(operand["parameter"]))
        return None
