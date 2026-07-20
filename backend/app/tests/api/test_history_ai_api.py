"""历史查询与 AI 报告 API 集成测试。"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models.account import Account
from app.db.models.order import Order
from app.db.models.trade import Trade
from app.db.session import SessionLocal
from app.main import app
from app.schemas.enums import (
    AccountStatus,
    Market,
    OrderSide,
    OrderStatus,
    PriceType,
    SignalAction,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_history():
    db = SessionLocal()
    account = db.query(Account).filter(Account.market == Market.STOCK).first()
    if account is None:
        account = Account(
            account_no=f"TEST_{uuid4().hex[:8]}",
            account_name="test",
            market=Market.STOCK,
            sdk_account_ref="TEST_STOCK",
            status=AccountStatus.ACTIVE,
        )
        db.add(account)
        db.flush()

    cid = f"hist-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    order = Order(
        client_order_id=cid,
        account_id=account.id,
        strategy_id="ma_cross",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        filled_quantity=Decimal("100"),
        status=OrderStatus.FILLED,
        submitted_at=now,
        last_event_at=now,
    )
    db.add(order)
    trade_buy = Trade(
        sdk_trade_id=f"tb-{uuid4().hex[:8]}",
        client_order_id=cid,
        account_id=account.id,
        strategy_id="ma_cross",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price=Decimal("10"),
        quantity=Decimal("100"),
        fee=Decimal("1"),
        trade_time=now - timedelta(hours=1),
    )
    trade_sell_cid = f"hist-sell-{uuid4().hex[:8]}"
    sell_order = Order(
        client_order_id=trade_sell_cid,
        account_id=account.id,
        strategy_id="ma_cross",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.SELL,
        action=SignalAction.CLOSE,
        price_type=PriceType.LIMIT,
        price=Decimal("12"),
        quantity=Decimal("100"),
        filled_quantity=Decimal("100"),
        status=OrderStatus.FILLED,
        submitted_at=now,
        last_event_at=now,
    )
    db.add(sell_order)
    trade_sell = Trade(
        sdk_trade_id=f"ts-{uuid4().hex[:8]}",
        client_order_id=trade_sell_cid,
        account_id=account.id,
        strategy_id="ma_cross",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.SELL,
        price=Decimal("12"),
        quantity=Decimal("100"),
        fee=Decimal("1"),
        trade_time=now,
    )
    db.add(trade_buy)
    db.add(trade_sell)
    db.commit()
    yield {"client_order_id": cid, "sell_client_order_id": trade_sell_cid}
    # 保留数据供人工查看；测试库可定期清理
    db.close()


def test_history_orders_and_trades(client, seeded_history):
    r = client.get("/api/history/orders", params={"symbol": "600000.SH", "page_size": 50})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert any(i["client_order_id"] == seeded_history["client_order_id"] for i in body["data"]["items"])

    r2 = client.get("/api/history/trades", params={"strategy_id": "ma_cross", "page_size": 50})
    assert r2.status_code == 200
    assert r2.json()["success"] is True
    assert r2.json()["data"]["total"] >= 1


def test_history_orders_csv(client, seeded_history):
    r = client.get(
        "/api/history/orders",
        params={"symbol": "600000.SH"},
        headers={"Accept": "text/csv"},
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    text = r.content.decode("utf-8-sig")
    assert "client_order_id" in text
    assert seeded_history["client_order_id"] in text


def test_history_chain(client, seeded_history):
    cid = seeded_history["client_order_id"]
    r = client.get(f"/api/history/orders/{cid}/chain")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["order"]["client_order_id"] == cid
    assert "risk_checks" in data
    assert "trades" in data
    assert "audit_logs" in data


def test_ai_report_generate_list_detail_feedback(client, seeded_history):
    now = datetime.now(timezone.utc)
    payload = {
        "range_start": (now - timedelta(days=1)).isoformat(),
        "range_end": (now + timedelta(hours=1)).isoformat(),
        "strategy_ids": ["ma_cross"],
        "markets": ["stock"],
        "symbols": ["600000.SH"],
    }
    r = client.post("/api/ai/reports", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    report_id = body["data"]["report_id"]
    assert body["data"]["metrics_summary"]["has_data"] is True
    content_check = client.get(f"/api/ai/reports/{report_id}")
    assert content_check.status_code == 200
    detail = content_check.json()["data"]
    assert "立即买入" not in detail["content"]
    assert "不提供直接下单入口" in detail["content"] or "复盘参考" in detail["content"]

    lst = client.get("/api/ai/reports")
    assert lst.status_code == 200
    assert any(i["report_id"] == report_id for i in lst.json()["data"]["items"])

    fb = client.post(f"/api/ai/reports/{report_id}/feedback", json={"useful": True})
    assert fb.status_code == 200
    assert fb.json()["data"]["metadata"].get("feedback") == "useful"


def test_ai_report_invalid_range(client):
    now = datetime.now(timezone.utc)
    r = client.post(
        "/api/ai/reports",
        json={
            "range_start": now.isoformat(),
            "range_end": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "AI_REPORT_INVALID_RANGE"
