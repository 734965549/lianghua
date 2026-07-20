"""指标计算确定性单测：固定成交数据断言手工计算值。"""

from datetime import datetime, timezone
from decimal import Decimal

from app.services.metrics_service import MetricsService


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_fifo_pnl_win_rate_and_fees():
    """
    手工：
    - 买 100@10，卖 100@12 → 毛利 200
    - 买 50@20，卖 50@18 → 毛亏 -100
    - 手续费合计 5
    - 净盈亏 95；胜率 1/2；盈亏比 (200)/(100)=2；连续亏损 1
    """
    trades = [
        {
            "symbol": "600000.SH",
            "side": "buy",
            "price": "10",
            "quantity": "100",
            "fee": "2",
            "trade_time": _dt("2026-06-01T10:00:00"),
        },
        {
            "symbol": "600000.SH",
            "side": "sell",
            "price": "12",
            "quantity": "100",
            "fee": "1",
            "trade_time": _dt("2026-06-01T11:00:00"),
        },
        {
            "symbol": "600000.SH",
            "side": "buy",
            "price": "20",
            "quantity": "50",
            "fee": "1",
            "trade_time": _dt("2026-06-02T10:00:00"),
        },
        {
            "symbol": "600000.SH",
            "side": "sell",
            "price": "18",
            "quantity": "50",
            "fee": "1",
            "trade_time": _dt("2026-06-02T11:00:00"),
        },
    ]
    # MetricsService.__init__ 需要 db，这里只测纯函数入口
    svc = object.__new__(MetricsService)
    result = MetricsService.compute_from_trades(svc, trades)

    assert result["has_data"] is True
    assert result["trade_count"] == 4
    assert result["round_trips"] == 2
    assert Decimal(result["fee_total"]) == Decimal("5")
    assert Decimal(result["total_pnl"]) == Decimal("95")  # 200 - 100 - 5
    assert Decimal(result["win_rate"]) == Decimal("0.5")
    assert Decimal(result["profit_loss_ratio"]) == Decimal("2")
    assert result["consecutive_loss_count"] == 1
    assert result["daily_pnl"]["2026-06-01"] == "200"
    assert result["daily_pnl"]["2026-06-02"] == "-100"


def test_empty_trades():
    svc = object.__new__(MetricsService)
    result = MetricsService.compute_from_trades(svc, [])
    assert result["has_data"] is False
    assert result["trade_count"] == 0


def test_max_drawdown():
    svc = object.__new__(MetricsService)
    curve = [Decimal("100"), Decimal("120"), Decimal("90"), Decimal("95")]
    assert MetricsService._max_drawdown(svc, curve) == Decimal("30")


def test_partial_fifo_match():
    """买 100@10，卖 40@15 → 仅一笔回合 pnl=200。"""
    trades = [
        {
            "symbol": "A",
            "side": "buy",
            "price": "10",
            "quantity": "100",
            "fee": "0",
            "trade_time": _dt("2026-06-01T10:00:00"),
        },
        {
            "symbol": "A",
            "side": "sell",
            "price": "15",
            "quantity": "40",
            "fee": "0",
            "trade_time": _dt("2026-06-01T11:00:00"),
        },
    ]
    svc = object.__new__(MetricsService)
    result = MetricsService.compute_from_trades(svc, trades)
    assert Decimal(result["total_pnl"]) == Decimal("200")
    assert result["round_trips"] == 1
