"""K-line data quality checks and trusted-data statistics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.trading_calendar import market_date, trading_days_between
from app.db.models.kline_bar import KlineBar as KlineBarModel
from app.db.models.market_snapshot import MarketSnapshot
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Market, Severity
from app.services.kline_quality import (
    is_trusted_kline,
    kline_identity,
    kline_validation_reasons,
)

logger = logging.getLogger(__name__)


def _is_valid_ohlc(
    open_: Decimal, high: Decimal, low: Decimal, close: Decimal
) -> bool:
    return (
        all(value.is_finite() and value > 0 for value in (open_, high, low, close))
        and high >= max(open_, close)
        and low <= min(open_, close)
    )


def check_symbol_klines(
    db: Session,
    *,
    market: Market,
    symbol: str,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    query = db.query(KlineBarModel).filter(
        KlineBarModel.market == market,
        KlineBarModel.symbol == symbol,
        KlineBarModel.interval == interval,
    )
    if start is not None:
        query = query.filter(KlineBarModel.bar_time >= start)
    if end is not None:
        query = query.filter(KlineBarModel.bar_time <= end)
    rows = query.order_by(KlineBarModel.bar_time, KlineBarModel.created_at).all()
    if not rows:
        return {
            "symbol": symbol,
            "market": market.value,
            "interval": interval,
            "count": 0,
            "raw_count": 0,
            "quarantined_count": 0,
            "duplicate_count": 0,
            "issues": [],
            "issue_count": 0,
            "health": "red",
        }

    issues: list[dict] = []
    seen: set[tuple] = set()
    trusted_rows: list[KlineBarModel] = []
    quarantined_count = 0
    duplicate_count = 0
    previous_close: Decimal | None = None
    suspended_streak = 0

    for row in rows:
        close = Decimal(str(row.close))
        volume = Decimal(str(row.volume or 0))
        if previous_close is not None and close == previous_close and volume == 0:
            suspended_streak += 1
        else:
            suspended_streak = 0
        if suspended_streak >= 3:
            issues.append(
                {
                    "type": "suspended",
                    "bar_time": row.bar_time.isoformat(),
                    "days": suspended_streak,
                }
            )
        previous_close = close

        reasons = kline_validation_reasons(row)
        for reason in reasons:
            issues.append(
                {
                    "type": reason,
                    "bar_time": row.bar_time.isoformat(),
                    "source": (row.raw_payload or {}).get("source", "unknown"),
                }
            )
        if reasons:
            quarantined_count += 1
            continue

        identity = kline_identity(row)
        if identity in seen:
            duplicate_count += 1
            issues.append(
                {
                    "type": "duplicate_trading_period",
                    "bar_time": row.bar_time.isoformat(),
                    "market_date": market_date(row.bar_time).isoformat(),
                }
            )
            continue
        seen.add(identity)
        trusted_rows.append(row)

    missing_days = 0
    if interval == "1d" and trusted_rows:
        present = {market_date(row.bar_time) for row in trusted_rows}
        expected_start = market_date(start) if start is not None else min(present)
        expected_end = market_date(end) if end is not None else max(present)
        expected = trading_days_between(market, expected_start, expected_end)
        missing_days = sum(day not in present for day in expected)
        if missing_days:
            issues.append({"type": "missing_trading_days", "days": missing_days})

    health = "green"
    if issues:
        health = "yellow" if len(issues) < 5 else "red"
    return {
        "symbol": symbol,
        "market": market.value,
        "interval": interval,
        "count": len(trusted_rows),
        "raw_count": len(rows),
        "quarantined_count": quarantined_count,
        "duplicate_count": duplicate_count,
        "start": trusted_rows[0].bar_time.isoformat() if trusted_rows else None,
        "end": trusted_rows[-1].bar_time.isoformat() if trusted_rows else None,
        "missing_days": missing_days,
        "issues": issues[:20],
        "issue_count": len(issues),
        "health": health,
    }


def evaluate_data_quality_gate(
    db: Session,
    *,
    targets: list[tuple[Market, str]],
    interval: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    """Evaluate the hard admission gate used by live trading and formal backtests."""
    reports = [
        check_symbol_klines(
            db,
            market=market,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
        )
        for market, symbol in targets
    ]
    blockers: list[dict] = []
    for report in reports:
        reasons: list[str] = []
        if report["raw_count"] == 0:
            reasons.append("no_data")
        if report["quarantined_count"] > 0:
            reasons.append("quarantined_records")
        if report["duplicate_count"] > 0:
            reasons.append("duplicate_trading_periods")
        if interval == "1d" and report.get("missing_days", 0) > 0:
            reasons.append("missing_daily_bars")
        if reasons:
            blockers.append(
                {
                    "market": report["market"],
                    "symbol": report["symbol"],
                    "interval": report["interval"],
                    "reasons": reasons,
                    "quarantined_count": report["quarantined_count"],
                    "duplicate_count": report["duplicate_count"],
                    "missing_days": report.get("missing_days", 0),
                }
            )

    labels = {
        "no_data": "无可用数据",
        "quarantined_records": "存在隔离记录",
        "duplicate_trading_periods": "存在重复周期",
        "missing_daily_bars": "存在日线缺口",
    }
    descriptions = [
        f"{item['symbol']}：{'、'.join(labels[reason] for reason in item['reasons'])}"
        for item in blockers[:5]
    ]
    return {
        "ready": not blockers,
        "interval": interval,
        "checked": len(reports),
        "blockers": blockers,
        "reason": "；".join(descriptions),
    }


def run_quality_check(db: Session, *, correlation_id: str = "data_quality") -> dict:
    symbols = (
        db.query(KlineBarModel.market, KlineBarModel.symbol, KlineBarModel.interval)
        .group_by(KlineBarModel.market, KlineBarModel.symbol, KlineBarModel.interval)
        .all()
    )
    results: list[dict] = []
    event_repo = SystemEventRepository(db)
    total_issues = 0

    for market, symbol, interval in symbols:
        report = check_symbol_klines(
            db, market=market, symbol=symbol, interval=interval
        )
        results.append(report)
        if report["issue_count"] > 0:
            total_issues += report["issue_count"]
            severity = (
                Severity.WARNING if report["health"] == "yellow" else Severity.ERROR
            )
            event_repo.add(
                module="data_quality",
                event_code="KLINE_QUALITY_ISSUE",
                message=f"{symbol} {interval} found {report['issue_count']} quality issues",
                severity=severity,
                payload={**report, "correlation_id": correlation_id},
            )

    if total_issues == 0:
        event_repo.add(
            module="data_quality",
            event_code="KLINE_QUALITY_OK",
            message=f"Quality check passed for {len(results)} K-line groups",
            severity=Severity.INFO,
            payload={"checked": len(results), "correlation_id": correlation_id},
        )

    db.flush()
    logger.info(
        "K-line quality check completed: %d groups, %d issues",
        len(results),
        total_issues,
    )
    return {
        "checked": len(results),
        "total_issues": total_issues,
        "reports": results,
    }


def integrity_report(db: Session) -> dict:
    groups = (
        db.query(KlineBarModel.market, KlineBarModel.symbol, KlineBarModel.interval)
        .group_by(KlineBarModel.market, KlineBarModel.symbol, KlineBarModel.interval)
        .order_by(KlineBarModel.symbol, KlineBarModel.interval)
        .all()
    )
    items = [
        check_symbol_klines(db, market=market, symbol=symbol, interval=interval)
        for market, symbol, interval in groups
    ]
    return {
        "kline_groups": len(items),
        "raw_total": sum(item["raw_count"] for item in items),
        "trusted_total": sum(item["count"] for item in items),
        "quarantined_total": sum(item["quarantined_count"] for item in items),
        "duplicate_total": sum(item["duplicate_count"] for item in items),
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def data_overview(db: Session) -> dict:
    rows = db.query(KlineBarModel).all()
    trusted_identities: set[tuple] = set()
    trusted_symbols: set[str] = set()
    quarantined = 0
    duplicates = 0
    for row in rows:
        if not is_trusted_kline(row):
            quarantined += 1
            continue
        identity = kline_identity(row)
        if identity in trusted_identities:
            duplicates += 1
            continue
        trusted_identities.add(identity)
        trusted_symbols.add(row.symbol)

    snapshot_total = db.query(func.count(MarketSnapshot.id)).scalar() or 0
    snapshot_symbols = db.query(MarketSnapshot.symbol).distinct().count()
    return {
        "kline_total": len(rows),
        "kline_trusted": len(trusted_identities),
        "kline_quarantined": quarantined,
        "kline_duplicates": duplicates,
        "kline_symbols": len(trusted_symbols),
        "snapshot_total": snapshot_total,
        "snapshot_symbols": snapshot_symbols,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
