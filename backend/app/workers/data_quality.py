"""K 线数据质量校验。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.kline_bar import KlineBar as KlineBarModel
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Market, Severity

logger = logging.getLogger(__name__)


def _is_valid_ohlc(open_: Decimal, high: Decimal, low: Decimal, close: Decimal) -> bool:
    if any(v < 0 for v in (open_, high, low, close)):
        return False
    if high < max(open_, close):
        return False
    if low > min(open_, close):
        return False
    return True


def check_symbol_klines(
    db: Session,
    *,
    market: Market,
    symbol: str,
    interval: str = "1d",
) -> dict:
    """校验单标的 K 线，返回问题列表。"""
    rows = (
        db.query(KlineBarModel)
        .filter(
            KlineBarModel.market == market,
            KlineBarModel.symbol == symbol,
            KlineBarModel.interval == interval,
        )
        .order_by(KlineBarModel.bar_time)
        .all()
    )
    issues: list[dict] = []
    if not rows:
        return {"symbol": symbol, "interval": interval, "count": 0, "issues": [], "health": "red"}

    prev_date: datetime | None = None
    zero_vol_streak = 0
    for bar in rows:
        o, h, l, c = Decimal(str(bar.open)), Decimal(str(bar.high)), Decimal(str(bar.low)), Decimal(str(bar.close))
        if not _is_valid_ohlc(o, h, l, c):
            issues.append({"type": "ohlc_invalid", "bar_time": bar.bar_time.isoformat()})
        vol = Decimal(str(bar.volume or 0))
        if vol == 0:
            zero_vol_streak += 1
        else:
            zero_vol_streak = 0
        if zero_vol_streak >= 3:
            issues.append({"type": "suspended", "bar_time": bar.bar_time.isoformat(), "days": zero_vol_streak})

        if interval == "1d" and prev_date is not None:
            gap = (bar.bar_time.date() - prev_date.date()).days
            if gap > 5:
                issues.append({"type": "gap", "from": prev_date.isoformat(), "to": bar.bar_time.isoformat(), "days": gap})
        prev_date = bar.bar_time

    health = "green"
    if issues:
        health = "yellow" if len(issues) < 5 else "red"
    return {
        "symbol": symbol,
        "market": market.value,
        "interval": interval,
        "count": len(rows),
        "start": rows[0].bar_time.isoformat(),
        "end": rows[-1].bar_time.isoformat(),
        "issues": issues[:20],
        "issue_count": len(issues),
        "health": health,
    }


def run_quality_check(db: Session, *, correlation_id: str = "data_quality") -> dict:
    """对数据库中所有 K 线标的执行质量检查，写入 system_events。"""
    symbols = (
        db.query(KlineBarModel.market, KlineBarModel.symbol, KlineBarModel.interval)
        .group_by(KlineBarModel.market, KlineBarModel.symbol, KlineBarModel.interval)
        .all()
    )
    results: list[dict] = []
    event_repo = SystemEventRepository(db)
    total_issues = 0

    for market, symbol, interval in symbols:
        report = check_symbol_klines(db, market=market, symbol=symbol, interval=interval)
        results.append(report)
        if report["issue_count"] > 0:
            total_issues += report["issue_count"]
            severity = Severity.WARNING if report["health"] == "yellow" else Severity.ERROR
            event_repo.add(
                module="data_quality",
                event_code="KLINE_QUALITY_ISSUE",
                message=f"{symbol} {interval} 发现 {report['issue_count']} 个数据质量问题",
                severity=severity,
                payload=report,
            )

    if total_issues == 0:
        event_repo.add(
            module="data_quality",
            event_code="KLINE_QUALITY_OK",
            message=f"质量检查通过，共 {len(results)} 组 K 线",
            severity=Severity.INFO,
            payload={"checked": len(results)},
        )

    db.flush()
    logger.info("数据质量检查完成: %d 组, %d 问题", len(results), total_issues)
    return {"checked": len(results), "total_issues": total_issues, "reports": results}


def integrity_report(db: Session) -> dict:
    """数据完整性报告：每个标的的 K 线覆盖范围。"""
    rows = (
        db.query(
            KlineBarModel.market,
            KlineBarModel.symbol,
            KlineBarModel.interval,
            func.count(KlineBarModel.id).label("count"),
            func.min(KlineBarModel.bar_time).label("start_time"),
            func.max(KlineBarModel.bar_time).label("end_time"),
        )
        .group_by(KlineBarModel.market, KlineBarModel.symbol, KlineBarModel.interval)
        .order_by(KlineBarModel.symbol, KlineBarModel.interval)
        .all()
    )
    items = []
    for r in rows:
        start = r.start_time
        end = r.end_time
        missing_days = 0
        if r.interval == "1d" and start and end:
            expected = (end.date() - start.date()).days + 1
            missing_days = max(0, expected - r.count)
        items.append({
            "market": r.market.value if isinstance(r.market, Market) else r.market,
            "symbol": r.symbol,
            "interval": r.interval,
            "count": r.count,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "missing_days": missing_days,
        })

    snapshot_count = db.query(func.count()).select_from(
        db.query(KlineBarModel).subquery()
    ).scalar()
    _ = snapshot_count  # placeholder for future snapshot stats

    return {
        "kline_groups": len(items),
        "items": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def data_overview(db: Session) -> dict:
    """数据概览统计。"""
    kline_total = db.query(func.count(KlineBarModel.id)).scalar() or 0
    symbol_count = (
        db.query(KlineBarModel.symbol)
        .distinct()
        .count()
    )
    from app.db.models.market_snapshot import MarketSnapshot

    snapshot_total = db.query(func.count(MarketSnapshot.id)).scalar() or 0
    snapshot_symbols = db.query(MarketSnapshot.symbol).distinct().count()

    return {
        "kline_total": kline_total,
        "kline_symbols": symbol_count,
        "snapshot_total": snapshot_total,
        "snapshot_symbols": snapshot_symbols,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
