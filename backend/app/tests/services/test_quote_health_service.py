from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.models.system_event import SystemEvent
from app.repositories.market_repo import MarketRepository
from app.repositories.system_event_repo import SystemEventRepository
from app.schemas.enums import Market, Severity, SystemStatus
from app.sdk import manager as sdk_manager
from app.sdk.models import QuoteSnapshot
from app.services.market_service import market_service
from app.services.quote_health_service import assess_quote_health
from app.services.system_service import SystemStateService
from app.workers.sync_jobs import check_quote_stale


@pytest.fixture(autouse=True)
def _market_runtime():
    sdk_manager.reset_adapters()
    market_service._started = False
    market_service._subscribed = {
        Market.STOCK: set(),
        Market.FUTURES: set(),
    }
    yield
    market_service._started = False
    market_service._subscribed = {
        Market.STOCK: set(),
        Market.FUTURES: set(),
    }
    sdk_manager.reset_adapters()


def _start_stock_subscription():
    sdk_manager.ensure_connected()
    market_service._started = True
    market_service._subscribed[Market.STOCK].add("600000.SH")


def _insert_quote(db, quote_time: datetime):
    MarketRepository(db).insert_snapshot(
        QuoteSnapshot(
            symbol="600000.SH",
            market=Market.STOCK,
            last_price=Decimal("10"),
            change_rate=Decimal("0"),
            volume=Decimal("100"),
            quote_time=quote_time,
        )
    )
    db.commit()


def test_normal_market_close_never_requires_breaker(db):
    _start_stock_subscription()
    saturday = datetime(2026, 7, 25, 2, 0, tzinfo=timezone.utc)

    health = assess_quote_health(db, now=saturday, timeout_seconds=10)

    assert health["state"] == "market_closed"
    assert health["breaker_required"] is False
    assert health["items"][0]["state"] == "market_closed"


def test_explicit_target_is_classified_without_runtime_subscription(db):
    saturday = datetime(2026, 7, 25, 2, 0, tzinfo=timezone.utc)

    health = assess_quote_health(
        db,
        targets=[(Market.STOCK, "600000.SH")],
        now=saturday,
        timeout_seconds=10,
    )

    assert health["state"] == "market_closed"
    assert health["breaker_required"] is False
    assert health["items"] == [
        {
            "market": "stock",
            "symbol": "600000.SH",
            "state": "market_closed",
            "blocking": False,
        }
    ]


def test_open_market_distinguishes_subscription_and_feed_stale(db):
    _start_stock_subscription()
    monday = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)

    missing = assess_quote_health(db, now=monday, timeout_seconds=10)
    _insert_quote(db, monday - timedelta(seconds=11))
    stale = assess_quote_health(db, now=monday, timeout_seconds=10)

    assert missing["state"] == "subscription_disconnected"
    assert missing["breaker_required"] is True
    assert stale["state"] == "feed_stale"
    assert stale["breaker_required"] is True


def test_open_market_distinguishes_source_disconnect(db):
    _start_stock_subscription()
    sdk_manager.get_stock_adapter().inject_disconnect()
    monday = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)

    health = assess_quote_health(db, now=monday, timeout_seconds=10)

    assert health["state"] == "source_disconnected"
    assert health["breaker_required"] is True


def test_stale_check_resolves_old_alert_during_normal_close(
    db, reset_system_state
):
    _start_stock_subscription()
    SystemEventRepository(db).add(
        module="market",
        event_code="quote_stale",
        message="old",
        severity=Severity.WARNING,
    )
    db.commit()

    health = check_quote_stale(
        db, now=datetime(2026, 7, 25, 2, 0, tzinfo=timezone.utc)
    )

    event = (
        db.query(SystemEvent)
        .filter(SystemEvent.event_code == "quote_stale")
        .one()
    )
    assert health["state"] == "market_closed"
    assert event.resolved is True
    assert SystemStateService(db).get_status()["status"] == SystemStatus.READY.value


def test_stale_check_degrades_only_during_open_market(
    db, reset_system_state
):
    _start_stock_subscription()
    monday = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)
    _insert_quote(db, monday - timedelta(seconds=11))

    health = check_quote_stale(db, now=monday)

    assert health["state"] == "feed_stale"
    assert SystemStateService(db).get_status()["status"] == SystemStatus.DEGRADED.value
    event = (
        db.query(SystemEvent)
        .filter(SystemEvent.event_code == "quote_stale")
        .one()
    )
    assert event.payload["state"] == "feed_stale"
