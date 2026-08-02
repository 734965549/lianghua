from decimal import Decimal, ROUND_DOWN
from typing import Any

from app.schemas.enums import OrderSide, PriceType, SignalAction
from app.sdk.models import KlineBar, QuoteSnapshot
from app.strategies.base import Strategy
from app.strategies.formula_evaluator import FormulaEngine
from app.strategies.indicators.base import Indicator, create_indicator_from_def
from app.strategies.rule_evaluator import RuleEvaluator
from app.strategies.rule_schema import DEFAULT_SYMBOLS_CONFIG
from app.strategies.rule_validator import resolve_parameters


def _resolve_period(spec: Any, parameters: dict) -> int:
    if isinstance(spec, int):
        return spec
    if isinstance(spec, dict) and "parameter" in spec:
        return int(parameters[spec["parameter"]])
    raise ValueError(f"无效的 period 规格: {spec}")


def _resolve_operand_decimal(spec: Any, parameters: dict) -> Decimal:
    if isinstance(spec, dict) and "parameter" in spec:
        return Decimal(str(parameters[spec["parameter"]]))
    if isinstance(spec, dict) and "constant" in spec:
        return Decimal(str(spec["constant"]))
    return Decimal(str(spec))


def _indicator_warmup(ind_def: dict, parameters: dict) -> int:
    ind_type = ind_def.get("type")
    if ind_type == "macd":
        params = ind_def.get("params", {})
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        return slow + signal + 1
    period = _resolve_period(ind_def["period"], parameters)
    return period + 1


class RuleStrategy(Strategy):
    """基于 DSL 规则的通用策略实现。"""

    strategy_id: str = ""
    name: str = ""
    description: str = ""
    version: str = "1"

    def __init__(
        self,
        *,
        strategy_id: str,
        name: str,
        definition: dict,
        parameters: dict,
        version: int = 1,
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.definition = definition
        self.resolved_params = resolve_parameters(definition, parameters)
        self.version = str(version)
        self.parameters = self.resolved_params
        self._interval = definition.get("interval", "1d")
        self._entry_rule = definition.get("entry_rule")
        self._exit_rule = definition.get("exit_rule")
        self._execution = definition.get("execution", {})
        self._risk = definition.get("risk", {})
        self._formulas = definition.get("formulas", []) or []
        self._cooldown_bars = int(self._execution.get("cooldown_bars", 0))
        self._quantity_spec = self._execution.get("quantity")
        self._quantity_pct_spec = self._execution.get("quantity_pct")

        sym_cfg = definition.get("symbols") or DEFAULT_SYMBOLS_CONFIG
        self._symbol_mode = sym_cfg.get("mode", "runtime")
        self._fixed_symbols = set(sym_cfg.get("list") or [])
        self._max_concurrent = int(sym_cfg.get("max_concurrent", 5))

        self._indicators_by_symbol: dict[str, dict[str, Indicator]] = {}
        self._prev_bar_fields: dict[str, dict[str, Decimal]] = {}
        self._formula_engines: dict[str, FormulaEngine] = {}
        self._formula_values: dict[str, dict[str, Decimal | None]] = {}
        self._formula_prev_values: dict[str, dict[str, Decimal | None]] = {}
        self._positions: dict[str, Decimal] = {}
        self._entry_prices: dict[str, Decimal] = {}
        self._cooldown_remaining: dict[str, int] = {}
        self._last_signal_bar: dict[str, str] = {}
        self._warmup = self._compute_warmup()

    def _compute_warmup(self) -> int:
        max_warmup = 1
        for ind_def in self.definition.get("indicators", []):
            try:
                max_warmup = max(max_warmup, _indicator_warmup(ind_def, self.resolved_params))
            except (KeyError, ValueError, TypeError):
                continue
        return max_warmup

    @property
    def warmup_bars(self) -> int:
        return self._warmup

    def _resolve_runtime_symbols(self, context) -> set[str]:
        runtime = set(context.parameters.get("symbols") or [])
        if self._symbol_mode == "fixed":
            return set(self._fixed_symbols)
        return runtime

    def _is_symbol_allowed(self, symbol: str) -> bool:
        if self._symbol_mode == "fixed":
            return symbol in self._fixed_symbols
        if not self._allowed_runtime_symbols:
            return True
        return symbol in self._allowed_runtime_symbols

    def _open_position_count(self) -> int:
        return sum(1 for qty in self._positions.values() if qty > 0)

    def _ensure_symbol(self, symbol: str) -> None:
        if symbol in self._indicators_by_symbol:
            return
        indicators: dict[str, Indicator] = {}
        for ind_def in self.definition.get("indicators", []):
            indicators[ind_def["id"]] = create_indicator_from_def(ind_def, self.resolved_params)
        self._indicators_by_symbol[symbol] = indicators
        self._prev_bar_fields[symbol] = {}
        self._formula_engines[symbol] = FormulaEngine(
            formulas=self._formulas,
            indicators=indicators,
            parameters=self.resolved_params,
            bar_fields={},
        )
        self._formula_values[symbol] = {}
        self._formula_prev_values[symbol] = {}
        self._positions[symbol] = Decimal("0")
        self._entry_prices[symbol] = Decimal("0")
        self._cooldown_remaining[symbol] = 0

    def _update_indicators(self, bar: KlineBar) -> dict[str, Decimal]:
        self._ensure_symbol(bar.symbol)
        fields = {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        prev = self._prev_bar_fields.get(bar.symbol, {})
        bar_fields = dict(fields)
        for key, val in prev.items():
            bar_fields[f"_prev_{key}"] = val

        indicators = self._indicators_by_symbol[bar.symbol]
        for ind in indicators.values():
            ind.update(bar)

        engine = self._formula_engines[bar.symbol]
        engine._bar_fields = bar_fields
        engine._indicators = indicators
        prev_vals = dict(self._formula_values.get(bar.symbol, {}))
        self._formula_prev_values[bar.symbol] = prev_vals
        self._formula_values[bar.symbol] = engine.evaluate_all()

        self._prev_bar_fields[bar.symbol] = fields
        return bar_fields

    def _sync_position(self, symbol: str) -> None:
        if self.context is None:
            return
        pos = self.context.get_position(symbol)
        if pos is not None:
            self._positions[symbol] = Decimal(str(pos.get("quantity", "0")))
            avg = pos.get("avg_cost")
            if avg and Decimal(str(avg)) > 0:
                self._entry_prices[symbol] = Decimal(str(avg))

    def _resolve_quantity(self, bar: KlineBar) -> Decimal:
        if self._quantity_spec is not None:
            return _resolve_operand_decimal(self._quantity_spec, self.resolved_params)

        if self._quantity_pct_spec is not None and self.context is not None:
            pct = _resolve_operand_decimal(self._quantity_pct_spec, self.resolved_params)
            max_pct = Decimal(str(self._risk.get("max_position_pct", "100")))
            effective_pct = min(pct, max_pct) / Decimal("100")

            account = self.context.get_account()
            available = Decimal(str(account.get("available_cash", "0")))
            price = bar.close
            if price <= 0:
                return Decimal("0")

            open_count = self._open_position_count()
            slots = max(self._max_concurrent - open_count, 1)
            alloc = available * effective_pct / Decimal(slots)
            raw_qty = (alloc / price).quantize(Decimal("1"), rounding=ROUND_DOWN)
            return max(raw_qty, Decimal("0"))

        return Decimal("100")

    def _check_risk_exit(self, symbol: str, bar: KlineBar) -> str | None:
        entry = self._entry_prices.get(symbol, Decimal("0"))
        if entry <= 0:
            return None

        pnl_pct = (bar.close - entry) / entry * Decimal("100")
        stop_loss = self._risk.get("stop_loss_pct")
        take_profit = self._risk.get("take_profit_pct")

        if stop_loss is not None and pnl_pct <= -Decimal(str(stop_loss)):
            return f"止损触发 {pnl_pct:.2f}%"
        if take_profit is not None and pnl_pct >= Decimal(str(take_profit)):
            return f"止盈触发 {pnl_pct:.2f}%"
        return None

    def _submit_exit(self, bar: KlineBar, *, reason: str, bar_key: str) -> list[str]:
        qty = self._positions.get(bar.symbol, Decimal("0"))
        if qty <= 0 or self.context is None:
            return []

        sid = self.context.submit_signal(
            symbol=bar.symbol,
            market=bar.market,
            side=OrderSide.SELL,
            action=SignalAction.CLOSE,
            price_type=PriceType.LIMIT,
            price=bar.close,
            quantity=qty,
            reason=reason,
            metadata={"strategy_version": self.version},
        )
        self._positions[bar.symbol] = Decimal("0")
        self._entry_prices[bar.symbol] = Decimal("0")
        self._cooldown_remaining[bar.symbol] = self._cooldown_bars
        self._last_signal_bar[bar.symbol] = bar_key
        return [sid]

    def on_start(self, context) -> None:
        self.context = context
        self._allowed_runtime_symbols = self._resolve_runtime_symbols(context)
        symbols = (
            list(self._fixed_symbols)
            if self._symbol_mode == "fixed"
            else list(self._allowed_runtime_symbols)
        )
        if not symbols and context.parameters.get("symbols"):
            symbols = list(context.parameters.get("symbols"))

        for symbol in symbols:
            self._ensure_symbol(symbol)
            warmup_bars = context.get_klines(symbol, self._interval, self._warmup)
            for bar in warmup_bars:
                if bar.symbol == symbol:
                    self._update_indicators(bar)

        context.log(
            "info",
            f"规则策略 {self.strategy_id} v{self.version} 启动，"
            f"预热 {self._warmup} 根，监控 {len(symbols)} 个标的，"
            f"最大并发持仓 {self._max_concurrent}",
        )

    def on_quote(self, quote: QuoteSnapshot) -> list:
        return []

    def on_bar(self, bar: KlineBar) -> list:
        if self.context is None:
            return []
        if not self._is_symbol_allowed(bar.symbol):
            return []

        bar_fields = self._update_indicators(bar)
        self._sync_position(bar.symbol)

        bar_key = bar.bar_time.isoformat()
        if self._last_signal_bar.get(bar.symbol) == bar_key:
            return []

        has_position = self._positions.get(bar.symbol, Decimal("0")) > 0

        if has_position:
            risk_reason = self._check_risk_exit(bar.symbol, bar)
            if risk_reason:
                return self._submit_exit(bar, reason=risk_reason, bar_key=bar_key)

        if self._cooldown_remaining.get(bar.symbol, 0) > 0:
            self._cooldown_remaining[bar.symbol] -= 1
            return []

        indicators = self._indicators_by_symbol[bar.symbol]
        evaluator = RuleEvaluator(
            indicators=indicators,
            parameters=self.resolved_params,
            bar_fields=bar_fields,
            formula_values=self._formula_values.get(bar.symbol, {}),
            formula_prev_values=self._formula_prev_values.get(bar.symbol, {}),
        )

        signals: list[str] = []

        if not has_position and self._entry_rule:
            if self._open_position_count() >= self._max_concurrent:
                return []
            if evaluator.evaluate(self._entry_rule):
                qty = self._resolve_quantity(bar)
                if qty <= 0:
                    return []
                sid = self.context.submit_signal(
                    symbol=bar.symbol,
                    market=bar.market,
                    side=OrderSide.BUY,
                    action=SignalAction.OPEN,
                    price_type=PriceType.LIMIT,
                    price=bar.close,
                    quantity=qty,
                    reason="规则策略买入信号",
                    metadata={"strategy_version": self.version},
                )
                signals.append(sid)
                self._positions[bar.symbol] = qty
                self._entry_prices[bar.symbol] = bar.close
                self._cooldown_remaining[bar.symbol] = self._cooldown_bars
                self._last_signal_bar[bar.symbol] = bar_key

        elif has_position and self._exit_rule:
            if evaluator.evaluate(self._exit_rule):
                signals.extend(
                    self._submit_exit(bar, reason="规则策略卖出信号", bar_key=bar_key)
                )

        return signals

    def on_stop(self) -> None:
        if self.context:
            self.context.log("info", f"规则策略 {self.strategy_id} 停止")
