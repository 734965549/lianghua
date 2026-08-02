from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def now_tz() -> datetime:
    """返回配置时区下的当前时间。"""
    return datetime.now(ZoneInfo(settings.tz))


def utc_now() -> datetime:
    """返回 UTC 当前时间。"""
    return datetime.now(ZoneInfo("UTC"))


def as_utc(value: datetime) -> datetime:
    """将数据库返回的无时区 UTC 时间或任意有时区时间统一为 UTC。"""
    utc = ZoneInfo("UTC")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=utc)
    return value.astimezone(utc)


def market_time_as_utc(value: datetime) -> datetime:
    """将行情供应商返回的交易所本地时间转换为 UTC。"""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=ZoneInfo(settings.tz))
    return value.astimezone(ZoneInfo("UTC"))


def as_market_time(value: datetime) -> datetime:
    """将 UTC/任意有时区时间转换为行情接口使用的交易所本地时间。"""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo(settings.tz))


def to_utc_iso(value: datetime | None) -> str | None:
    """序列化为带 UTC 偏移的 ISO 8601，避免前端把无时区值当成本地时间。"""
    return as_utc(value).isoformat() if value is not None else None
