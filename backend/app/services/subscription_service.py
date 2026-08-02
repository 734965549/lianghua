import logging
from collections import defaultdict

from app.schemas.enums import Market
from app.services.market_service import market_service

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """按需行情订阅管理器：按 subscriber 维度的引用计数。"""

    def __init__(self):
        # (market, symbol) -> subscriber_id set
        self._subscribers: dict[tuple[Market, str], set[str]] = defaultdict(set)
        # subscriber_id -> set[(market, symbol)]
        self._subscriptions: dict[str, set[tuple[Market, str]]] = defaultdict(set)

    def subscribe(self, subscriber_id: str, market: Market, symbols: list[str]) -> list[str]:
        """为指定订阅者增加订阅，首次引用时通知 market_service。"""
        added: list[str] = []
        for symbol in symbols:
            key = (market, symbol)
            first = len(self._subscribers[key]) == 0
            if subscriber_id not in self._subscribers[key]:
                self._subscribers[key].add(subscriber_id)
                self._subscriptions[subscriber_id].add(key)
            if first:
                try:
                    market_service.subscribe([symbol], market)
                    added.append(symbol)
                except Exception:
                    logger.exception("订阅行情失败: %s %s", market.value, symbol)
        return added

    def unsubscribe(self, subscriber_id: str, market: Market, symbols: list[str]) -> list[str]:
        """为指定订阅者取消订阅，引用归零时通知 market_service。"""
        removed: list[str] = []
        for symbol in symbols:
            key = (market, symbol)
            if subscriber_id in self._subscribers[key]:
                self._subscribers[key].discard(subscriber_id)
                self._subscriptions[subscriber_id].discard(key)
            if len(self._subscribers[key]) == 0:
                try:
                    market_service.unsubscribe([symbol], market)
                    removed.append(symbol)
                except Exception:
                    logger.exception("取消订阅行情失败: %s %s", market.value, symbol)
                self._subscribers.pop(key, None)
        return removed

    def unsubscribe_all(self, subscriber_id: str) -> list[tuple[Market, str]]:
        """取消某订阅者的全部订阅。"""
        keys = list(self._subscriptions.get(subscriber_id, []))
        for market, symbol in keys:
            self.unsubscribe(subscriber_id, market, [symbol])
        self._subscriptions.pop(subscriber_id, None)
        return keys

    def get_subscribed(self) -> list[tuple[Market, str]]:
        return list(self._subscribers.keys())


subscription_manager = SubscriptionManager()
