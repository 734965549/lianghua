"""AI 客户端工厂：未配置则返回 None，走规则化模板。"""

from __future__ import annotations

from app.core.config import settings


def get_ai_client():
    if not settings.ai_provider or not settings.ai_api_key:
        return None
    if settings.ai_provider == "openai":
        from openai import OpenAI

        kwargs = {"api_key": settings.ai_api_key}
        if settings.ai_base_url:
            kwargs["base_url"] = settings.ai_base_url
        return OpenAI(**kwargs)
    return None


def resolve_model_name() -> str:
    if settings.ai_provider and settings.ai_api_key:
        return settings.ai_model or "gpt-4o-mini"
    return "rule_based"
