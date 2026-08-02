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
from app.strategies.rule_schema import DEFAULT_SYMBOLS_CONFIG
from app.strategies.rule_validator import RuleValidator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是量化策略定义生成器。用户用自然语言描述交易策略，你只输出一个 JSON 对象，不要输出 Python 代码，不要解释。

输出 JSON 结构：
{
  "name": "策略名称（中文，简短）",
  "description": "策略描述（一句话）",
  "definition": { ...策略定义... }
}

definition 必须包含：
- schema_version: 固定 1
- market: "stock" 或 "futures"
- interval: K线周期，如 "1m" "5m" "15m" "1h" "1d"
- parameters: 可调参数字典，每项含 type/default，integer 类型可加 min/max
- indicators: 指标数组
- formulas: 自定义公式数组（无则 []）
- entry_rule: 买入规则树
- exit_rule: 卖出规则树
- execution: { quantity 或 quantity_pct, cooldown_bars }
- symbols: { mode: "runtime"|"fixed", list: [], max_concurrent: 5 }
- risk: { stop_loss_pct, take_profit_pct, max_position_pct }（字符串数字）

指标 type：sma, ema, rsi, macd, bollinger, atr, roc, volume_sma, kdj
指标输出：sma/ema/rsi/atr/roc/volume_sma→value；macd→value/signal/histogram；bollinger→value/upper/lower；kdj→k/d/j
macd 不需要 period，用 params: { fast, slow, signal }；bollinger 额外 params: { std_dev: "2" }

操作符 operator：
- 比较: gt, gte, lt, lte, eq
- 穿越: cross_above, cross_below
- 区间: between（target/low/high）
- 趋势: rising, falling（operand）

操作数 operand：
- 指标: { "indicator": "id", "output": "value" }
- 价格: { "field": "open|high|low|close|volume" }
- 常量: { "constant": "30" }
- 参数: { "parameter": "name" }
- 公式: { "formula": "id" }

规则树：{ "all": [...] } 全部满足；{ "any": [...] } 任一满足；{ "not": ... } 取反

公式 expression：+ - * / ( )，引用 @指标.输出 $close #参数 &公式id

约束：指标≤20，条件≤50，嵌套≤5，period 1-500，execution 必须指定 quantity 或 quantity_pct。
只输出 JSON，不要用 markdown 代码块包裹。"""


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


def normalize_definition(definition: dict) -> dict:
    """补齐 AI 可能遗漏的默认字段。"""
    normalized = dict(definition)
    normalized.setdefault("schema_version", 1)
    normalized.setdefault("formulas", [])
    normalized.setdefault("parameters", {})
    normalized.setdefault("indicators", [])
    normalized.setdefault("risk", {})
    if "symbols" not in normalized or not isinstance(normalized.get("symbols"), dict):
        normalized["symbols"] = dict(DEFAULT_SYMBOLS_CONFIG)
    if "execution" not in normalized or not isinstance(normalized.get("execution"), dict):
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

        self.audit.log(
            action="ai_strategy_generate",
            module="ai",
            object_type="strategy_definition",
            object_id="",
            result="success" if not errors else "warning",
            request_summary={
                "prompt_len": len(cleaned),
                "market": definition.get("market"),
                "interval": definition.get("interval"),
                "validation_errors": errors[:5],
            },
        )

        return {
            "name": name,
            "description": description,
            "definition": definition,
            "validation": {"valid": len(errors) == 0, "errors": errors},
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
