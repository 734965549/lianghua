from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def now_tz() -> datetime:
    """返回配置时区下的当前时间。"""
    return datetime.now(ZoneInfo(settings.tz))


def utc_now() -> datetime:
    """返回 UTC 当前时间。"""
    return datetime.now(ZoneInfo("UTC"))
