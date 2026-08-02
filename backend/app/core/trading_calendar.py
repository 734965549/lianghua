from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from importlib.metadata import version
import re
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from app.core.config import settings
from app.core.domestic_futures import FUTURES_EXCHANGE_BY_PRODUCT
from app.schemas.enums import Market

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
EXCHANGE_CALENDAR_NAME = "XSHG"


class TradingCalendarError(RuntimeError):
    """Raised when the bundled exchange calendar cannot safely classify a date."""


@lru_cache(maxsize=1)
def _exchange_calendar():
    return xcals.get_calendar(EXCHANGE_CALENDAR_NAME)


def _calendar_bounds() -> tuple[date, date]:
    calendar = _exchange_calendar()
    return calendar.bound_min().date(), calendar.bound_max().date()


@lru_cache(maxsize=8)
def _provider_year_status(year: int) -> tuple[bool, int]:
    lower, upper = _calendar_bounds()
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    if year_start < lower or year_end > upper:
        return False, 0

    weekday_closures = 0
    current = year_start
    while current <= year_end:
        if current.weekday() < 5 and not _provider_is_session(current):
            weekday_closures += 1
        current += timedelta(days=1)
    return True, weekday_closures


@lru_cache(maxsize=8192)
def _provider_is_session(value: date) -> bool:
    lower, upper = _calendar_bounds()
    if not lower <= value <= upper:
        raise TradingCalendarError(
            f"交易日 {value.isoformat()} 超出 {EXCHANGE_CALENDAR_NAME} 离线日历范围 "
            f"{lower.isoformat()}..{upper.isoformat()}，请先升级 exchange-calendars"
        )
    return bool(_exchange_calendar().is_session(value))


def trading_calendar_status(reference_date: date | None = None) -> dict:
    """Return auditable coverage details for the bundled offline calendar."""
    current = reference_date or datetime.now(SHANGHAI_TZ).date()
    lower, upper = _calendar_bounds()
    supported, weekday_closures = _provider_year_status(current.year)
    return {
        "provider": f"exchange-calendars:{EXCHANGE_CALENDAR_NAME}",
        "provider_version": version("exchange-calendars"),
        "year": current.year,
        "supported": supported,
        "supported_from": lower.isoformat(),
        "supported_through": upper.isoformat(),
        "weekday_holiday_count": weekday_closures,
        "stock_extra_holiday_count": len(_configured_holidays(Market.STOCK)),
        "futures_extra_holiday_count": len(_configured_holidays(Market.FUTURES)),
    }


def validate_trading_calendar(reference_date: date | None = None) -> dict:
    """Fail closed unless the provider covers the full current calendar year."""
    status = trading_calendar_status(reference_date)
    if not status["supported"]:
        raise TradingCalendarError(
            f"交易日历未覆盖 {status['year']} 完整年度；当前仅覆盖至 "
            f"{status['supported_through']}。请升级 exchange-calendars 后再启动服务。"
        )
    if status["weekday_holiday_count"] <= 0:
        raise TradingCalendarError(
            f"交易日历 {status['provider']} 未包含 {status['year']} 工作日休市记录，"
            "拒绝按仅周末规则启动。"
        )
    return status


def _configured_holidays(market: Market) -> frozenset[date]:
    values: set[date] = set()
    configured = (
        settings.futures_market_holidays
        if market == Market.FUTURES
        else settings.stock_market_holidays
    )
    for raw in configured.split(","):
        item = raw.strip()
        if item:
            values.add(date.fromisoformat(item))
    return frozenset(values)


COMMODITY_DAY_SESSIONS = (
    (time(9, 0), time(10, 15)),
    (time(10, 30), time(11, 30)),
    (time(13, 30), time(15, 0)),
)
CFFEX_INDEX_DAY_SESSIONS = (
    (time(9, 30), time(11, 30)),
    (time(13, 0), time(15, 0)),
)
CFFEX_BOND_DAY_SESSIONS = (
    (time(9, 30), time(11, 30)),
    (time(13, 0), time(15, 15)),
)

# 连续交易（夜盘）按品种显式列出。没有列出的新品种按“仅日盘”处理，
# 这样不会在交易所尚未开通夜盘时误触发停更熔断。
NIGHT_CLOSE_BY_PRODUCT: dict[str, time] = {
    # SHFE / INE: 贵金属、原油
    **{product: time(2, 30) for product in ("AU", "AG", "SC")},
    # SHFE / INE: 有色金属
    **{
        product: time(1, 0)
        for product in ("CU", "AL", "ZN", "PB", "NI", "SN", "SS", "AO", "BC")
    },
    # SHFE / INE: 黑色、能源化工
    **{
        product: time(23, 0)
        for product in ("RB", "HC", "RU", "BU", "FU", "SP", "NR", "LU", "BR")
    },
    # DCE
    **{
        product: time(23, 0)
        for product in (
            "A",
            "B",
            "M",
            "Y",
            "P",
            "C",
            "CS",
            "I",
            "J",
            "JM",
            "L",
            "V",
            "PP",
            "EG",
            "EB",
            "PG",
            "BZ",
        )
    },
    # CZCE
    **{
        product: time(23, 0)
        for product in (
            "TA",
            "OI",
            "RM",
            "ZC",
            "SR",
            "CF",
            "MA",
            "FG",
            "SF",
            "SM",
            "CY",
            "UR",
            "SA",
            "PF",
            "SH",
            "PX",
            "PR",
            "PL",
        )
    },
}

CFFEX_INDEX_PRODUCTS = frozenset({"IF", "IH", "IC", "IM"})
CFFEX_BOND_PRODUCTS = frozenset({"TS", "TF", "T", "TL"})


def futures_product(symbol: str | None) -> str:
    """从 IF2509 / rb0 等合约代码提取品种代码。"""
    if not symbol:
        return ""
    matched = re.match(r"[A-Za-z]+", symbol.strip())
    return matched.group(0).upper() if matched else ""


def futures_exchange(symbol: str | None) -> str | None:
    return FUTURES_EXCHANGE_BY_PRODUCT.get(futures_product(symbol))


def _within(current: time, sessions: tuple[tuple[time, time], ...]) -> bool:
    return any(start <= current < end for start, end in sessions)


def _next_weekday(value: date) -> date:
    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _night_anchor_is_open(anchor: date) -> bool:
    """夜盘需同时满足当前工作日和其后的交易日均开市，覆盖节前停夜盘。"""
    return is_trading_day(Market.FUTURES, anchor) and is_trading_day(
        Market.FUTURES, _next_weekday(anchor)
    )


def market_date(value: datetime) -> date:
    """Return the Shanghai market date for a timestamp."""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(SHANGHAI_TZ).date()


def is_trading_day(market: Market | str, value: date) -> bool:
    """Classify a trading day using the bundled exchange calendar plus overrides."""
    market = Market(market)
    if value.weekday() >= 5:
        return False
    if value in _configured_holidays(market):
        return False
    return _provider_is_session(value)


def canonical_daily_bar_time(value: datetime) -> datetime:
    """Canonicalize a daily bar to Shanghai midnight represented in UTC."""
    local_midnight = datetime.combine(market_date(value), time.min, tzinfo=SHANGHAI_TZ)
    return local_midnight.astimezone(timezone.utc)


def is_open_session(
    market: Market | str,
    value: datetime,
    *,
    symbol: str | None = None,
) -> bool:
    """Return whether a market/product is in its regular exchange session."""
    market = Market(market)
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(SHANGHAI_TZ)
    current = local.time().replace(tzinfo=None)
    if market == Market.STOCK:
        if not is_trading_day(market, local.date()):
            return False
        return time(9, 30) <= current < time(11, 30) or time(13, 0) <= current < time(15, 0)

    product = futures_product(symbol)
    exchange = futures_exchange(symbol)
    if is_trading_day(market, local.date()):
        day_sessions = COMMODITY_DAY_SESSIONS
        if exchange == "CFFEX" or product in CFFEX_INDEX_PRODUCTS | CFFEX_BOND_PRODUCTS:
            day_sessions = (
                CFFEX_BOND_DAY_SESSIONS
                if product in CFFEX_BOND_PRODUCTS
                else CFFEX_INDEX_DAY_SESSIONS
            )
        if _within(current, day_sessions):
            return True

    night_close = NIGHT_CLOSE_BY_PRODUCT.get(product)
    if night_close is None:
        return False
    if current >= time(21, 0):
        before_close = night_close < time(21, 0) or current < night_close
        return before_close and _night_anchor_is_open(local.date())
    if night_close < time(21, 0) and current < night_close:
        return _night_anchor_is_open(local.date() - timedelta(days=1))
    return False


def trading_days_between(
    market: Market | str, start: date, end: date
) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if is_trading_day(market, current):
            days.append(current)
        current += timedelta(days=1)
    return days


def shanghai_day_bounds(
    value: datetime | None = None,
) -> tuple[datetime, datetime]:
    current = value or datetime.now(timezone.utc)
    local_date = market_date(current)
    start_local = datetime.combine(local_date, time.min, tzinfo=SHANGHAI_TZ)
    end_local = datetime.combine(local_date, time.max, tzinfo=SHANGHAI_TZ)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )
