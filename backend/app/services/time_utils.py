from datetime import datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

DAY_MAP = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def is_in_session(now: datetime, sessions: list) -> bool:
    """检查当前时间是否在允许交易时段。空列表表示不限制。"""
    if not sessions:
        return True

    local = now.astimezone(SHANGHAI)
    weekday = local.weekday()
    current_minutes = local.hour * 60 + local.minute

    for session in sessions:
        days = session.get("days", [])
        if days and weekday not in {DAY_MAP.get(d, -1) for d in days}:
            continue
        start_parts = session.get("start", "00:00").split(":")
        end_parts = session.get("end", "23:59").split(":")
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
        end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
        if start_minutes <= current_minutes <= end_minutes:
            return True
    return False
