"""AI 客户端工厂：支持环境变量与系统配置库提供的运行时配置。

供 AiReportService（复盘报告）与 AiStrategyService（策略定义生成）共用。
未配置 provider/api_key 时返回 None：复盘降级为规则模板，策略生成返回错误。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.config import settings


def _env_config() -> dict[str, str]:
    return {
        "provider": settings.ai_provider,
        "api_key": settings.ai_api_key,
        "base_url": settings.ai_base_url,
        "model": settings.ai_model,
    }


def normalize_ai_config(config: Mapping[str, Any] | None = None) -> dict[str, str]:
    source = config or _env_config()
    return {
        "provider": str(source.get("provider") or "").strip().lower(),
        "api_key": str(source.get("api_key") or "").strip(),
        "base_url": str(source.get("base_url") or "").strip(),
        "model": str(source.get("model") or "gpt-4o-mini").strip(),
    }


def get_ai_client(
    config: Mapping[str, Any] | None = None,
    *,
    timeout: float = 30.0,
):
    resolved = normalize_ai_config(config)
    if not resolved["provider"] or not resolved["api_key"]:
        return None
    if resolved["provider"] == "openai":
        from openai import OpenAI

        kwargs: dict[str, Any] = {
            "api_key": resolved["api_key"],
            "timeout": timeout,
            "max_retries": 0,
        }
        if resolved["base_url"]:
            kwargs["base_url"] = resolved["base_url"]
        return OpenAI(**kwargs)
    return None


def resolve_model_name(config: Mapping[str, Any] | None = None) -> str:
    resolved = normalize_ai_config(config)
    if resolved["provider"] and resolved["api_key"]:
        return resolved["model"] or "gpt-4o-mini"
    return "rule_based"
