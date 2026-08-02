"""AI 自然语言策略定义生成服务。

将用户中文描述转为规则 DSL JSON（非 Python 代码），经 RuleValidator 校验后
返回给策略构建器。与 AiReportService 共用 ai_client，职责分离。

API: POST /api/ai/strategies/generate
文档: doc/strategy-builder-design.md
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.core.config import settings
from app.schemas.error_codes import ErrorCode
from app.services.ai_client import get_ai_client, resolve_model_name
from app.services.audit_service import AuditService
from app.services.settings_service import SettingsService
from app.services.strategy_builder_service import strategy_builder_service
from app.strategies.rule_schema import DEFAULT_MA_CROSS_DEFINITION, DEFAULT_SYMBOLS_CONFIG
from app.strategies.rule_validator import RuleValidator

logger = logging.getLogger(__name__)

_FEW_SHOT_EXAMPLE = json.dumps(
    {
        "name": "RSI 超卖反弹",
        "description": "RSI 低于 30 买入，高于 70 卖出，账户 30% 仓位",
        "definition": {
            "schema_version": 1,
            "market": "stock",
            "interval": "1d",
            "parameters": {},
            "indicators": [
                {"id": "rsi_14", "type": "rsi", "source": "close", "period": 14},
            ],
            "formulas": [],
            "entry_rule": {
                "all": [
                    {
                        "operator": "lt",
                        "left": {"indicator": "rsi_14", "output": "value"},
                        "right": {"constant": "30"},
                    }
                ]
            },
            "exit_rule": {
                "any": [
                    {
                        "operator": "gt",
                        "left": {"indicator": "rsi_14", "output": "value"},
                        "right": {"constant": "70"},
                    }
                ]
            },
            "execution": {"quantity_pct": {"constant": "30"}, "cooldown_bars": 1},
            "symbols": {"mode": "runtime", "list": [], "max_concurrent": 5},
            "risk": {"stop_loss_pct": "5", "take_profit_pct": "10", "max_position_pct": "30"},
        },
    },
    ensure_ascii=False,
    indent=2,
)

SYSTEM_PROMPT = f"""你是量化策略定义生成器。用户用自然语言描述交易策略，你只输出一个 JSON 对象，不要输出 Python 代码，不要解释。

输出 JSON 结构：
{{
  "name": "策略名称（中文，简短）",
  "description": "策略描述（一句话）",
  "definition": {{ ...策略定义... }}
}}

definition 必须包含：
- schema_version: 固定 1
- market: "stock" 或 "futures"
- interval: K线周期，如 "1m" "5m" "15m" "1h" "1d"
- parameters: 可调参数字典，每项含 type/default，integer 类型可加 min/max
- indicators: 指标数组
- formulas: 自定义公式数组（无则 []）
- entry_rule: 买入规则树
- exit_rule: 卖出规则树
- execution: {{ quantity 或 quantity_pct, cooldown_bars }}
- symbols: {{ mode: "runtime"|"fixed", list: [], max_concurrent: 5 }}
- risk: {{ stop_loss_pct, take_profit_pct, max_position_pct }}（字符串数字）

指标 type：sma, ema, rsi, macd, bollinger, atr, roc, volume_sma, kdj
指标输出：sma/ema/rsi/atr/roc/volume_sma→value；macd→value/signal/histogram；bollinger→value/upper/lower；kdj→k/d/j

【指标 period 规则 — 必须严格遵守】
- 需要周期的指标（sma/ema/rsi/bollinger/atr/roc/volume_sma/kdj）必须在指标对象顶层写 period
- period 只能是整数（如 20）或参数引用 {{ "parameter": "参数名" }}
- 禁止把 period 放进 params；params 仅用于 macd 的 fast/slow/signal 和 bollinger 的 std_dev
- macd 不需要顶层 period，示例：{{ "id": "macd_1", "type": "macd", "source": "close", "params": {{ "fast": 12, "slow": 26, "signal": 9 }} }}

【execution 规则 — 必须严格遵守】
- quantity 与 quantity_pct 二选一，值必须是操作数对象，禁止裸数字
- 固定股数：{{ "quantity": {{ "constant": "100" }}, "cooldown_bars": 1 }}
- 账户百分比：{{ "quantity_pct": {{ "constant": "30" }}, "cooldown_bars": 1 }}
- 引用参数：{{ "quantity": {{ "parameter": "quantity" }} }}

操作符 operator：
- 比较: gt, gte, lt, lte, eq
- 穿越: cross_above, cross_below
- 区间: between（target/low/high）
- 趋势: rising, falling（operand）

操作数 operand：
- 指标: {{ "indicator": "id", "output": "value" }}
- 价格: {{ "field": "open|high|low|close|volume" }}
- 常量: {{ "constant": "30" }}
- 参数: {{ "parameter": "name" }}
- 公式: {{ "formula": "id" }}

规则树：{{ "all": [...] }} 全部满足；{{ "any": [...] }} 任一满足；{{ "not": ... }} 取反

公式 expression：+ - * / ( )，引用 @指标.输出 $close #参数 &公式id

约束：指标≤20，条件≤50，嵌套≤5，period 1-500，execution 必须指定 quantity 或 quantity_pct。
只输出 JSON，不要用 markdown 代码块包裹。

完整合法示例（请严格参照字段形状）：
{_FEW_SHOT_EXAMPLE}

双均线参考（period 可用参数引用）：
{json.dumps(DEFAULT_MA_CROSS_DEFINITION, ensure_ascii=False, indent=2)}"""


def extract_json_object(text: str) -> dict:
    """从 AI 回复中提取 JSON 对象。"""
    raw = text.strip()
    if not raw:
        raise ValueError("AI 返回为空")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        snippet = raw[start : end + 1]
        parsed = json.loads(snippet)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("无法解析 AI 返回的 JSON")


_OPERAND_KEYS = frozenset({"indicator", "field", "constant", "parameter", "formula"})


def _coerce_period(value: Any) -> Any:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    if isinstance(value, dict) and "parameter" in value:
        return value
    return value


def _normalize_operand(value: Any) -> dict | None:
    if isinstance(value, dict) and _OPERAND_KEYS.intersection(value):
        return value
    if isinstance(value, (int, float)):
        return {"constant": str(value)}
    if isinstance(value, str):
        try:
            float(value)
            return {"constant": value}
        except ValueError:
            return None
    return None


def _normalize_indicator(ind: dict) -> dict:
    normalized = dict(ind)
    params = dict(normalized.get("params") or {})

    if normalized.get("period") is None and "period" in params:
        normalized["period"] = _coerce_period(params.pop("period"))

    if "period" in normalized:
        normalized["period"] = _coerce_period(normalized["period"])

    if normalized.get("period") is None:
        ind_id = normalized.get("id", "")
        if isinstance(ind_id, str):
            match = re.search(r"_(\d+)$", ind_id)
            if match:
                normalized["period"] = int(match.group(1))

    if params:
        normalized["params"] = params
    elif "params" in normalized:
        normalized.pop("params")

    return normalized


def _normalize_execution(execution: dict) -> dict:
    normalized = dict(execution)
    for key in ("quantity", "quantity_pct"):
        if key not in normalized:
            continue
        fixed = _normalize_operand(normalized[key])
        if fixed is None:
            normalized.pop(key)
        else:
            normalized[key] = fixed

    if normalized.get("quantity") is None and normalized.get("quantity_pct") is None:
        normalized["quantity"] = {"constant": "100"}
    normalized.setdefault("cooldown_bars", 1)
    return normalized


def normalize_definition(definition: dict) -> dict:
    """补齐 AI 可能遗漏的默认字段，并修正常见形状错误。"""
    normalized = dict(definition)
    normalized.setdefault("schema_version", 1)
    normalized.setdefault("formulas", [])
    normalized.setdefault("parameters", {})
    normalized.setdefault("risk", {})

    indicators = normalized.get("indicators")
    if isinstance(indicators, list):
        normalized["indicators"] = [
            _normalize_indicator(item) for item in indicators if isinstance(item, dict)
        ]
    else:
        normalized["indicators"] = []

    if "symbols" not in normalized or not isinstance(normalized.get("symbols"), dict):
        normalized["symbols"] = dict(DEFAULT_SYMBOLS_CONFIG)

    execution = normalized.get("execution")
    if isinstance(execution, dict):
        normalized["execution"] = _normalize_execution(execution)
    else:
        normalized["execution"] = {"quantity": {"constant": "100"}, "cooldown_bars": 1}

    return normalized


class AiStrategyService:
    """调用 AI 模型生成策略 definition，并做 JSON 解析与 DSL 校验。"""
    def __init__(self, db: Session, *, correlation_id: str = ""):
        self.db = db
        self.audit = AuditService(db, correlation_id=correlation_id)
        self.ai_config = SettingsService(db, correlation_id=correlation_id).get_ai_runtime_config()
        self.ai_client = get_ai_client(
            self.ai_config, timeout=settings.ai_generation_timeout
        )
        self.model_name = resolve_model_name(self.ai_config)
        self.catalog = strategy_builder_service.get_indicator_catalog()

    def generate(
        self,
        prompt: str,
        *,
        market: str | None = None,
        interval: str | None = None,
    ) -> dict:
        cleaned = prompt.strip()
        if not cleaned:
            raise BizError(ErrorCode.AI_STRATEGY_PROMPT_EMPTY, "请描述您想要的策略")
        if not self.ai_client:
            raise BizError(
                ErrorCode.AI_STRATEGY_NOT_CONFIGURED,
                "AI 未配置，请先在系统设置中填写 AI Provider 和 API Key",
            )

        user_prompt = self._build_user_prompt(cleaned, market=market, interval=interval)
        raw_content = self._call_ai(user_prompt)
        payload = extract_json_object(raw_content)

        name = str(payload.get("name") or "").strip() or "AI 生成策略"
        description = str(payload.get("description") or "").strip()
        definition = payload.get("definition")
        if not isinstance(definition, dict):
            raise BizError(
                ErrorCode.AI_STRATEGY_INVALID_OUTPUT,
                "AI 返回格式无效：缺少 definition 对象",
                debug=raw_content[:500],
            )

        definition = normalize_definition(definition)
        if market in {"stock", "futures"}:
            definition["market"] = market
        if interval:
            definition["interval"] = interval

        errors = RuleValidator().validate(definition)
        if errors:
            fixed = self._retry_with_validation_errors(cleaned, definition, errors, market, interval)
            if fixed is not None:
                name = fixed["name"]
                description = fixed["description"]
                definition = fixed["definition"]
                errors = fixed["errors"]

        if errors:
            self.audit.log(
                action="ai_strategy_generate",
                module="ai",
                object_type="strategy_definition",
                object_id="",
                result="failed",
                request_summary={
                    "prompt_len": len(cleaned),
                    "validation_errors": errors[:10],
                },
            )
            raise BizError(
                ErrorCode.AI_STRATEGY_INVALID_OUTPUT,
                f"AI 生成的策略定义未通过校验（{len(errors)} 项），请调整描述后重试",
                debug="; ".join(errors[:10]),
            )

        self.audit.log(
            action="ai_strategy_generate",
            module="ai",
            object_type="strategy_definition",
            object_id="",
            result="success",
            request_summary={
                "prompt_len": len(cleaned),
                "market": definition.get("market"),
                "interval": definition.get("interval"),
            },
        )

        return {
            "name": name,
            "description": description,
            "definition": definition,
            "validation": {"valid": True, "errors": []},
            "model_name": self.model_name,
        }

    def _build_user_prompt(
        self,
        prompt: str,
        *,
        market: str | None = None,
        interval: str | None = None,
    ) -> str:
        hints: list[str] = []
        if market in {"stock", "futures"}:
            hints.append(f"市场偏好：{market}")
        if interval:
            hints.append(f"周期偏好：{interval}")
        hint_text = "\n".join(hints)
        catalog_summary = json.dumps(
            {
                "indicators": self.catalog.get("indicators", []),
                "operators": self.catalog.get("operators", []),
                "fields": self.catalog.get("fields", []),
                "formula_ref_help": self.catalog.get("formula_ref_help", ""),
            },
            ensure_ascii=False,
        )
        parts = [
            "请根据以下自然语言描述生成完整策略 JSON：",
            prompt,
        ]
        if hint_text:
            parts.extend(["", hint_text])
        parts.extend(["", "可用指标与操作符目录：", catalog_summary])
        return "\n".join(parts)

    def _call_ai(self, user_prompt: str) -> str:
        try:
            resp = self.ai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            content = resp.choices[0].message.content or ""
        except Exception as exc:
            logger.exception("AI 策略生成调用失败: %s", exc)
            self.audit.log(
                action="ai_strategy_failed",
                module="ai",
                object_type="strategy_definition",
                object_id="",
                result="failed",
                reason=str(exc),
            )
            message = self._format_ai_error(exc)
            raise BizError(
                ErrorCode.AI_STRATEGY_FAILED,
                message,
                retryable=True,
            ) from exc

        if not content.strip():
            raise BizError(ErrorCode.AI_STRATEGY_INVALID_OUTPUT, "AI 返回为空")
        return content

    @staticmethod
    def _format_ai_error(exc: Exception) -> str:
        from openai import APITimeoutError

        if isinstance(exc, APITimeoutError):
            timeout = int(settings.ai_generation_timeout)
            return (
                f"AI 策略生成超时（{timeout} 秒）。"
                "连通性测试只验证模型列表，完整生成耗时更长，"
                "请稍后重试或调大 LIANGHUA_AI_GENERATION_TIMEOUT。"
            )
        return f"AI 策略生成失败: {exc}"

    def _retry_with_validation_errors(
        self,
        original_prompt: str,
        definition: dict,
        errors: list[str],
        market: str | None,
        interval: str | None,
    ) -> dict[str, Any] | None:
        fix_prompt = (
            f"原始需求：{original_prompt}\n\n"
            f"上次生成的 definition 校验失败，请修正后重新输出完整 JSON：\n"
            f"错误：{'; '.join(errors)}\n\n"
            f"上次 definition：\n{json.dumps(definition, ensure_ascii=False)}"
        )
        user_prompt = self._build_user_prompt(fix_prompt, market=market, interval=interval)
        try:
            raw_content = self._call_ai(user_prompt)
            payload = extract_json_object(raw_content)
        except (BizError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("AI 策略修正失败: %s", exc)
            return None

        name = str(payload.get("name") or "").strip() or "AI 生成策略"
        description = str(payload.get("description") or "").strip()
        new_def = payload.get("definition")
        if not isinstance(new_def, dict):
            return None

        new_def = normalize_definition(new_def)
        if market in {"stock", "futures"}:
            new_def["market"] = market
        if interval:
            new_def["interval"] = interval
        new_errors = RuleValidator().validate(new_def)
        return {
            "name": name,
            "description": description,
            "definition": new_def,
            "errors": new_errors,
        }
