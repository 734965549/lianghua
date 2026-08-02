"""可交易标的目录同步与持久化。"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.instrument import Instrument
from app.db.session import SessionLocal
from app.schemas.enums import Market
from app.sdk import manager as sdk_manager

logger = logging.getLogger(__name__)


class InstrumentCatalogService:
    def __init__(self) -> None:
        self._sync_lock = threading.Lock()
        self._sync_thread: threading.Thread | None = None

    def sync_all(self, db: Session) -> dict[str, Any]:
        """从当前行情源同步股票及期货目录；单个市场失败不覆盖已有目录。"""
        if not self._sync_lock.acquire(blocking=False):
            return {"status": "running", "counts": self.counts(db), "errors": []}
        counts: dict[str, int] = {}
        errors: list[str] = []
        try:
            # 期货目录是轻量品种表，优先落库，避免等待 A 股全市场分页同步。
            for market in (Market.FUTURES, Market.STOCK):
                try:
                    adapter = sdk_manager.get_adapter_for_market(market)
                    loader = getattr(adapter, "list_instruments", None)
                    if not callable(loader):
                        raise RuntimeError(f"{adapter.name} 不支持标的目录同步")
                    records = loader()
                    if not records:
                        raise RuntimeError("行情源返回空目录")
                    self._replace_market(db, market, records, source=adapter.name)
                    db.commit()
                    counts[market.value] = len(records)
                except Exception as exc:
                    db.rollback()
                    logger.exception("同步 %s 标的目录失败", market.value)
                    errors.append(f"{market.value}: {exc}")
            return {
                "status": "partial" if errors and counts else "failed" if errors else "ok",
                "counts": {**self.counts(db), **counts},
                "errors": errors,
            }
        finally:
            self._sync_lock.release()

    def start_background_sync(self) -> bool:
        if self._sync_thread and self._sync_thread.is_alive():
            return False
        try:
            adapters = (
                sdk_manager.get_stock_adapter(),
                sdk_manager.get_futures_adapter(),
            )
        except Exception:
            logger.exception("初始化标的目录同步失败")
            return False
        if not any(
            getattr(adapter, "name", "") in {"ifind", "akshare"}
            for adapter in adapters
        ):
            return False

        def run() -> None:
            db = SessionLocal()
            try:
                self.sync_all(db)
            finally:
                db.close()

        self._sync_thread = threading.Thread(
            target=run,
            name="instrument-catalog-sync",
            daemon=True,
        )
        self._sync_thread.start()
        return True

    def counts(self, db: Session) -> dict[str, int]:
        rows = (
            db.query(Instrument.market, func.count(Instrument.id))
            .filter(Instrument.is_active.is_(True))
            .group_by(Instrument.market)
            .all()
        )
        return {
            (market.value if isinstance(market, Market) else str(market)): int(count)
            for market, count in rows
        }

    def _replace_market(
        self,
        db: Session,
        market: Market,
        records: list[dict[str, Any]],
        *,
        source: str,
    ) -> None:
        db.query(Instrument).filter(Instrument.market == market).update(
            {Instrument.is_active: False},
            synchronize_session=False,
        )
        synced_at = datetime.now(timezone.utc)
        for item in records:
            raw_payload = dict(item.get("raw_payload") or {})
            raw_payload.update(
                {"catalog_source": source, "catalog_synced_at": synced_at.isoformat()}
            )
            stmt = insert(Instrument).values(
                symbol=str(item["symbol"]).strip().upper(),
                market=market,
                name=str(item.get("name") or item["symbol"])[:128],
                exchange=str(item.get("exchange") or "")[:32],
                price_tick=Decimal(str(item.get("price_tick") or "0")),
                lot_size=Decimal(str(item.get("lot_size") or "1")),
                multiplier=Decimal(str(item.get("multiplier") or "1")),
                is_active=True,
                raw_payload=raw_payload,
                updated_at=synced_at,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uk_instruments_market_symbol",
                set_={
                    "name": stmt.excluded.name,
                    "exchange": stmt.excluded.exchange,
                    "price_tick": stmt.excluded.price_tick,
                    "lot_size": stmt.excluded.lot_size,
                    "multiplier": stmt.excluded.multiplier,
                    "is_active": True,
                    "raw_payload": stmt.excluded.raw_payload,
                    "updated_at": synced_at,
                },
            )
            db.execute(stmt)


instrument_catalog_service = InstrumentCatalogService()
