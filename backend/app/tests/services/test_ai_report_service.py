"""AI 报告指令词过滤与规则模板。"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

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
    # 否定前缀须整段替换，避免「不要立即买入」→「不要建议关注」
    negated, neg_hits = sanitize_ai_content("不要立即买入该标的")
    assert "立即买入" not in negated
    assert "不要建议关注" not in negated
    assert negated == "建议关注该标的"
    assert "立即买入" in neg_hits


def test_rule_based_no_data_has_disclaimer():
    svc = object.__new__(AiReportService)
    md = AiReportService._rule_based_template(
        svc,
        {"has_data": False, "range_start": "a", "range_end": "b"},
        [],
        [],
        {"generated_at": "2026-07-20T12:00:00+00:00", "scope": {"strategy_ids": ["ma_cross"]}},
    )
    assert "无交易数据" in md
    assert "生成时间" in md
    assert "ma_cross" in md
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
        "trade_frequency": "2.00",
        "round_trips": 2,
        "fee_total": "5",
        "avg_holding_minutes": "30",
        "risk_reject_count": 1,
        "circuit_breaker_count": 0,
        "consecutive_loss_count": 2,
        "strategy_ranking": [
            {"strategy_id": "ma_cross", "total_pnl": "100", "trade_count": 4, "win_rate": "0.5"}
        ],
    }
    md = AiReportService._rule_based_template(
        svc,
        metrics,
        ["标的 X 已实现盈亏 -50"],
        ["连续亏损达到 3 次以上"],
        {"generated_at": "2026-07-20T12:00:00+00:00", "scope": {"markets": ["stock"]}},
    )
    assert "总盈亏：100" in md
    assert "生成时间" in md
    assert "过滤条件" in md
    assert "策略表现排名" in md
    assert "ma_cross" in md
    assert "交易频率" in md
    assert "仅供复盘参考" in md
    assert "立即买入" not in md
    assert "立即卖出" not in md


def test_rule_based_empty_ranking_and_symbols_filter():
    svc = object.__new__(AiReportService)
    metrics = {
        "has_data": True,
        "range_start": "a",
        "range_end": "b",
        "total_pnl": "0",
        "win_rate": "0",
        "profit_loss_ratio": "0",
        "max_drawdown": "0",
        "trade_count": 0,
        "trade_frequency": "0",
        "round_trips": 0,
        "fee_total": "0",
        "avg_holding_minutes": "0",
        "risk_reject_count": 0,
        "circuit_breaker_count": 0,
        "consecutive_loss_count": 0,
        "strategy_ranking": [],
    }
    md = AiReportService._rule_based_template(
        svc,
        metrics,
        [],
        [],
        {"generated_at": "t", "scope": {"symbols": ["600000.SH"]}},
    )
    assert "暂无策略维度数据" in md
    assert "600000.SH" in md


def test_loss_attribution_and_abnormal():
    svc = object.__new__(AiReportService)
    trades = [
        {"symbol": "A", "side": "buy", "quantity": "100", "price": "10"},
        {"symbol": "A", "side": "sell", "quantity": "60", "price": "9"},
        {"symbol": "A", "side": "sell", "quantity": "40", "price": "8"},
    ]
    losses = AiReportService._loss_attribution(svc, trades)
    assert losses
    assert "标的 A" in losses[0]

    assert AiReportService._loss_attribution(svc, []) == []

    abs_patterns = AiReportService._detect_abnormal(
        svc,
        {
            "consecutive_loss_count": 3,
            "trade_count": 10,
            "risk_reject_count": 5,
            "circuit_breaker_count": 1,
        },
    )
    assert any("连续亏损" in x for x in abs_patterns)
    assert any("风控拒绝" in x for x in abs_patterns)
    assert any("熔断" in x for x in abs_patterns)


def test_build_user_prompt():
    svc = object.__new__(AiReportService)
    text = AiReportService._build_user_prompt(svc, {"a": 1}, ["loss"], ["ab"])
    assert "请基于以下数据" in text
    assert "loss" in text


def test_call_ai_success_and_filter():
    svc = object.__new__(AiReportService)
    svc.model_name = "test-model"
    svc.audit = MagicMock()
    msg = SimpleNamespace(content="分析完成，建议立即买入观察")
    choice = SimpleNamespace(message=msg)
    resp = SimpleNamespace(choices=[choice])
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    svc.ai_client = client

    out = AiReportService._call_ai(svc, {"has_data": True}, [], [], None)
    assert "立即买入" not in out
    assert "建议关注" in out
    assert svc.audit.log.called


def test_call_ai_fallback_on_error():
    svc = object.__new__(AiReportService)
    svc.model_name = "test-model"
    svc.audit = MagicMock()
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("api down")
    svc.ai_client = client

    out = AiReportService._call_ai(
        svc,
        {
            "has_data": False,
            "range_start": "a",
            "range_end": "b",
        },
        [],
        [],
        {"generated_at": "t", "scope": {}},
    )
    assert "无交易数据" in out
    assert svc.audit.log.called


@pytest.mark.integration
def test_generate_with_ai_client_and_get_feedback(db, monkeypatch):
    svc = AiReportService(db, correlation_id="ai_cov")
    fake_client = MagicMock()
    msg = SimpleNamespace(content="复盘摘要，无指令")
    fake_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=msg)]
    )
    svc.ai_client = fake_client
    svc.model_name = "mock-ai"

    monkeypatch.setattr(
        svc.metrics,
        "compute",
        lambda **kw: {
            "has_data": True,
            "range_start": "2026-01-01",
            "range_end": "2026-01-02",
            "total_pnl": "1",
            "win_rate": "0.5",
            "profit_loss_ratio": "1",
            "max_drawdown": "0",
            "trade_count": 1,
            "trade_frequency": "1",
            "round_trips": 1,
            "fee_total": "0",
            "avg_holding_minutes": "1",
            "risk_reject_count": 0,
            "circuit_breaker_count": 0,
            "consecutive_loss_count": 0,
            "strategy_ranking": [],
        },
    )
    monkeypatch.setattr(svc.trade_repo, "query_for_metrics", lambda **kw: [])

    now = datetime.now(timezone.utc)
    result = svc.generate(range_start=now, range_end=now, symbols=["600000.SH"])
    db.commit()
    assert result["model_name"] == "mock-ai"
    rid = result["report_id"]

    detail = svc.get_report(rid)
    assert detail is not None
    assert detail["content"]
    assert svc.get_report(uuid4()) is None

    fb = svc.mark_feedback(rid, True)
    assert fb is not None
    assert fb["metadata"].get("feedback") == "useful"
    assert svc.mark_feedback(uuid4(), False) is None

    rows, total = svc.list_reports(page=1, page_size=10)
    assert total >= 1
    assert any(r["report_id"] == rid for r in rows)
