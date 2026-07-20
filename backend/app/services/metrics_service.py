"""确定性指标计算，不依赖 AI 模型。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.asset_repo import AssetRepository
from app.repositories.risk_repo import RiskRepository
from app.repositories.trade_repo import TradeRepository


class MetricsService:
    def __init__(self, db: Session):
        self.trade_repo = TradeRepository(db)
        self.asset_repo = AssetRepository(db)
        self.risk_repo = RiskRepository(db)

    def compute(
        self,
        *,
        range_start: datetime,
        range_end: datetime,
        strategy_ids: list[str] | None = None,
        markets: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> dict:
        trades = self.trade_repo.query_for_metrics(
            range_start=range_start,
            range_end=range_end,
            strategy_ids=strategy_ids,
            markets=markets,
            symbols=symbols,
        )
        result = self.compute_from_trades(trades)
        result["range_start"] = range_start.isoformat()
        result["range_end"] = range_end.isoformat()

        asset_curve = self.asset_repo.curve(range_start, range_end)
        max_drawdown = self._max_drawdown([Decimal(str(a["total_asset"])) for a in asset_curve])
        result["max_drawdown"] = str(max_drawdown)

        result["risk_reject_count"] = self.risk_repo.count_rejected(range_start, range_end)
        result["circuit_breaker_count"] = self.risk_repo.count_breaker(range_start, range_end)
        return result

    def compute_from_trades(self, trades: list[dict]) -> dict:
        """纯函数入口，便于单测用固定成交数据断言。"""
        if not trades:
            return {
                "has_data": False,
                "message": "所选范围内无成交数据",
                "total_pnl": "0",
                "daily_pnl": {},
                "win_rate": "0",
                "profit_loss_ratio": "0",
                "max_drawdown": "0",
                "trade_count": 0,
                "fee_total": "0",
                "slippage_estimate": "0",
                "risk_reject_count": 0,
                "circuit_breaker_count": 0,
                "consecutive_loss_count": 0,
                "avg_holding_minutes": "0",
                "round_trips": 0,
            }

        pnls = self._fifo_round_trip_pnls(trades)
        total_pnl = sum(pnls, Decimal("0"))
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = Decimal(len(wins)) / Decimal(len(pnls)) if pnls else Decimal("0")
        if wins and losses:
            avg_win = sum(wins, Decimal("0")) / Decimal(len(wins))
            avg_loss = abs(sum(losses, Decimal("0")) / Decimal(len(losses)))
            profit_loss_ratio = avg_win / avg_loss if avg_loss else Decimal("0")
        else:
            profit_loss_ratio = Decimal("0")

        fee_total = sum((Decimal(str(t.get("fee") or 0)) for t in trades), Decimal("0"))
        # 已实现盈亏扣除手续费
        total_pnl = total_pnl - fee_total

        return {
            "has_data": True,
            "total_pnl": str(total_pnl),
            "daily_pnl": self._group_by_day(pnls, trades),
            "win_rate": str(win_rate),
            "profit_loss_ratio": str(profit_loss_ratio),
            "max_drawdown": "0",
            "trade_count": len(trades),
            "fee_total": str(fee_total),
            "slippage_estimate": str(self._estimate_slippage(trades)),
            "risk_reject_count": 0,
            "circuit_breaker_count": 0,
            "consecutive_loss_count": self._max_consecutive_loss(pnls),
            "avg_holding_minutes": str(self._avg_holding_minutes(trades)),
            "round_trips": len(pnls),
        }

    def _fifo_round_trip_pnls(self, trades: list[dict]) -> list[Decimal]:
        """按标的 FIFO 配对买/卖，计算已实现盈亏（未扣费）。"""
        lots: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)  # symbol -> [(qty, price)]
        pnls: list[Decimal] = []

        for t in trades:
            symbol = str(t["symbol"])
            side = str(t["side"])
            qty = Decimal(str(t["quantity"]))
            price = Decimal(str(t["price"]))
            if qty <= 0:
                continue

            if side == "buy":
                lots[symbol].append((qty, price))
                continue

            # sell：消耗买仓
            remain = qty
            while remain > 0 and lots[symbol]:
                lot_qty, lot_price = lots[symbol][0]
                matched = min(remain, lot_qty)
                pnls.append((price - lot_price) * matched)
                lot_qty -= matched
                remain -= matched
                if lot_qty <= 0:
                    lots[symbol].pop(0)
                else:
                    lots[symbol][0] = (lot_qty, lot_price)
            # 无开仓的卖出暂不计入（避免虚构盈亏）
        return pnls

    def _max_drawdown(self, curve: list[Decimal]) -> Decimal:
        if not curve:
            return Decimal("0")
        peak = curve[0]
        max_dd = Decimal("0")
        for v in curve:
            if v > peak:
                peak = v
            dd = peak - v
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _max_consecutive_loss(self, pnls: list[Decimal]) -> int:
        max_run = run = 0
        for p in pnls:
            if p < 0:
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        return max_run

    def _estimate_slippage(self, trades: list[dict]) -> Decimal:
        """无信号价时返回 0；有 signal_price 字段则累加 |成交价-信号价|*数量。"""
        total = Decimal("0")
        for t in trades:
            if t.get("signal_price") is None:
                continue
            slip = abs(Decimal(str(t["price"])) - Decimal(str(t["signal_price"])))
            total += slip * Decimal(str(t["quantity"]))
        return total

    def _group_by_day(self, pnls: list[Decimal], trades: list[dict]) -> dict:
        """按卖出成交日聚合已实现盈亏（简化：把每笔 round-trip pnl 挂到对应卖出日）。"""
        # 重新走一遍 FIFO，同时记录卖出日
        lots: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        daily: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        for t in trades:
            symbol = str(t["symbol"])
            side = str(t["side"])
            qty = Decimal(str(t["quantity"]))
            price = Decimal(str(t["price"]))
            tt = t.get("trade_time")
            day = tt.date().isoformat() if isinstance(tt, datetime) else str(tt)[:10]
            if qty <= 0:
                continue
            if side == "buy":
                lots[symbol].append((qty, price))
                continue
            remain = qty
            while remain > 0 and lots[symbol]:
                lot_qty, lot_price = lots[symbol][0]
                matched = min(remain, lot_qty)
                daily[day] += (price - lot_price) * matched
                lot_qty -= matched
                remain -= matched
                if lot_qty <= 0:
                    lots[symbol].pop(0)
                else:
                    lots[symbol][0] = (lot_qty, lot_price)
        return {k: str(v) for k, v in sorted(daily.items())}

    def _avg_holding_minutes(self, trades: list[dict]) -> Decimal:
        lots: dict[str, list[tuple[Decimal, datetime]]] = defaultdict(list)
        holds: list[Decimal] = []

        for t in trades:
            symbol = str(t["symbol"])
            side = str(t["side"])
            qty = Decimal(str(t["quantity"]))
            tt = t.get("trade_time")
            if not isinstance(tt, datetime) or qty <= 0:
                continue
            if side == "buy":
                lots[symbol].append((qty, tt))
                continue
            remain = qty
            while remain > 0 and lots[symbol]:
                lot_qty, open_time = lots[symbol][0]
                matched = min(remain, lot_qty)
                minutes = Decimal(str((tt - open_time).total_seconds() / 60.0))
                holds.append(minutes)
                lot_qty -= matched
                remain -= matched
                if lot_qty <= 0:
                    lots[symbol].pop(0)
                else:
                    lots[symbol][0] = (lot_qty, open_time)
        if not holds:
            return Decimal("0")
        return sum(holds, Decimal("0")) / Decimal(len(holds))
