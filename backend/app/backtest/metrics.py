import math
from datetime import datetime
from decimal import Decimal
from statistics import mean, pstdev

from app.backtest.account import SimulationAccount
from app.backtest.models import BacktestMetrics, EquityPoint


def _to_float(value: Decimal) -> float:
    return float(value)


def _safe(value: float) -> Decimal:
    if math.isnan(value) or math.isinf(value):
        return Decimal("0")
    return Decimal(str(value))


class BacktestMetricsCalculator:
    """基于账户快照与权益曲线计算绩效指标。"""

    def __init__(self, initial_cash: Decimal, account: SimulationAccount, equity_curve: list[EquityPoint]):
        self.initial_cash = initial_cash
        self.account = account
        self.equity_curve = equity_curve

    def calculate(self) -> BacktestMetrics:
        if not self.equity_curve:
            final_equity = self.initial_cash
        else:
            final_equity = self.equity_curve[-1].equity

        total_return = (final_equity - self.initial_cash) / self.initial_cash
        total_return_pct = total_return * Decimal("100")

        annualized_return_pct = self._annualized_return(total_return)
        max_drawdown_pct = self._max_drawdown()
        sharpe_ratio = self._sharpe()

        return BacktestMetrics(
            total_return_pct=_safe(_to_float(total_return_pct)),
            annualized_return_pct=_safe(_to_float(annualized_return_pct)),
            sharpe_ratio=_safe(_to_float(sharpe_ratio)),
            max_drawdown_pct=_safe(_to_float(max_drawdown_pct)),
            win_rate_pct=Decimal("0"),
            profit_factor=Decimal("0"),
            total_trades=0,
        )

    def _annualized_return(self, total_return: Decimal) -> Decimal:
        if len(self.equity_curve) < 2:
            return Decimal("0")
        start = self.equity_curve[0].time
        end = self.equity_curve[-1].time
        days = (end - start).total_seconds() / 86400
        if days <= 0:
            return Decimal("0")
        # 年化 = (1 + total_return) ^ (365 / days) - 1
        try:
            annualized = (Decimal("1") + total_return) ** (Decimal("365") / Decimal(str(days))) - Decimal("1")
            return annualized * Decimal("100")
        except Exception:
            return Decimal("0")

    def _max_drawdown(self) -> Decimal:
        peak = Decimal("0")
        max_dd = Decimal("0")
        for point in self.equity_curve:
            equity = point.equity
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd
        return max_dd * Decimal("100")

    def _sharpe(self) -> Decimal:
        if len(self.equity_curve) < 2:
            return Decimal("0")
        returns: list[Decimal] = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i - 1].equity
            curr = self.equity_curve[i].equity
            if prev > 0:
                returns.append((curr - prev) / prev)
        if not returns:
            return Decimal("0")
        returns_f = [_to_float(r) for r in returns]
        avg = mean(returns_f)
        std = pstdev(returns_f)
        if std == 0:
            return Decimal("0")
        # 假设每日采样，年化夏普 = (mean / std) * sqrt(252)
        sharpe = (avg / std) * math.sqrt(252)
        return Decimal(str(sharpe))


def calculate_trade_metrics(trades: list) -> BacktestMetrics:
    """基于成交记录补充胜率、盈亏比、总交易次数。"""
    total = len(trades)
    if total == 0:
        return BacktestMetrics(
            total_return_pct=Decimal("0"),
            annualized_return_pct=Decimal("0"),
            sharpe_ratio=Decimal("0"),
            max_drawdown_pct=Decimal("0"),
            win_rate_pct=Decimal("0"),
            profit_factor=Decimal("0"),
            total_trades=0,
        )
    profits = []
    losses = []
    for t in trades:
        # 简化：买入为负现金流，卖出为正现金流，按成交金额-成本计算单笔盈亏
        amount = t.quantity * t.price
        cost = amount + t.commission + t.tax
        if t.side.value == "buy":
            profits.append(-_to_float(cost))
        else:
            profits.append(_to_float(amount - t.commission - t.tax))
    wins = [p for p in profits if p > 0]
    loss_sum = sum(p for p in profits if p < 0)
    win_rate = len(wins) / total * 100 if total else 0
    profit_factor = abs(sum(wins) / loss_sum) if loss_sum != 0 else Decimal("0")
    return BacktestMetrics(
        total_return_pct=Decimal("0"),
        annualized_return_pct=Decimal("0"),
        sharpe_ratio=Decimal("0"),
        max_drawdown_pct=Decimal("0"),
        win_rate_pct=_safe(win_rate),
        profit_factor=_safe(profit_factor),
        total_trades=total,
    )
