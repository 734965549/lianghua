from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.time import as_utc, utc_now
from app.core.trading_calendar import (
    canonical_daily_bar_time,
    is_trading_day,
    market_date,
)
from app.schemas.enums import Market
from app.sdk.models import KlineBar

QUALITY_ACCEPTED = "accepted"
QUALITY_QUARANTINED = "quarantined"


@dataclass(frozen=True)
class PreparedKline:
    bar: KlineBar
    quality_status: str
    reasons: tuple[str, ...]
    source: str

    @property
    def accepted(self) -> bool:
        return self.quality_status == QUALITY_ACCEPTED


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def kline_source(raw_payload: Any) -> str:
    raw = raw_payload if isinstance(raw_payload, dict) else {}
    return str(raw.get("provider") or raw.get("source") or "unknown")


def source_is_simulated(source: str, raw_payload: Any = None) -> bool:
    raw = raw_payload if isinstance(raw_payload, dict) else {}
    normalized = source.strip().lower()
    return bool(raw.get("simulated")) or normalized in {
        "mock",
        "mocktradingadapter",
        "simulated",
        "simulatedthsdriver",
    }


def kline_validation_reasons(bar: KlineBar | Any) -> list[str]:
    reasons: list[str] = []
    market = Market(bar.market)
    bar_time = bar.bar_time
    if bar_time.tzinfo is None or bar_time.utcoffset() is None:
        reasons.append("timezone_missing")

    values = {
        "open": _decimal(bar.open),
        "high": _decimal(bar.high),
        "low": _decimal(bar.low),
        "close": _decimal(bar.close),
        "volume": _decimal(bar.volume),
    }
    if any(
        values[key] is None or values[key] <= 0
        for key in ("open", "high", "low", "close")
    ):
        reasons.append("price_invalid")
    elif values["high"] < max(values["open"], values["close"]):
        reasons.append("high_below_open_or_close")
    elif values["low"] > min(values["open"], values["close"]):
        reasons.append("low_above_open_or_close")
    if values["volume"] is None or values["volume"] < 0:
        reasons.append("volume_invalid")

    raw = bar.raw_payload if isinstance(bar.raw_payload, dict) else {}
    if raw.get("quality_status") == QUALITY_QUARANTINED:
        reasons.extend(str(reason) for reason in raw.get("quality_reasons") or ())
    if bar.interval == "1d" and not is_trading_day(market, market_date(bar_time)):
        reasons.append("non_trading_day")
    return list(dict.fromkeys(reasons))


def prepare_kline(bar: KlineBar) -> PreparedKline:
    original_time = bar.bar_time
    normalized_time = (
        canonical_daily_bar_time(original_time)
        if bar.interval == "1d"
        else as_utc(original_time)
    )
    reasons = tuple(kline_validation_reasons(bar))
    status = QUALITY_QUARANTINED if reasons else QUALITY_ACCEPTED
    raw_payload = dict(bar.raw_payload or {})
    source = kline_source(raw_payload)
    raw_payload.update(
        {
            "source": source,
            "market_date": market_date(original_time).isoformat(),
            "original_bar_time": (
                original_time.isoformat()
                if original_time.tzinfo is not None
                and original_time.utcoffset() is not None
                else f"{original_time.isoformat()} (timezone missing)"
            ),
            "quality_status": status,
            "quality_reasons": list(reasons),
            "quality_checked_at": utc_now().isoformat(),
        }
    )
    return PreparedKline(
        bar=bar.model_copy(
            update={"bar_time": normalized_time, "raw_payload": raw_payload}
        ),
        quality_status=status,
        reasons=reasons,
        source=source,
    )


def is_trusted_kline(bar: KlineBar | Any) -> bool:
    return not kline_validation_reasons(bar)


def kline_identity(bar: KlineBar | Any) -> tuple:
    if bar.interval == "1d":
        return Market(bar.market), bar.symbol, bar.interval, market_date(bar.bar_time)
    return Market(bar.market), bar.symbol, bar.interval, as_utc(bar.bar_time)


def quality_metadata(bar: KlineBar | Any) -> dict[str, Any]:
    raw = bar.raw_payload if isinstance(bar.raw_payload, dict) else {}
    reasons = kline_validation_reasons(bar)
    source = kline_source(raw)
    return {
        "source": source,
        "simulated": source_is_simulated(source, raw),
        "market_date": market_date(bar.bar_time).isoformat(),
        "quality_status": QUALITY_QUARANTINED if reasons else QUALITY_ACCEPTED,
        "quality_reasons": reasons,
    }


def stamp_kline_source(
    bars: list[KlineBar], source: str
) -> list[KlineBar]:
    stamped: list[KlineBar] = []
    for bar in bars:
        raw_payload = dict(bar.raw_payload or {})
        raw_payload.setdefault("provider", source)
        stamped.append(bar.model_copy(update={"raw_payload": raw_payload}))
    return stamped
