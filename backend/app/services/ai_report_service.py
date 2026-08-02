import logging
import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.ai_report_repo import AiReportRepository
from app.repositories.trade_repo import TradeRepository
from app.services.ai_client import get_ai_client, resolve_model_name
from app.services.audit_service import AuditService
from app.services.metrics_service import MetricsService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是量化交易复盘助手。请严格遵守：
1. 只能基于输入的指标和交易数据分析，不得编造不存在的交易、收益或风险事件。
2. 不得输出"立即买入/卖出/加仓/减仓"等直接交易指令。
3. 所有建议必须表述为复盘参考，决策由用户自行判断。
4. 当数据不足时，必须明确说明数据不足，不要强行给出结论。
5. 报告语言为中文。
"""

FORBIDDEN_PATTERNS = [
    "立即买入",
    "立即卖出",
    "马上买入",
    "马上卖出",
    "一键下单",
    "立即下单",
    "立刻买入",
    "立刻卖出",
]

# 可选否定/建议前缀一并替换，避免「不要立即买入」→「不要建议关注」
_SANITIZE_PREFIX = r"(?:不要|别|禁止|切勿|请勿|建议)?"
_SANITIZE_REPLACEMENT = "建议关注"


def sanitize_ai_content(content: str) -> tuple[str, list[str]]:
    """扫描并替换指令性词汇，返回 (正文, 命中列表)。"""
    hits: list[str] = []
    out = content
    for pat in sorted(FORBIDDEN_PATTERNS, key=len, reverse=True):
        pattern = re.compile(_SANITIZE_PREFIX + re.escape(pat))
        if pattern.search(out):
            hits.append(pat)
            out = pattern.sub(_SANITIZE_REPLACEMENT, out)
    return out, hits


class AiReportService:
    def __init__(self, db: Session, *, correlation_id: str = ""):
        self.db = db
        self.audit = AuditService(db, correlation_id=correlation_id)
        self.metrics = MetricsService(db)
        self.repo = AiReportRepository(db)
        self.trade_repo = TradeRepository(db)
        self.ai_config = SettingsService(db, correlation_id=correlation_id).get_ai_runtime_config()
        self.ai_client = get_ai_client(
            self.ai_config, timeout=settings.ai_generation_timeout
        )
        self.model_name = resolve_model_name(self.ai_config)

    def generate(
        self,
        *,
        range_start: datetime,
        range_end: datetime,
        strategy_ids: list[str] | None = None,
        markets: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> dict:
        metrics = self.metrics.compute(
            range_start=range_start,
            range_end=range_end,
            strategy_ids=strategy_ids,
            markets=markets,
            symbols=symbols,
        )
        trades = self.trade_repo.query_for_metrics(
            range_start=range_start,
            range_end=range_end,
            strategy_ids=strategy_ids,
            markets=markets,
            symbols=symbols,
        )
        loss_attribution = self._loss_attribution(trades)
        abnormal_patterns = self._detect_abnormal(metrics)

        scope = {
            "strategy_ids": strategy_ids or [],
            "markets": markets or [],
            "symbols": symbols or [],
        }
        now = datetime.now(timezone.utc)
        template_ctx = {
            "generated_at": now.isoformat(),
            "scope": scope,
        }

        if self.ai_client and metrics.get("has_data"):
            content = self._call_ai(metrics, loss_attribution, abnormal_patterns, template_ctx)
        else:
            content = self._rule_based_template(
                metrics, loss_attribution, abnormal_patterns, template_ctx
            )

        report = self.repo.add_report(
            range_start=range_start,
            range_end=range_end,
            scope=scope,
            metrics=metrics,
            content=content,
            content_format="markdown",
            model_name=self.model_name if self.ai_client else "rule_based",
            generated_at=now,
        )
        self.audit.log(
            action="ai_report_generate",
            module="ai",
            object_type="ai_report",
            object_id=str(report.report_id),
            result="success",
            request_summary={"range": [range_start.isoformat(), range_end.isoformat()], "scope": scope},
        )
        return {
            "report_id": str(report.report_id),
            "generated_at": report.generated_at.isoformat(),
            "metrics_summary": metrics,
            "model_name": report.model_name,
        }

    def list_reports(self, *, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        offset = (page - 1) * page_size
        rows, total = self.repo.list_reports(offset=offset, limit=page_size)
        return [self._summary(r) for r in rows], total

    def get_report(self, report_id) -> dict | None:
        from uuid import UUID

        rid = report_id if isinstance(report_id, UUID) else UUID(str(report_id))
        row = self.repo.get_by_id(rid)
        if row is None:
            return None
        return self._detail(row)

    def mark_feedback(self, report_id, useful: bool) -> dict | None:
        from uuid import UUID

        rid = report_id if isinstance(report_id, UUID) else UUID(str(report_id))
        row = self.repo.update_metadata(rid, {"feedback": "useful" if useful else "useless"})
        if row is None:
            return None
        return self._detail(row)

    def _call_ai(self, metrics, loss_attribution, abnormal, template_ctx: dict | None = None) -> str:
        user_prompt = self._build_user_prompt(metrics, loss_attribution, abnormal)
        try:
            resp = self.ai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = resp.choices[0].message.content or ""
        except Exception as exc:
            logger.exception("AI 调用失败，回退规则模板: %s", exc)
            self.audit.log(
                action="ai_report_fallback",
                module="ai",
                object_type="ai_report",
                object_id="",
                result="warning",
                reason=str(exc),
            )
            return self._rule_based_template(metrics, loss_attribution, abnormal, template_ctx)

        content, hits = sanitize_ai_content(content)
        for pat in hits:
            self.audit.log(
                action="ai_report_filtered",
                module="ai",
                object_type="ai_report",
                object_id="",
                result="warning",
                reason=f"过滤禁用词汇: {pat}",
            )
        return content

    def _rule_based_template(
        self, metrics, loss_attribution, abnormal, template_ctx: dict | None = None
    ) -> str:
        ctx = template_ctx or {}
        scope = ctx.get("scope") or {}
        generated_at = ctx.get("generated_at") or datetime.now(timezone.utc).isoformat()
        filter_bits = []
        if scope.get("strategy_ids"):
            filter_bits.append(f"策略={','.join(scope['strategy_ids'])}")
        if scope.get("markets"):
            filter_bits.append(f"市场={','.join(scope['markets'])}")
        if scope.get("symbols"):
            filter_bits.append(f"标的={','.join(scope['symbols'])}")
        filter_text = "；".join(filter_bits) if filter_bits else "全部（无额外过滤）"

        if not metrics.get("has_data"):
            return (
                "# 复盘报告\n\n"
                f"- 生成时间：{generated_at}\n"
                f"- 过滤条件：{filter_text}\n"
                f"- 数据区间：{metrics.get('range_start', '')} 至 {metrics.get('range_end', '')}\n\n"
                "所选范围内无交易数据，无法生成分析。\n\n"
                "> 本报告由规则模板生成，仅供复盘参考，不构成投资建议，不提供直接下单入口。\n"
            )
        loss_lines = "\n".join(f"- {x}" for x in loss_attribution) or "- 暂无明显亏损归因"
        abnormal_lines = "\n".join(f"- {x}" for x in abnormal) or "- 未检测到异常模式"
        ranking = metrics.get("strategy_ranking") or []
        if ranking:
            rank_lines = "\n".join(
                f"- {i+1}. {r.get('strategy_id')}: 盈亏 {r.get('total_pnl')}，"
                f"笔数 {r.get('trade_count')}，胜率 {r.get('win_rate')}"
                for i, r in enumerate(ranking)
            )
        else:
            rank_lines = "- 暂无策略维度数据"
        return f"""# 量化交易复盘报告

## 数据范围
- 生成时间：{generated_at}
- 过滤条件：{filter_text}
- 数据区间：{metrics.get('range_start', '')} 至 {metrics.get('range_end', '')}

## 总体表现
- 总盈亏：{metrics.get('total_pnl')}
- 胜率：{metrics.get('win_rate')}
- 盈亏比：{metrics.get('profit_loss_ratio')}
- 最大回撤：{metrics.get('max_drawdown')}
- 交易次数：{metrics.get('trade_count')}
- 交易频率（日均笔数）：{metrics.get('trade_frequency')}
- 已实现回合：{metrics.get('round_trips')}
- 手续费：{metrics.get('fee_total')}
- 平均持仓分钟：{metrics.get('avg_holding_minutes')}

## 策略表现排名
{rank_lines}

## 风险事件
- 风控拒绝次数：{metrics.get('risk_reject_count')}
- 熔断次数：{metrics.get('circuit_breaker_count')}
- 连续亏损次数：{metrics.get('consecutive_loss_count')}

## 亏损归因
{loss_lines}

## 异常模式
{abnormal_lines}

## 改进建议
- 建议关注连续亏损后的策略暂停机制。
- 建议复核风控拒绝较多的标的与参数。
- 建议结合最大回撤复核仓位上限。

## 局限性
- 本报告基于历史数据，不代表未来表现。
- 仅供复盘参考，不构成投资建议，不提供直接下单入口。

> 本报告由规则模板生成（model_name=rule_based）。
"""

    def _loss_attribution(self, trades: list[dict]) -> list[str]:
        if not trades:
            return []
        from collections import defaultdict
        from decimal import Decimal

        lots: dict[str, list] = defaultdict(list)
        pnl_by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for t in trades:
            symbol = str(t["symbol"])
            side = str(t["side"])
            qty = Decimal(str(t["quantity"]))
            price = Decimal(str(t["price"]))
            if side == "buy":
                lots[symbol].append((qty, price))
                continue
            remain = qty
            while remain > 0 and lots[symbol]:
                lot_qty, lot_price = lots[symbol][0]
                matched = min(remain, lot_qty)
                pnl_by_symbol[symbol] += (price - lot_price) * matched
                lot_qty -= matched
                remain -= matched
                if lot_qty <= 0:
                    lots[symbol].pop(0)
                else:
                    lots[symbol][0] = (lot_qty, lot_price)

        losses = [(s, p) for s, p in pnl_by_symbol.items() if p < 0]
        losses.sort(key=lambda x: x[1])
        return [f"标的 {s} 已实现盈亏 {p}" for s, p in losses[:5]]

    def _detect_abnormal(self, metrics: dict) -> list[str]:
        abnormal: list[str] = []
        if int(metrics.get("consecutive_loss_count") or 0) >= 3:
            abnormal.append("连续亏损达到 3 次以上")
        trade_count = int(metrics.get("trade_count") or 0)
        reject = int(metrics.get("risk_reject_count") or 0)
        if trade_count > 0 and reject > trade_count * 0.3:
            abnormal.append("风控拒绝比例超过 30%，可能存在策略参数问题")
        if int(metrics.get("circuit_breaker_count") or 0) > 0:
            abnormal.append("区间内发生过熔断或紧急停止")
        return abnormal

    def _build_user_prompt(self, metrics, loss_attribution, abnormal) -> str:
        return f"""请基于以下数据生成复盘分析：

## 指标
{metrics}

## 亏损归因
{loss_attribution}

## 异常模式
{abnormal}

请输出：总体表现摘要、策略表现排名、亏损归因、风控事件分析、异常行为提示、改进建议。
不要输出任何直接下单指令。
"""

    def _summary(self, row) -> dict:
        return {
            "report_id": str(row.report_id),
            "range_start": row.range_start.isoformat(),
            "range_end": row.range_end.isoformat(),
            "scope": row.scope,
            "model_name": row.model_name,
            "generated_at": row.generated_at.isoformat(),
            "metrics_summary": {
                "has_data": (row.metrics or {}).get("has_data"),
                "total_pnl": (row.metrics or {}).get("total_pnl"),
                "trade_count": (row.metrics or {}).get("trade_count"),
                "win_rate": (row.metrics or {}).get("win_rate"),
            },
            "metadata": row.metadata_ or {},
        }

    def _detail(self, row) -> dict:
        return {
            "report_id": str(row.report_id),
            "range_start": row.range_start.isoformat(),
            "range_end": row.range_end.isoformat(),
            "scope": row.scope,
            "metrics": row.metrics,
            "content": row.content,
            "content_format": row.content_format,
            "model_name": row.model_name,
            "generated_at": row.generated_at.isoformat(),
            "metadata": row.metadata_ or {},
        }
