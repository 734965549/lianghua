import logging
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.api.ws_hub import broadcast_sync
from app.broker import manager as broker_manager
from app.core.time import to_utc_iso
from app.db.session import SessionLocal
from app.repositories.market_repo import MarketRepository
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Market, Severity
from app.sdk import manager as sdk_manager
from app.sdk.models import KlineBar, QuoteSnapshot
from app.sdk.normalization import is_plausible_change_rate, max_abs_change_rate
from app.services.kline_quality import (
    kline_source,
    quality_metadata,
    source_is_simulated,
    stamp_kline_source,
)

logger = logging.getLogger(__name__)

DEFAULT_SUBSCRIPTIONS: dict[Market, list[str]] = {
    Market.STOCK: ["600000.SH"],
    Market.FUTURES: ["IF2509"],
}

STALE_THRESHOLD_SECONDS = 10


def _decimal_str(value: Decimal | float | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(Decimal(str(value)))


def quote_validation_error(quote: QuoteSnapshot) -> str | None:
    """返回行情隔离原因；None 表示可进入策略、风控和交易链路。"""
    if not quote.symbol.strip():
        return "标的代码为空"
    if not quote.last_price.is_finite() or quote.last_price <= 0:
        return "最新价必须为有限正数"
    if not quote.change_rate.is_finite():
        return "涨跌幅不是有限数值"
    max_rate = max_abs_change_rate(quote.market, quote.symbol)
    if not is_plausible_change_rate(
        quote.market, quote.symbol, quote.change_rate
    ):
        return f"涨跌幅 {quote.change_rate} 超出 {quote.market.value} 市场范围 ±{max_rate}"
    if not quote.volume.is_finite() or quote.volume < 0:
        return "成交量必须为有限非负数"
    if quote.quote_time.tzinfo is None or quote.quote_time.utcoffset() is None:
        return "行情时间缺少时区"
    if quote.bid_price is not None and (
        not quote.bid_price.is_finite() or quote.bid_price < 0
    ):
        return "买一价必须为有限非负数"
    if quote.ask_price is not None and (
        not quote.ask_price.is_finite() or quote.ask_price < 0
    ):
        return "卖一价必须为有限非负数"
    if (
        quote.bid_price is not None
        and quote.ask_price is not None
        and quote.bid_price > 0
        and quote.ask_price > 0
        and quote.bid_price > quote.ask_price
    ):
        return "买一价高于卖一价"
    return None


def quote_to_dict(
    quote: QuoteSnapshot | object, *, fallback_source: str | None = None
) -> dict:
    """将 QuoteSnapshot 或 ORM 行序列化为 API 响应。"""
    raw_payload = quote.raw_payload if isinstance(quote.raw_payload, dict) else {}
    source = str(
        raw_payload.get("provider")
        or raw_payload.get("source")
        or fallback_source
        or "unknown"
    ).lower()
    if isinstance(quote, QuoteSnapshot):
        return {
            "symbol": quote.symbol,
            "market": quote.market.value if isinstance(quote.market, Market) else quote.market,
            "last_price": _decimal_str(quote.last_price),
            "change_rate": _decimal_str(quote.change_rate),
            "volume": _decimal_str(quote.volume),
            "bid_price": _decimal_str(quote.bid_price),
            "ask_price": _decimal_str(quote.ask_price),
            "quote_time": to_utc_iso(quote.quote_time),
            "source": source,
            "simulated": source_is_simulated(source, raw_payload),
        }
    return {
        "symbol": quote.symbol,
        "market": quote.market.value if isinstance(quote.market, Market) else quote.market,
        "last_price": _decimal_str(quote.last_price),
        "change_rate": _decimal_str(quote.change_rate),
        "volume": _decimal_str(quote.volume),
        "bid_price": _decimal_str(quote.bid_price),
        "ask_price": _decimal_str(quote.ask_price),
        "quote_time": to_utc_iso(quote.quote_time),
        "source": source,
        "simulated": source_is_simulated(source, raw_payload),
    }


def kline_to_dict(bar: KlineBar | object) -> dict:
    quality = quality_metadata(bar)
    if isinstance(bar, KlineBar):
        return {
            "symbol": bar.symbol,
            "market": bar.market.value if isinstance(bar.market, Market) else bar.market,
            "interval": bar.interval,
            "bar_time": to_utc_iso(bar.bar_time),
            "open": _decimal_str(bar.open),
            "high": _decimal_str(bar.high),
            "low": _decimal_str(bar.low),
            "close": _decimal_str(bar.close),
            "volume": _decimal_str(bar.volume),
            **quality,
        }
    return {
        "symbol": bar.symbol,
        "market": bar.market.value if isinstance(bar.market, Market) else bar.market,
        "interval": bar.interval,
        "bar_time": to_utc_iso(bar.bar_time),
        "open": _decimal_str(bar.open),
        "high": _decimal_str(bar.high),
        "low": _decimal_str(bar.low),
        "close": _decimal_str(bar.close),
        "volume": _decimal_str(bar.volume),
        **quality,
    }


class MarketService:
    def __init__(self):
        self._subscribed: dict[Market, set[str]] = {
            Market.STOCK: set(),
            Market.FUTURES: set(),
        }
        self._started = False
        self._reconfigure_lock = threading.Lock()

    @property
    def started(self) -> bool:
        return self._started

    def start(self) -> None:
        if self._started:
            return
        sdk_manager.ensure_connected()
        sdk_manager.get_stock_adapter().on_quote_update(self._handle_quote)
        sdk_manager.get_futures_adapter().on_quote_update(self._handle_quote)
        from app.services.order_service import order_service
        from app.services.trade_service import trade_service

        # 通过 Broker 抽象层注册订单/成交回调，避免与 AdapterBroker 互相覆盖
        for market in (Market.STOCK, Market.FUTURES):
            broker = broker_manager.get_broker(market)
            broker.on_order_update(order_service.on_order_update)
            broker.on_trade_update(trade_service.on_trade_update)
            # TqSdk 直接接入：主动连接期货交易通道（live 与只读均需登录才可查询）
            broker_name = getattr(broker, "name", "")
            if broker_name == "tqsdk":
                try:
                    broker.connect()
                except Exception:
                    logger.exception("%s 交易通道启动失败，将保持未就绪状态", broker_name.upper())


        db = SessionLocal()
        try:
            from app.services.watchlist_service import watchlist_service

            watchlist_service.ensure_defaults(db)
            subs = watchlist_service.get_enabled_subscriptions(db)
            db.commit()
        finally:
            db.close()

        for market, symbols in subs.items():
            if symbols:
                self.subscribe(symbols, market)
        self._started = True
        logger.info("MarketService 已启动，股票池订阅 %s", subs)

    def stop(self) -> None:
        if not self._started:
            return
        try:
            sdk_manager.get_stock_adapter().disconnect()
        except Exception:
            logger.debug("停止 stock adapter 异常", exc_info=True)
        try:
            sdk_manager.get_futures_adapter().disconnect()
        except Exception:
            logger.debug("停止 futures adapter 异常", exc_info=True)
        # 主动断开直接 Broker
        for market in (Market.STOCK, Market.FUTURES):
            try:
                broker = broker_manager.get_broker(market)
                broker_name = getattr(broker, "name", "")
                if broker_name in {"tqsdk", "qmt", "ptrade"}:
                    broker.disconnect()
            except Exception:
                logger.debug("停止 broker %s 异常", market.value, exc_info=True)
        self._started = False

    def reconfigure(self) -> None:
        """应用最新行情源配置并恢复当前订阅，无需重启整个后端。"""
        with self._reconfigure_lock:
            previous_subscriptions = {
                market: set(symbols) for market, symbols in self._subscribed.items()
            }
            self.stop()
            sdk_manager.reset_adapters()
            broker_manager.reset_brokers()
            self._subscribed = {
                Market.STOCK: set(),
                Market.FUTURES: set(),
            }
            try:
                self.start()
                for market, symbols in previous_subscriptions.items():
                    if symbols:
                        self.subscribe(sorted(symbols), market)
            except Exception:
                self._started = False
                logger.exception("行情源热切换失败")
                raise

    def _handle_quote(self, quote: QuoteSnapshot) -> None:
        db = SessionLocal()
        try:
            raw_payload = dict(quote.raw_payload or {})
            raw_payload.setdefault("provider", self._source_name(quote.market))
            quote = quote.model_copy(update={"raw_payload": raw_payload})
            validation_error = quote_validation_error(quote)
            if validation_error:
                payload = quote_to_dict(quote)
                payload["reason"] = validation_error
                payload["source"] = (
                    quote.raw_payload.get("provider")
                    if isinstance(quote.raw_payload, dict)
                    else None
                )
                SystemEventRepository(db).add(
                    module="market_data",
                    event_code="QUOTE_QUARANTINED",
                    message=f"{quote.symbol} 行情已隔离：{validation_error}",
                    severity=Severity.ERROR,
                    payload=payload,
                )
                db.commit()
                broadcast_sync("quote.quarantined", payload)
                logger.warning("隔离异常行情 %s: %s", quote.symbol, validation_error)
                return

            repo = MarketRepository(db)
            repo.insert_snapshot(quote)
            db.commit()
            broadcast_sync("quote.update", quote_to_dict(quote))
            from app.services.strategy_service import strategy_service

            try:
                strategy_service.dispatch_quote(quote)
            except Exception:
                logger.exception("策略行情分发失败: %s", quote.symbol)
        except Exception:
            logger.exception("处理行情更新失败: %s", quote.symbol)
            db.rollback()
        finally:
            db.close()

    def subscribe(self, symbols: list[str], market: Market | str) -> list[str]:
        if isinstance(market, str):
            market = Market(market)
        adapter = sdk_manager.get_adapter_for_market(market)
        if not self._started:
            adapter.connect()
        adapter.subscribe_quotes(symbols)
        self._subscribed[market].update(symbols)
        return symbols

    def unsubscribe(self, symbols: list[str], market: Market | str) -> list[str]:
        if isinstance(market, str):
            market = Market(market)
        adapter = sdk_manager.get_adapter_for_market(market)
        adapter.unsubscribe_quotes(symbols)
        self._subscribed[market].difference_update(symbols)
        return symbols

    def get_subscribed(self) -> list[tuple[Market, str]]:
        result: list[tuple[Market, str]] = []
        for mkt, symbols in self._subscribed.items():
            for sym in symbols:
                result.append((mkt, sym))
        return result

    def sync_watchlist_subscriptions(self, db: Session) -> None:
        """根据股票池变更同步订阅。"""
        from app.services.watchlist_service import watchlist_service

        subs = watchlist_service.get_enabled_subscriptions(db)
        for market, symbols in subs.items():
            current = self._subscribed.get(market, set())
            desired = set(symbols)
            to_add = desired - current
            if to_add:
                self.subscribe(list(to_add), market)
            # 暂不自动取消订阅，避免短暂禁用导致丢行情

    def list_quotes(
        self,
        db: Session,
        *,
        market: Market | str | None = None,
        symbols: list[str] | None = None,
    ) -> list[dict]:
        if isinstance(market, str):
            market = Market(market)
        repo = MarketRepository(db)
        rows = repo.list_latest_quotes(market=market, symbols=symbols)
        return [
            quote_to_dict(r, fallback_source=self._source_name(r.market))
            for r in rows
        ]

    def get_quote(self, db: Session, market: Market | str, symbol: str) -> dict:
        if isinstance(market, str):
            market = Market(market)
        repo = MarketRepository(db)
        row = repo.get_latest_quote(market, symbol)
        if row:
            return quote_to_dict(row, fallback_source=self._source_name(market))
        adapter = sdk_manager.get_adapter_for_market(market)
        snap = adapter.get_quote(symbol)
        raw_payload = dict(snap.raw_payload or {})
        raw_payload.setdefault("provider", self._source_name(market))
        snap = snap.model_copy(update={"raw_payload": raw_payload})
        repo.insert_snapshot(snap)
        db.commit()
        return quote_to_dict(snap)

    def get_klines(
        self,
        db: Session,
        *,
        market: Market | str,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
        trusted_only: bool = True,
    ) -> list[dict]:
        if isinstance(market, str):
            market = Market(market)
        limit = min(max(limit, 1), 2000)
        adapter = sdk_manager.get_adapter_for_market(market)
        active_source = self._source_name(market)
        repo = MarketRepository(db)
        rows = repo.query_klines(
            market=market,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            limit=limit,
            trusted_only=trusted_only,
            expected_source=active_source,
        )
        if len(rows) >= limit:
            return [kline_to_dict(r) for r in reversed(rows)]

        now = datetime.now(timezone.utc)
        fetch_end = end or now
        if start is not None:
            fetch_start = start
        elif interval in {"1m", "5m"}:
            # 休市后仍需取得最后一个交易时段，不能只请求“当前时间往前 N 分钟”。
            fetch_start = fetch_end - timedelta(days=7)
        else:
            fetch_start = fetch_end - timedelta(days=max(limit * 2, 30))

        bars = stamp_kline_source(
            adapter.get_kline(symbol, interval, fetch_start, fetch_end),
            active_source,
        )
        if bars:
            if len(bars) > limit:
                bars = bars[-limit:]
            repo.upsert_klines(bars)
            db.commit()
            rows = repo.query_klines(
                market=market,
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
                limit=limit,
                trusted_only=trusted_only,
                expected_source=active_source,
            )
        return [kline_to_dict(r) for r in reversed(rows)]

    @staticmethod
    def _source_name(market: Market) -> str:
        adapter = sdk_manager.get_adapter_for_market(market)
        return str(getattr(adapter, "name", adapter.__class__.__name__)).lower()


market_service = MarketService()
