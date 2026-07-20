import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.api.response import BizError
from app.api.ws_hub import broadcast_sync
from app.db.session import SessionLocal
from app.repositories.market_repo import MarketRepository
from app.schemas.enums import Market
from app.sdk import manager as sdk_manager
from app.sdk.models import KlineBar, QuoteSnapshot

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


def quote_to_dict(quote: QuoteSnapshot | object) -> dict:
    """将 QuoteSnapshot 或 ORM 行序列化为 API 响应。"""
    if isinstance(quote, QuoteSnapshot):
        return {
            "symbol": quote.symbol,
            "market": quote.market.value if isinstance(quote.market, Market) else quote.market,
            "last_price": _decimal_str(quote.last_price),
            "change_rate": _decimal_str(quote.change_rate),
            "volume": _decimal_str(quote.volume),
            "bid_price": _decimal_str(quote.bid_price),
            "ask_price": _decimal_str(quote.ask_price),
            "quote_time": quote.quote_time.isoformat(),
        }
    return {
        "symbol": quote.symbol,
        "market": quote.market.value if isinstance(quote.market, Market) else quote.market,
        "last_price": _decimal_str(quote.last_price),
        "change_rate": _decimal_str(quote.change_rate),
        "volume": _decimal_str(quote.volume),
        "bid_price": _decimal_str(quote.bid_price),
        "ask_price": _decimal_str(quote.ask_price),
        "quote_time": quote.quote_time.isoformat(),
    }


def kline_to_dict(bar: KlineBar | object) -> dict:
    if isinstance(bar, KlineBar):
        return {
            "symbol": bar.symbol,
            "market": bar.market.value if isinstance(bar.market, Market) else bar.market,
            "interval": bar.interval,
            "bar_time": bar.bar_time.isoformat(),
            "open": _decimal_str(bar.open),
            "high": _decimal_str(bar.high),
            "low": _decimal_str(bar.low),
            "close": _decimal_str(bar.close),
            "volume": _decimal_str(bar.volume),
        }
    return {
        "symbol": bar.symbol,
        "market": bar.market.value if isinstance(bar.market, Market) else bar.market,
        "interval": bar.interval,
        "bar_time": bar.bar_time.isoformat(),
        "open": _decimal_str(bar.open),
        "high": _decimal_str(bar.high),
        "low": _decimal_str(bar.low),
        "close": _decimal_str(bar.close),
        "volume": _decimal_str(bar.volume),
    }


class MarketService:
    def __init__(self):
        self._subscribed: dict[Market, set[str]] = {
            Market.STOCK: set(),
            Market.FUTURES: set(),
        }
        self._started = False

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

        for adapter in (sdk_manager.get_stock_adapter(), sdk_manager.get_futures_adapter()):
            adapter.on_order_update(order_service.on_order_update)
            adapter.on_trade_update(trade_service.on_trade_update)
        for market, symbols in DEFAULT_SUBSCRIPTIONS.items():
            self.subscribe(symbols, market)
        self._started = True
        logger.info("MarketService 已启动，默认订阅 %s", DEFAULT_SUBSCRIPTIONS)

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
        self._started = False

    def _handle_quote(self, quote: QuoteSnapshot) -> None:
        db = SessionLocal()
        try:
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

    def get_subscribed(self) -> list[tuple[Market, str]]:
        result: list[tuple[Market, str]] = []
        for mkt, symbols in self._subscribed.items():
            for sym in symbols:
                result.append((mkt, sym))
        return result

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
        return [quote_to_dict(r) for r in rows]

    def get_quote(self, db: Session, market: Market | str, symbol: str) -> dict:
        if isinstance(market, str):
            market = Market(market)
        repo = MarketRepository(db)
        row = repo.get_latest_quote(market, symbol)
        if row:
            return quote_to_dict(row)
        adapter = sdk_manager.get_adapter_for_market(market)
        snap = adapter.get_quote(symbol)
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
    ) -> list[dict]:
        if isinstance(market, str):
            market = Market(market)
        limit = min(max(limit, 1), 2000)
        repo = MarketRepository(db)
        rows = repo.query_klines(
            market=market,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            limit=limit,
        )
        if len(rows) >= limit:
            return [kline_to_dict(r) for r in reversed(rows)]

        now = datetime.now(timezone.utc)
        fetch_end = end or now
        step_map = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "1d": timedelta(days=1),
        }
        step = step_map.get(interval, timedelta(minutes=1))
        fetch_start = start or (fetch_end - step * limit)

        adapter = sdk_manager.get_adapter_for_market(market)
        bars = adapter.get_kline(symbol, interval, fetch_start, fetch_end)
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
            )
        return [kline_to_dict(r) for r in reversed(rows)]


market_service = MarketService()
