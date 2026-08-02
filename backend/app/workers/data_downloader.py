"""历史 K 线批量下载引擎。"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.api.ws_hub import broadcast_sync
from app.db.session import SessionLocal
from app.repositories.data_sync_log_repo import DataSyncLogRepository
from app.repositories.market_repo import MarketRepository
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Market, Severity
from app.sdk import manager as sdk_manager
from app.services.kline_quality import stamp_kline_source

logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 2.5
MAX_RETRIES = 3
ITEM_TIMEOUT_SECONDS = 90
TASK_TIMEOUT_SECONDS = 30 * 60


class DownloadCancelled(RuntimeError):
    pass


class DownloadTimedOut(RuntimeError):
    pass


class DataDownloader:
    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._current_task_id: uuid.UUID | None = None
        self._progress: dict = {}
        self._cancel_event = threading.Event()
        self._started_monotonic: float | None = None
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_task_id(self) -> str | None:
        return str(self._current_task_id) if self._current_task_id else None

    def get_progress(self) -> dict:
        with self._lock:
            return dict(self._progress)

    def cancel(self, task_id: str | None = None) -> bool:
        with self._lock:
            if not self._running or self._current_task_id is None:
                return False
            if task_id and str(self._current_task_id) != task_id:
                return False
            self._cancel_event.set()
            self._progress = {
                **self._progress,
                "status": "cancelling",
                "message": "已请求取消，等待当前数据源调用结束",
            }
            return True

    def start_download(
        self,
        *,
        symbols: list[tuple[Market, str]],
        intervals: list[str],
        start_date: str,
        end_date: str | None = None,
        task_type: str = "download",
    ) -> str:
        with self._lock:
            if self._running:
                raise RuntimeError("已有下载任务正在运行")
            self._running = True
            self._cancel_event.clear()
            self._started_monotonic = time.monotonic()

        db = SessionLocal()
        try:
            repo = DataSyncLogRepository(db)
            sym_names = [s for _, s in symbols]
            task = repo.create_task(
                task_type=task_type,
                symbols=sym_names,
                intervals=intervals,
                start_date=start_date,
                end_date=end_date,
            )
            db.commit()
            task_id = task.id
        finally:
            db.close()

        self._current_task_id = task_id
        total = len(symbols) * len(intervals)
        self._progress = {"task_id": str(task_id), "done": 0, "total": total, "items": {}, "status": "running"}

        thread = threading.Thread(
            target=self._run_download,
            args=(task_id, symbols, intervals, start_date, end_date),
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return str(task_id)

    def _run_download(
        self,
        task_id: uuid.UUID,
        symbols: list[tuple[Market, str]],
        intervals: list[str],
        start_date: str,
        end_date: str | None,
    ) -> None:
        db = SessionLocal()
        log_repo = DataSyncLogRepository(db)
        market_repo = MarketRepository(db)
        try:
            log_repo.mark_running(task_id)
            db.commit()

            end_dt = self._parse_date(end_date) if end_date else datetime.now(timezone.utc)
            start_dt = self._parse_date(start_date)
            done = 0
            total = len(symbols) * len(intervals)
            items: dict[str, dict] = {}

            for market, symbol in symbols:
                for interval in intervals:
                    self._raise_if_stopped()
                    key = f"{symbol}:{interval}"
                    items[key] = {"status": "downloading", "symbol": symbol, "interval": interval}
                    self._update_progress(db, log_repo, task_id, done, total, items)

                    try:
                        bars = self._fetch_with_retry(market, symbol, interval, start_dt, end_dt)
                        self._raise_if_stopped()
                        outcome = {
                            "received": 0,
                            "accepted": 0,
                            "quarantined": 0,
                            "deduplicated": 0,
                            "quarantine_reasons": [],
                        }
                        if bars:
                            outcome = market_repo.upsert_klines(bars)
                            if outcome["quarantined"]:
                                SystemEventRepository(db).add(
                                    module="data_quality",
                                    event_code="KLINE_QUARANTINED",
                                    message=(
                                        f"{symbol} {interval}: "
                                        f"{outcome['quarantined']} bars quarantined"
                                    ),
                                    severity=Severity.ERROR,
                                    payload={
                                        "task_id": str(task_id),
                                        **outcome,
                                    },
                                )
                            db.commit()
                        items[key] = {
                            "status": "done",
                            "symbol": symbol,
                            "interval": interval,
                            "count": outcome["accepted"],
                            "received": outcome["received"],
                            "quarantined": outcome["quarantined"],
                            "deduplicated": outcome["deduplicated"],
                        }
                    except Exception as exc:
                        logger.exception("下载失败 %s %s", symbol, interval)
                        items[key] = {
                            "status": "failed",
                            "symbol": symbol,
                            "interval": interval,
                            "error": str(exc),
                        }

                    done += 1
                    self._update_progress(db, log_repo, task_id, done, total, items)
                    if self._cancel_event.wait(RATE_LIMIT_SECONDS):
                        raise DownloadCancelled("用户取消了下载任务")

            log_repo.mark_done(task_id)
            db.commit()
            with self._lock:
                self._progress["status"] = "done"
                self._progress["done"] = done
        except DownloadCancelled as exc:
            db.rollback()
            log_repo.mark_cancelled(task_id, str(exc))
            db.commit()
            with self._lock:
                self._progress = {
                    **self._progress,
                    "status": "cancelled",
                    "error": str(exc),
                }
        except DownloadTimedOut as exc:
            db.rollback()
            log_repo.mark_failed(task_id, str(exc))
            db.commit()
            with self._lock:
                self._progress = {
                    **self._progress,
                    "status": "failed",
                    "error": str(exc),
                }
        except Exception as exc:
            logger.exception("批量下载任务失败")
            db.rollback()
            log_repo.mark_failed(task_id, str(exc))
            db.commit()
            with self._lock:
                self._progress["status"] = "failed"
                self._progress["error"] = str(exc)
        finally:
            with self._lock:
                self._running = False
                self._current_task_id = None
                self._started_monotonic = None
                self._thread = None
            db.close()
            broadcast_sync("data.download.progress", self.get_progress())

    def _update_progress(
        self,
        db: Session,
        log_repo: DataSyncLogRepository,
        task_id: uuid.UUID,
        done: int,
        total: int,
        items: dict,
    ) -> None:
        progress = {
            "done": done,
            "total": total,
            "items": items,
            "status": "running",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._progress = {"task_id": str(task_id), **progress}
        log_repo.update_progress(task_id, progress)
        db.commit()
        broadcast_sync("data.download.progress", self.get_progress())

    def _fetch_with_retry(
        self,
        market: Market,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list:
        adapter = sdk_manager.get_adapter_for_market(market)
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self._raise_if_stopped()
            try:
                bars = self._call_with_timeout(
                    lambda: adapter.get_kline(symbol, interval, start, end),
                    ITEM_TIMEOUT_SECONDS,
                )
                source = str(
                    getattr(adapter, "name", adapter.__class__.__name__)
                ).lower()
                return stamp_kline_source(bars, source)
            except Exception as exc:
                last_exc = exc
                wait = (2**attempt) * RATE_LIMIT_SECONDS
                logger.warning("重试 %s %s (%d/%d): %s", symbol, interval, attempt + 1, MAX_RETRIES, exc)
                if self._cancel_event.wait(wait):
                    raise DownloadCancelled("用户取消了下载任务") from exc
        if last_exc:
            raise last_exc
        return []

    def _raise_if_stopped(self) -> None:
        if self._cancel_event.is_set():
            raise DownloadCancelled("用户取消了下载任务")
        if (
            self._started_monotonic is not None
            and time.monotonic() - self._started_monotonic > TASK_TIMEOUT_SECONDS
        ):
            raise DownloadTimedOut(
                f"下载任务超过 {TASK_TIMEOUT_SECONDS // 60} 分钟，已自动终止"
            )

    @staticmethod
    def _call_with_timeout(call, timeout_seconds: int):
        result: list = []
        error: list[BaseException] = []

        def invoke() -> None:
            try:
                result.append(call())
            except BaseException as exc:  # 在线程边界保留原始异常
                error.append(exc)

        worker = threading.Thread(target=invoke, daemon=True)
        worker.start()
        worker.join(timeout_seconds)
        if worker.is_alive():
            raise TimeoutError(f"单个数据源调用超过 {timeout_seconds} 秒")
        if error:
            raise error[0]
        return result[0] if result else []

    @staticmethod
    def _parse_date(s: str) -> datetime:
        return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)


data_downloader = DataDownloader()
