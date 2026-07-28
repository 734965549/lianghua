from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.sdk.models import PlaceOrderRequest
from app.schemas.error_codes import ErrorCode
from app.services.time_utils import is_in_session


@dataclass
class RiskContext:
    request: PlaceOrderRequest
    system_status: str
    risk_config: dict
    account_asset: dict
    positions: list[dict]
    today_trade_count: int
    today_pnl: Decimal
    recent_signals: list[dict]
    now: datetime
    latest_price: Decimal | None = None


@dataclass
class RuleResult:
    rule_code: str
    result: str
    reason: str = ""


class RiskRule(ABC):
    rule_code: str

    @abstractmethod
    def check(self, ctx: RiskContext) -> RuleResult: ...


class SystemStateRule(RiskRule):
    rule_code = "RISK_SYSTEM_STATE"
    ALLOWED = {"trading"}

    def check(self, ctx: RiskContext) -> RuleResult:
        if ctx.system_status in self.ALLOWED:
            return RuleResult(self.rule_code, "passed")
        return RuleResult(
            self.rule_code,
            "rejected",
            f"系统状态 {ctx.system_status} 不允许提交新委托",
        )


class SymbolWhitelistRule(RiskRule):
    rule_code = "RISK_SYMBOL_WHITELIST"

    def check(self, ctx: RiskContext) -> RuleResult:
        allowed = set(ctx.risk_config.get("allowed_symbols", []))
        if not allowed or ctx.request.symbol in allowed:
            return RuleResult(self.rule_code, "passed")
        return RuleResult(self.rule_code, "rejected", f"{ctx.request.symbol} 不在白名单")


class SymbolBlacklistRule(RiskRule):
    rule_code = "RISK_SYMBOL_BLACKLIST"

    def check(self, ctx: RiskContext) -> RuleResult:
        if ctx.request.symbol in set(ctx.risk_config.get("blocked_symbols", [])):
            return RuleResult(self.rule_code, "rejected", f"{ctx.request.symbol} 在黑名单")
        return RuleResult(self.rule_code, "passed")


class TradingSessionRule(RiskRule):
    rule_code = "RISK_TRADING_SESSION"

    def check(self, ctx: RiskContext) -> RuleResult:
        sessions = ctx.risk_config.get("trading_sessions", [])
        if is_in_session(ctx.now, sessions):
            return RuleResult(self.rule_code, "passed")
        return RuleResult(self.rule_code, "rejected", "当前不在允许交易时段")


class OrderAmountRule(RiskRule):
    rule_code = "RISK_ORDER_AMOUNT_LIMIT"

    def check(self, ctx: RiskContext) -> RuleResult:
        price = ctx.request.price or Decimal("0")
        if price <= 0 and ctx.latest_price:
            price = ctx.latest_price
        if price <= 0:
            return RuleResult(self.rule_code, "passed")
        amount = price * ctx.request.quantity
        limit = Decimal(str(ctx.risk_config.get("max_order_amount", 0)))
        if limit > 0 and amount > limit:
            return RuleResult(
                self.rule_code,
                "rejected",
                f"单笔金额 {amount} 超过上限 {limit}",
            )
        return RuleResult(self.rule_code, "passed")


class OrderQuantityRule(RiskRule):
    rule_code = "RISK_ORDER_QUANTITY_LIMIT"

    def check(self, ctx: RiskContext) -> RuleResult:
        limit = Decimal(str(ctx.risk_config.get("max_order_quantity", 0)))
        if limit > 0 and ctx.request.quantity > limit:
            return RuleResult(
                self.rule_code,
                "rejected",
                f"单笔数量 {ctx.request.quantity} 超过上限 {limit}",
            )
        return RuleResult(self.rule_code, "passed")


class SymbolPositionRule(RiskRule):
    rule_code = "RISK_SYMBOL_POSITION_LIMIT"

    def check(self, ctx: RiskContext) -> RuleResult:
        limit = Decimal(str(ctx.risk_config.get("max_symbol_position", 0)))
        pos_qty = sum(
            Decimal(str(p.get("quantity", 0)))
            for p in ctx.positions
            if p.get("symbol") == ctx.request.symbol
        )
        side = ctx.request.side.value if hasattr(ctx.request.side, "value") else ctx.request.side
        new_qty = pos_qty + ctx.request.quantity if side == "buy" else pos_qty
        if limit > 0 and new_qty > limit:
            return RuleResult(
                self.rule_code,
                "rejected",
                f"标的 {ctx.request.symbol} 持仓 {new_qty} 超过上限 {limit}",
            )
        return RuleResult(self.rule_code, "passed")


class TotalPositionRule(RiskRule):
    rule_code = "RISK_TOTAL_POSITION_LIMIT"

    def check(self, ctx: RiskContext) -> RuleResult:
        limit = Decimal(str(ctx.risk_config.get("max_total_position", 0)))
        total = sum(
            Decimal(str(p.get("market_value", 0)))
            for p in ctx.positions
        )
        side = ctx.request.side.value if hasattr(ctx.request.side, "value") else ctx.request.side
        # 买入时计入本次新委托敞口，避免已接近上限时仍可通过
        if side == "buy":
            price = ctx.request.price or Decimal("0")
            if price <= 0 and ctx.latest_price:
                price = ctx.latest_price
            if price > 0:
                total += price * ctx.request.quantity
        if limit > 0 and total > limit:
            return RuleResult(
                self.rule_code,
                "rejected",
                f"总仓位 {total} 超过上限 {limit}",
            )
        return RuleResult(self.rule_code, "passed")


class DailyLossRule(RiskRule):
    rule_code = ErrorCode.RISK_DAILY_LOSS_LIMIT

    def check(self, ctx: RiskContext) -> RuleResult:
        limit = Decimal(str(ctx.risk_config.get("daily_loss_limit", 0)))
        if limit > 0 and ctx.today_pnl < 0 and abs(ctx.today_pnl) >= limit:
            return RuleResult(
                self.rule_code,
                "rejected",
                f"当日亏损 {abs(ctx.today_pnl)} 达到熔断阈值 {limit}",
            )
        return RuleResult(self.rule_code, "passed")


class DailyTradeCountRule(RiskRule):
    rule_code = "RISK_DAILY_TRADE_COUNT"

    def check(self, ctx: RiskContext) -> RuleResult:
        limit = int(ctx.risk_config.get("daily_trade_count_limit", 0))
        if limit > 0 and ctx.today_trade_count >= limit:
            return RuleResult(
                self.rule_code,
                "rejected",
                f"当日交易次数 {ctx.today_trade_count} 超过上限 {limit}",
            )
        return RuleResult(self.rule_code, "passed")


class DuplicateSignalRule(RiskRule):
    rule_code = "RISK_DUPLICATE_SIGNAL"

    def check(self, ctx: RiskContext) -> RuleResult:
        window = int(ctx.risk_config.get("duplicate_signal_window_seconds", 3))
        cutoff = ctx.now.timestamp() - window
        strategy_id = ctx.request.metadata.get("strategy_id", "")
        side = ctx.request.side.value if hasattr(ctx.request.side, "value") else ctx.request.side
        action = ctx.request.action.value if hasattr(ctx.request.action, "value") else ctx.request.action
        for signal in ctx.recent_signals:
            if (
                signal.get("strategy_id") == strategy_id
                and signal.get("symbol") == ctx.request.symbol
                and signal.get("side") == side
                and signal.get("action") == action
                and signal.get("ts", 0) >= cutoff
            ):
                return RuleResult(self.rule_code, "rejected", "短时间重复信号")
        return RuleResult(self.rule_code, "passed")


RULES_ORDERED = [
    SystemStateRule,
    SymbolWhitelistRule,
    SymbolBlacklistRule,
    TradingSessionRule,
    OrderAmountRule,
    OrderQuantityRule,
    SymbolPositionRule,
    TotalPositionRule,
    DailyLossRule,
    DailyTradeCountRule,
    DuplicateSignalRule,
]
