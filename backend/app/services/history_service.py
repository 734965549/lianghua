"""历史交易查询与 CSV 导出、交易链路聚合。"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.time import as_utc, to_utc_iso
from app.core.text import repair_display_text
from app.db.models.audit_log import AuditLog
from app.db.models.strategy_signal import StrategySignal
from app.repositories.order_repo import OrderRepository
from app.repositories.risk_repo import RiskRepository
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType
from app.services.order_service import order_to_dict
from app.services.trade_service import trade_to_dict

ORDER_CSV_HEADERS = [
    "client_order_id",
    "sdk_order_id",
    "symbol",
    "market",
    "side",
    "action",
    "price",
    "quantity",
    "filled_quantity",
    "status",
    "created_at",
    "filled_at",
    "strategy_id",
    "fee",
]

TRADE_CSV_HEADERS = [
    "sdk_trade_id",
    "client_order_id",
    "sdk_order_id",
    "symbol",
    "market",
    "side",
    "price",
    "quantity",
    "fee",
    "trade_time",
    "strategy_id",
]


def _historical_data_quality(order, trades: list, signal=None) -> dict:
    issues: list[str] = []
    if str(order.sdk_order_id or "").upper().startswith("MOCK"):
        issues.append("simulated_sdk_record")

    limit_price = Decimal(str(order.price or 0))
    if order.price_type == PriceType.LIMIT and limit_price > 0:
        for trade in trades:
            fill_price = Decimal(str(trade.price))
            crossed_limit = (
                order.side == OrderSide.BUY and fill_price > limit_price
            ) or (
                order.side == OrderSide.SELL and fill_price < limit_price
            )
            if crossed_limit:
                issues.append(
                    f"limit_price_violation:{fill_price} vs {limit_price}"
                )
                break

    if signal is not None and signal.signal_time and order.created_at:
        delta = abs(
            (as_utc(signal.signal_time) - as_utc(order.created_at)).total_seconds()
        )
        if 7.5 * 3600 <= delta <= 8.5 * 3600:
            issues.append("legacy_timezone_offset_8h")

    classification = (
        "historical_test_data"
        if any(
            issue.startswith("limit_price_violation")
            or issue == "legacy_timezone_offset_8h"
            for issue in issues
        )
        else "simulated_data"
        if "simulated_sdk_record" in issues
        else "production_data"
    )
    return {
        "classification": classification,
        "isolated": classification == "historical_test_data",
        "issues": issues,
        "label": {
            "historical_test_data": "历史测试脏数据",
            "simulated_data": "模拟交易数据",
            "production_data": "正常记录",
        }[classification],
    }


class HistoryService:
    def __init__(self, db: Session):
        self.db = db
        self.orders = OrderRepository(db)
        self.trades = TradeRepository(db)
        self.risk = RiskRepository(db)

    def list_orders(
        self,
        *,
        market: Market | None = None,
        symbol: str | None = None,
        status: OrderStatus | None = None,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        offset = (page - 1) * page_size
        rows, total = self.orders.list_orders(
            market=market,
            symbol=symbol,
            status=status,
            strategy_id=strategy_id,
            start=start,
            end=end,
            offset=offset,
            limit=page_size,
        )
        items: list[dict] = []
        for row in rows:
            trades = self.trades.list_by_client_order_id(row.client_order_id)
            quality = _historical_data_quality(row, trades)
            items.append({**order_to_dict(row), "data_quality": quality})
        return items, total

    def list_trades(
        self,
        *,
        market: Market | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        offset = (page - 1) * page_size
        rows, total = self.trades.list_trades(
            market=market,
            symbol=symbol,
            strategy_id=strategy_id,
            start=start,
            end=end,
            offset=offset,
            limit=page_size,
        )
        items: list[dict] = []
        quality_by_order: dict[str, dict] = {}
        for row in rows:
            if row.client_order_id not in quality_by_order:
                order = self.orders.get_by_client_order_id(row.client_order_id)
                quality_by_order[row.client_order_id] = (
                    _historical_data_quality(
                        order,
                        self.trades.list_by_client_order_id(row.client_order_id),
                    )
                    if order is not None
                    else {
                        "classification": "historical_test_data",
                        "isolated": True,
                        "issues": ["orphan_trade"],
                        "label": "历史测试脏数据",
                    }
                )
            items.append(
                {
                    **trade_to_dict(row),
                    "data_quality": quality_by_order[row.client_order_id],
                }
            )
        return items, total

    def orders_csv(
        self,
        *,
        market: Market | None = None,
        symbol: str | None = None,
        status: OrderStatus | None = None,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> str:
        rows = self.orders.list_orders_export(
            market=market,
            symbol=symbol,
            status=status,
            strategy_id=strategy_id,
            start=start,
            end=end,
        )
        # 成交费用按 client_order_id 汇总
        fee_map: dict[str, float] = {}
        for o in rows:
            trades = self.trades.list_by_client_order_id(o.client_order_id)
            fee_map[o.client_order_id] = float(sum(float(t.fee or 0) for t in trades))

        buf = io.StringIO()
        buf.write("\ufeff")  # UTF-8 BOM for Excel
        writer = csv.DictWriter(buf, fieldnames=ORDER_CSV_HEADERS)
        writer.writeheader()
        for o in rows:
            d = order_to_dict(o)
            writer.writerow(
                {
                    "client_order_id": d["client_order_id"],
                    "sdk_order_id": d.get("sdk_order_id") or "",
                    "symbol": d["symbol"],
                    "market": d["market"],
                    "side": d["side"],
                    "action": d["action"],
                    "price": d["price"],
                    "quantity": d["quantity"],
                    "filled_quantity": d["filled_quantity"],
                    "status": d["status"],
                    "created_at": d["created_at"],
                    "filled_at": d.get("last_event_at") or "",
                    "strategy_id": d.get("strategy_id") or "",
                    "fee": fee_map.get(o.client_order_id, 0),
                }
            )
        return buf.getvalue()

    def trades_csv(
        self,
        *,
        market: Market | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> str:
        rows, _ = self.trades.list_trades(
            market=market,
            symbol=symbol,
            strategy_id=strategy_id,
            start=start,
            end=end,
            offset=0,
            limit=10000,
        )
        buf = io.StringIO()
        buf.write("\ufeff")
        writer = csv.DictWriter(buf, fieldnames=TRADE_CSV_HEADERS)
        writer.writeheader()
        for t in rows:
            d = trade_to_dict(t)
            writer.writerow(
                {
                    "sdk_trade_id": d["sdk_trade_id"],
                    "client_order_id": d["client_order_id"],
                    "sdk_order_id": d.get("sdk_order_id") or "",
                    "symbol": d["symbol"],
                    "market": d["market"],
                    "side": d["side"],
                    "price": d["price"],
                    "quantity": d["quantity"],
                    "fee": d["fee"],
                    "trade_time": d["trade_time"],
                    "strategy_id": d.get("strategy_id") or "",
                }
            )
        return buf.getvalue()

    def order_chain(self, client_order_id: str) -> dict | None:
        order = self.orders.get_by_client_order_id(client_order_id)
        if order is None:
            return None

        signal = None
        if order.signal_id:
            signal = self.db.get(StrategySignal, order.signal_id)

        risk_checks = self.risk.list_by_client_order_id(client_order_id)
        trades = self.trades.list_by_client_order_id(client_order_id)
        audits = (
            self.db.query(AuditLog)
            .filter(AuditLog.object_id == client_order_id)
            .order_by(AuditLog.event_time.asc())
            .all()
        )

        data_quality = _historical_data_quality(order, trades, signal)
        return {
            "order": {**order_to_dict(order), "data_quality": data_quality},
            "signal": (
                {
                    "signal_id": str(signal.signal_id),
                    "strategy_id": signal.strategy_id,
                    "symbol": signal.symbol,
                    "market": signal.market.value,
                    "side": signal.side.value,
                    "action": signal.action.value,
                    "price": str(signal.price),
                    "quantity": str(signal.quantity),
                    "reason": repair_display_text(signal.reason),
                    "signal_time": to_utc_iso(signal.signal_time),
                }
                if signal
                else None
            ),
            "risk_checks": [
                {
                    "id": str(c.check_id),
                    "result": c.result.value,
                    "rule_code": c.rule_code,
                    "reason": c.reason,
                    "checked_at": to_utc_iso(c.checked_at),
                }
                for c in risk_checks
            ],
            "trades": [
                {**trade_to_dict(t), "data_quality": data_quality}
                for t in trades
            ],
            "data_quality": data_quality,
            "audit_logs": [
                {
                    "id": a.id,
                    "event_time": to_utc_iso(a.event_time),
                    "action": a.action,
                    "module": a.module,
                    "result": a.result,
                    "reason": a.reason,
                    "correlation_id": a.correlation_id,
                }
                for a in audits
            ],
        }
