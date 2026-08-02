import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from app.strategies.rule_schema import (
    INDICATOR_OUTPUTS,
    INDICATOR_TYPES_V1,
    INDICATOR_TYPES_NO_PERIOD,
    MAX_CONDITIONS,
    MAX_FORMULAS,
    MAX_FORMULA_LENGTH,
    MAX_INDICATORS,
    MAX_NEST_DEPTH,
    MAX_PERIOD,
    MAX_SYMBOLS,
    MAX_CONCURRENT_POSITIONS,
    OHLCV_SOURCES,
    SCHEMA_VERSION,
    ALL_OPERATORS,
)
from app.strategies.formula_evaluator import FormulaError, tokenize, TokKind


class RuleValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class RuleValidator:
    """校验策略 DSL 结构与引用。"""

    def validate(self, definition: dict) -> list[str]:
        errors: list[str] = []
        if not isinstance(definition, dict):
            return ["定义必须是 JSON 对象"]

        schema_version = definition.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            errors.append(f"不支持的 schema_version: {schema_version}")

        market = definition.get("market")
        if market not in {"stock", "futures"}:
            errors.append("market 必须是 stock 或 futures")

        interval = definition.get("interval")
        if not isinstance(interval, str) or not interval:
            errors.append("interval 不能为空")

        parameters = definition.get("parameters", {})
        if not isinstance(parameters, dict):
            errors.append("parameters 必须是对象")
            parameters = {}

        indicators = definition.get("indicators", [])
        if not isinstance(indicators, list):
            errors.append("indicators 必须是数组")
            indicators = []
        elif len(indicators) > MAX_INDICATORS:
            errors.append(f"指标数量不能超过 {MAX_INDICATORS}")

        indicator_ids: set[str] = set()
        indicator_outputs: dict[str, set[str]] = {}
        for idx, ind in enumerate(indicators):
            errors.extend(
                self._validate_indicator(ind, idx, parameters, indicator_ids, indicator_outputs)
            )

        formula_ids: set[str] = set()
        formulas = definition.get("formulas", [])
        if formulas is None:
            formulas = []
        if not isinstance(formulas, list):
            errors.append("formulas 必须是数组")
            formulas = []
        elif len(formulas) > MAX_FORMULAS:
            errors.append(f"公式数量不能超过 {MAX_FORMULAS}")
        else:
            errors.extend(self._validate_formulas(formulas, indicator_ids, parameters, formula_ids))

        symbols_cfg = definition.get("symbols")
        if symbols_cfg is not None:
            errors.extend(self._validate_symbols(symbols_cfg))

        condition_count = 0
        for rule_name in ("entry_rule", "exit_rule"):
            rule = definition.get(rule_name)
            if rule is None:
                errors.append(f"缺少 {rule_name}")
                continue
            cnt, rule_errors = self._validate_rule_group(
                rule,
                indicator_ids,
                indicator_outputs,
                formula_ids,
                parameters,
                depth=1,
            )
            condition_count += cnt
            errors.extend(rule_errors)

        if condition_count > MAX_CONDITIONS:
            errors.append(f"条件数量不能超过 {MAX_CONDITIONS}")

        execution = definition.get("execution", {})
        if not isinstance(execution, dict):
            errors.append("execution 必须是对象")
        else:
            errors.extend(self._validate_execution(execution, parameters))

        risk = definition.get("risk", {})
        if risk is not None and not isinstance(risk, dict):
            errors.append("risk 必须是对象")

        return errors

    def _validate_symbols(self, cfg: Any) -> list[str]:
        errors: list[str] = []
        if not isinstance(cfg, dict):
            return ["symbols 必须是对象"]
        mode = cfg.get("mode", "runtime")
        if mode not in {"fixed", "runtime"}:
            errors.append("symbols.mode 必须是 fixed 或 runtime")
        sym_list = cfg.get("list", [])
        if not isinstance(sym_list, list):
            errors.append("symbols.list 必须是数组")
        elif len(sym_list) > MAX_SYMBOLS:
            errors.append(f"固定标的数量不能超过 {MAX_SYMBOLS}")
        elif mode == "fixed" and not sym_list:
            errors.append("fixed 模式必须指定 symbols.list")
        max_conc = cfg.get("max_concurrent", 5)
        if not isinstance(max_conc, int) or max_conc < 1 or max_conc > MAX_CONCURRENT_POSITIONS:
            errors.append(f"symbols.max_concurrent 必须是 1-{MAX_CONCURRENT_POSITIONS} 的整数")
        return errors

    def _validate_formulas(
        self,
        formulas: list,
        indicator_ids: set[str],
        parameters: dict,
        formula_ids: set[str],
    ) -> list[str]:
        errors: list[str] = []
        for idx, f in enumerate(formulas):
            if not isinstance(f, dict):
                errors.append(f"formulas[{idx}] 必须是对象")
                continue
            fid = f.get("id")
            expr = f.get("expression")
            if not isinstance(fid, str) or not fid:
                errors.append(f"formulas[{idx}].id 无效")
                continue
            if fid in formula_ids:
                errors.append(f"公式 id 重复: {fid}")
            formula_ids.add(fid)
            if not isinstance(expr, str) or not expr.strip():
                errors.append(f"formulas[{idx}].expression 不能为空")
                continue
            if len(expr) > MAX_FORMULA_LENGTH:
                errors.append(f"formulas[{idx}] 表达式超过 {MAX_FORMULA_LENGTH} 字符")
            try:
                tokens = tokenize(expr)
            except FormulaError as exc:
                errors.append(f"formulas[{idx}]: {exc}")
                continue
            for tok in tokens:
                if tok.kind != TokKind.REF:
                    continue
                ref = tok.value
                if ref.startswith("&"):
                    continue
                if ref.startswith("@"):
                    ind_part = ref[1:].split(".")[0]
                    if ind_part not in indicator_ids:
                        errors.append(f"formulas[{idx}] 引用了未知指标: {ind_part}")
                elif ref.startswith("#"):
                    pname = ref[1:]
                    if pname not in parameters:
                        errors.append(f"formulas[{idx}] 引用了未知参数: {pname}")
        # 循环依赖检测
        for f in formulas:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            expr = f.get("expression", "")
            if not isinstance(fid, str):
                continue
            if self._formula_has_cycle(fid, expr, formulas):
                errors.append(f"公式 {fid} 存在循环引用")
        return errors

    def _formula_has_cycle(self, start_id: str, expression: str, formulas: list) -> bool:
        expr_map = {
            f["id"]: f.get("expression", "")
            for f in formulas
            if isinstance(f, dict) and isinstance(f.get("id"), str)
        }

        def deps(expr: str) -> set[str]:
            try:
                tokens = tokenize(expr)
            except FormulaError:
                return set()
            return {t.value[1:] for t in tokens if t.kind == TokKind.REF and t.value.startswith("&")}

        stack = [start_id]
        visited: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in visited:
                return True
            visited.add(cur)
            for d in deps(expr_map.get(cur, expression if cur == start_id else "")):
                if d == start_id:
                    return True
                stack.append(d)
        return False

    def validate_or_raise(self, definition: dict) -> None:
        errors = self.validate(definition)
        if errors:
            raise RuleValidationError(errors)

    def _validate_indicator(
        self,
        ind: Any,
        idx: int,
        parameters: dict,
        indicator_ids: set[str],
        indicator_outputs: dict[str, set[str]],
    ) -> list[str]:
        errors: list[str] = []
        if not isinstance(ind, dict):
            return [f"indicators[{idx}] 必须是对象"]

        ind_id = ind.get("id")
        if not isinstance(ind_id, str) or not ind_id:
            errors.append(f"indicators[{idx}].id 无效")
        elif ind_id in indicator_ids:
            errors.append(f"指标 id 重复: {ind_id}")
        else:
            indicator_ids.add(ind_id)

        ind_type = ind.get("type")
        if ind_type not in INDICATOR_TYPES_V1:
            errors.append(f"indicators[{idx}].type 不支持: {ind_type}")
            return errors

        outputs = INDICATOR_OUTPUTS.get(ind_type, {"value"})
        if isinstance(ind_id, str) and ind_id:
            indicator_outputs[ind_id] = outputs

        source = ind.get("source", "close")
        if source not in OHLCV_SOURCES:
            errors.append(f"indicators[{idx}].source 无效: {source}")

        if ind_type not in INDICATOR_TYPES_NO_PERIOD:
            period_spec = ind.get("period")
            if period_spec is None:
                errors.append(f"indicators[{idx}].period 不能为空")
            else:
                errors.extend(
                    self._validate_period_spec(period_spec, parameters, f"indicators[{idx}].period")
                )

        params = ind.get("params", {})
        if params is not None and not isinstance(params, dict):
            errors.append(f"indicators[{idx}].params 必须是对象")

        return errors

    def _validate_period_spec(
        self, spec: Any, parameters: dict, path: str
    ) -> list[str]:
        errors: list[str] = []
        if isinstance(spec, int):
            if spec < 1 or spec > MAX_PERIOD:
                errors.append(f"{path} 超出范围 1-{MAX_PERIOD}")
        elif isinstance(spec, dict):
            param_name = spec.get("parameter")
            if not isinstance(param_name, str) or param_name not in parameters:
                errors.append(f"{path} 引用了未知参数: {param_name}")
            else:
                pdef = parameters[param_name]
                if pdef.get("type") != "integer":
                    errors.append(f"{path} 参数 {param_name} 必须是 integer 类型")
        else:
            errors.append(f"{path} 格式无效")
        return errors

    def _validate_rule_group(
        self,
        node: Any,
        indicator_ids: set[str],
        indicator_outputs: dict[str, set[str]],
        formula_ids: set[str],
        parameters: dict,
        *,
        depth: int,
    ) -> tuple[int, list[str]]:
        if depth > MAX_NEST_DEPTH:
            return 0, [f"规则嵌套深度超过 {MAX_NEST_DEPTH}"]

        errors: list[str] = []
        count = 0

        if not isinstance(node, dict):
            return 0, ["规则组必须是对象"]

        keys = set(node.keys())
        if "all" in keys:
            items = node["all"]
            if not isinstance(items, list) or not items:
                errors.append("all 规则组不能为空")
            else:
                for item in items:
                    if self._is_condition(item):
                        count += 1
                        errors.extend(
                            self._validate_condition(
                                item, indicator_ids, indicator_outputs, formula_ids, parameters
                            )
                        )
                    else:
                        sub_count, sub_errors = self._validate_rule_group(
                            item,
                            indicator_ids,
                            indicator_outputs,
                            formula_ids,
                            parameters,
                            depth=depth + 1,
                        )
                        count += sub_count
                        errors.extend(sub_errors)
            return count, errors

        if "any" in keys:
            items = node["any"]
            if not isinstance(items, list) or not items:
                errors.append("any 规则组不能为空")
            else:
                for item in items:
                    if self._is_condition(item):
                        count += 1
                        errors.extend(
                            self._validate_condition(
                                item, indicator_ids, indicator_outputs, formula_ids, parameters
                            )
                        )
                    else:
                        sub_count, sub_errors = self._validate_rule_group(
                            item,
                            indicator_ids,
                            indicator_outputs,
                            formula_ids,
                            parameters,
                            depth=depth + 1,
                        )
                        count += sub_count
                        errors.extend(sub_errors)
            return count, errors

        if "not" in keys:
            inner = node["not"]
            if self._is_condition(inner):
                count += 1
                errors.extend(
                    self._validate_condition(
                        inner, indicator_ids, indicator_outputs, formula_ids, parameters
                    )
                )
            else:
                sub_count, sub_errors = self._validate_rule_group(
                    inner,
                    indicator_ids,
                    indicator_outputs,
                    formula_ids,
                    parameters,
                    depth=depth + 1,
                )
                count += sub_count
                errors.extend(sub_errors)
            return count, errors

        if self._is_condition(node):
            count += 1
            errors.extend(
                self._validate_condition(
                    node, indicator_ids, indicator_outputs, formula_ids, parameters
                )
            )
            return count, errors

        return count, ["规则组必须包含 all/any/not 或为条件"]

    def _is_condition(self, node: Any) -> bool:
        return isinstance(node, dict) and "operator" in node

    def _validate_condition(
        self,
        cond: dict,
        indicator_ids: set[str],
        indicator_outputs: dict[str, set[str]],
        formula_ids: set[str],
        parameters: dict,
    ) -> list[str]:
        errors: list[str] = []
        op = cond.get("operator")
        if op not in ALL_OPERATORS:
            errors.append(f"不支持的操作符: {op}")
            return errors

        if op in {"rising", "falling"}:
            operand = cond.get("operand") or cond.get("left")
            errors.extend(
                self._validate_operand(
                    operand, indicator_ids, indicator_outputs, formula_ids, parameters, "operand"
                )
            )
            return errors

        if op == "between":
            target = cond.get("target") or cond.get("left")
            errors.extend(
                self._validate_operand(
                    target, indicator_ids, indicator_outputs, formula_ids, parameters, "target"
                )
            )
            low = cond.get("low")
            high = cond.get("high")
            errors.extend(
                self._validate_operand(
                    low, indicator_ids, indicator_outputs, formula_ids, parameters, "low"
                )
            )
            errors.extend(
                self._validate_operand(
                    high, indicator_ids, indicator_outputs, formula_ids, parameters, "high"
                )
            )
            return errors

        left = cond.get("left")
        right = cond.get("right")
        errors.extend(
            self._validate_operand(
                left, indicator_ids, indicator_outputs, formula_ids, parameters, "left"
            )
        )
        errors.extend(
            self._validate_operand(
                right, indicator_ids, indicator_outputs, formula_ids, parameters, "right"
            )
        )
        return errors

    def _validate_operand(
        self,
        operand: Any,
        indicator_ids: set[str],
        indicator_outputs: dict[str, set[str]],
        formula_ids: set[str],
        parameters: dict,
        path: str,
    ) -> list[str]:
        if operand is None:
            return [f"{path} 不能为空"]
        if not isinstance(operand, dict):
            return [f"{path} 必须是对象"]

        if "formula" in operand:
            ref = operand["formula"]
            if ref not in formula_ids:
                return [f"{path} 引用了未知公式: {ref}"]
            return []

        if "indicator" in operand:
            ref = operand["indicator"]
            if ref not in indicator_ids:
                return [f"{path} 引用了未知指标: {ref}"]
            output = operand.get("output", "value")
            allowed = indicator_outputs.get(ref, {"value"})
            if output not in allowed:
                return [f"{path} 指标 {ref} 不支持输出: {output}"]
            return []

        if "field" in operand:
            if operand["field"] not in OHLCV_SOURCES:
                return [f"{path} 字段无效: {operand['field']}"]
            return []

        if "constant" in operand:
            try:
                val = Decimal(str(operand["constant"]))
                if not val.is_finite():
                    return [f"{path} 常量无效"]
            except (InvalidOperation, ValueError, TypeError):
                return [f"{path} 常量格式无效"]
            return []

        if "parameter" in operand:
            pname = operand["parameter"]
            if pname not in parameters:
                return [f"{path} 引用了未知参数: {pname}"]
            return []

        return [f"{path} 必须包含 indicator/field/constant/parameter 之一"]

    def _validate_execution(self, execution: dict, parameters: dict) -> list[str]:
        errors: list[str] = []
        quantity = execution.get("quantity")
        quantity_pct = execution.get("quantity_pct")
        if quantity is None and quantity_pct is None:
            errors.append("execution 必须指定 quantity 或 quantity_pct")
        if quantity is not None:
            errors.extend(
                self._validate_operand(
                    quantity, set(), {}, set(), parameters, "execution.quantity"
                )
            )
        if quantity_pct is not None:
            errors.extend(
                self._validate_operand(
                    quantity_pct, set(), {}, set(), parameters, "execution.quantity_pct"
                )
            )

        cooldown = execution.get("cooldown_bars", 0)
        if not isinstance(cooldown, int) or cooldown < 0 or cooldown > 100:
            errors.append("execution.cooldown_bars 必须是 0-100 的整数")
        return errors


def definition_checksum(definition: dict) -> str:
    payload = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_parameters(definition: dict, overrides: dict | None = None) -> dict:
    """从 DSL parameters 定义解析实际参数值。"""
    result: dict = {}
    schema = definition.get("parameters", {})
    for name, spec in schema.items():
        if overrides and name in overrides:
            result[name] = overrides[name]
        else:
            result[name] = spec.get("default")
    if overrides:
        for key, val in overrides.items():
            if key not in result:
                result[key] = val
    return result


def parameters_json_schema(definition: dict) -> dict:
    """从 DSL parameters 生成 JSON Schema。"""
    props: dict = {}
    required: list[str] = []
    for name, spec in definition.get("parameters", {}).items():
        ptype = spec.get("type", "string")
        json_type = {"integer": "integer", "decimal": "string", "string": "string"}.get(ptype, "string")
        prop: dict = {"type": json_type, "title": name}
        if "default" in spec:
            prop["default"] = spec["default"]
        if "min" in spec:
            prop["minimum"] = spec["min"]
        if "max" in spec:
            prop["maximum"] = spec["max"]
        props[name] = prop
        required.append(name)
    return {"type": "object", "properties": props, "required": required}
