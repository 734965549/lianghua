"""AI 报告指令词过滤与规则模板。"""

from app.services.ai_report_service import AiReportService, sanitize_ai_content


def test_sanitize_forbidden_patterns():
    text = "建议立即买入该标的，或马上卖出止损，不要一键下单。"
    out, hits = sanitize_ai_content(text)
    assert "立即买入" not in out
    assert "马上卖出" not in out
    assert "一键下单" not in out
    assert "建议关注" in out
    assert "立即买入" in hits
    assert "马上卖出" in hits
    assert "一键下单" in hits


def test_rule_based_no_data_has_disclaimer():
    svc = object.__new__(AiReportService)
    md = AiReportService._rule_based_template(svc, {"has_data": False}, [], [])
    assert "无交易数据" in md
    assert "不提供直接下单入口" in md
    for pat in ["立即买入", "立即卖出", "一键下单"]:
        assert pat not in md


def test_rule_based_with_metrics_no_orders_language():
    svc = object.__new__(AiReportService)
    metrics = {
        "has_data": True,
        "range_start": "2026-06-01",
        "range_end": "2026-06-21",
        "total_pnl": "100",
        "win_rate": "0.5",
        "profit_loss_ratio": "1.5",
        "max_drawdown": "10",
        "trade_count": 4,
        "round_trips": 2,
        "fee_total": "5",
        "avg_holding_minutes": "30",
        "risk_reject_count": 1,
        "circuit_breaker_count": 0,
        "consecutive_loss_count": 2,
    }
    md = AiReportService._rule_based_template(svc, metrics, ["标的 X 已实现盈亏 -50"], ["连续亏损达到 3 次以上"])
    assert "总盈亏：100" in md
    assert "仅供复盘参考" in md
    assert "立即买入" not in md
    assert "立即卖出" not in md
