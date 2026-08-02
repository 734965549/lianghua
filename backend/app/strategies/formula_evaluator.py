"""安全公式表达式求值（禁止 eval）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Callable

REF_PATTERN = re.compile(
    r"^@(?P<ind>[a-zA-Z_][a-zA-Z0-9_]*)(?:\.(?P<out>[a-zA-Z_][a-zA-Z0-9_]*))?$"
    r"|^\$(?P<field>open|high|low|close|volume)$"
    r"|^#(?P<param>[a-zA-Z_][a-zA-Z0-9_]*)$"
    r"|^&(?P<formula>[a-zA-Z_][a-zA-Z0-9_]*)$"
)


class FormulaError(Exception):
    pass


def _safe_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        d = Decimal(str(value)) if not isinstance(value, Decimal) else value
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not d.is_finite():
        return None
    return d


class TokKind(Enum):
    NUMBER = "number"
    REF = "ref"
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    LPAREN = "("
    RPAREN = ")"
    EOF = "eof"


@dataclass
class Token:
    kind: TokKind
    value: str = ""


def tokenize(expr: str) -> list[Token]:
    expr = expr.strip()
    if not expr:
        raise FormulaError("公式不能为空")
    tokens: list[Token] = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "+*/()":
            tokens.append(Token(TokKind(ch), ch))
            i += 1
            continue
        if ch == "-":
            tokens.append(Token(TokKind.MINUS, "-"))
            i += 1
            continue
        if ch in "@$#&":
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] in "._$#@&"):
                j += 1
            tokens.append(Token(TokKind.REF, expr[i:j]))
            i = j
            continue
        if ch.isdigit() or ch == ".":
            j = i
            while j < len(expr) and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            tokens.append(Token(TokKind.NUMBER, expr[i:j]))
            i = j
            continue
        raise FormulaError(f"非法字符: {ch}")
    tokens.append(Token(TokKind.EOF))
    return tokens


class _Evaluator:
    def __init__(self, tokens: list[Token], resolver: Callable[[str], Decimal | None]):
        self._tokens = tokens
        self._pos = 0
        self._resolve = resolver

    def _cur(self) -> Token:
        return self._tokens[self._pos]

    def _eat(self, kind: TokKind | None = None) -> Token:
        tok = self._cur()
        if kind and tok.kind != kind:
            raise FormulaError(f"语法错误，期望 {kind.value}，实际 {tok.kind.value}")
        self._pos += 1
        return tok

    def evaluate(self) -> Decimal | None:
        val = self._expr()
        if self._cur().kind != TokKind.EOF:
            raise FormulaError("表达式未预期结束")
        return val

    def _expr(self) -> Decimal | None:
        val = self._term()
        while self._cur().kind in (TokKind.PLUS, TokKind.MINUS):
            op = self._eat().kind
            rhs = self._term()
            if val is None or rhs is None:
                return None
            val = val + rhs if op == TokKind.PLUS else val - rhs
        return val

    def _term(self) -> Decimal | None:
        val = self._factor()
        while self._cur().kind in (TokKind.STAR, TokKind.SLASH):
            op = self._eat().kind
            rhs = self._factor()
            if val is None or rhs is None:
                return None
            if op == TokKind.STAR:
                val = val * rhs
            else:
                if rhs == 0:
                    return None
                val = val / rhs
        return val

    def _factor(self) -> Decimal | None:
        if self._cur().kind == TokKind.MINUS:
            self._eat(TokKind.MINUS)
            val = self._factor()
            return -val if val is not None else None
        if self._cur().kind == TokKind.NUMBER:
            return _safe_decimal(self._eat(TokKind.NUMBER).value)
        if self._cur().kind == TokKind.REF:
            return self._resolve(self._eat(TokKind.REF).value)
        if self._cur().kind == TokKind.LPAREN:
            self._eat(TokKind.LPAREN)
            val = self._expr()
            self._eat(TokKind.RPAREN)
            return val
        raise FormulaError(f"语法错误: {self._cur().kind.value}")


def evaluate_expression(expression: str, resolver: Callable[[str], Decimal | None]) -> Decimal | None:
    tokens = tokenize(expression)
    return _Evaluator(tokens, resolver).evaluate()


class FormulaEngine:
    """按拓扑顺序求值公式列表。"""

    def __init__(
        self,
        *,
        formulas: list[dict],
        indicators: dict,
        parameters: dict,
        bar_fields: dict[str, Decimal],
        use_prev: bool = False,
    ):
        self._formula_defs = [
            f for f in formulas if isinstance(f, dict) and f.get("id") and f.get("expression")
        ]
        self._indicators = indicators
        self._parameters = parameters
        self._bar_fields = bar_fields
        self._use_prev = use_prev
        self._values: dict[str, Decimal | None] = {}
        self._prev_values: dict[str, Decimal | None] = {}

    def _base_resolver(self, ref: str, values: dict[str, Decimal | None]) -> Decimal | None:
        m = REF_PATTERN.match(ref)
        if not m:
            raise FormulaError(f"非法引用: {ref}")
        if m.group("formula"):
            return values.get(m.group("formula"))
        if m.group("ind"):
            ind = self._indicators.get(m.group("ind"))
            if ind is None:
                return None
            output = m.group("out") or "value"
            if self._use_prev:
                return _safe_decimal(ind.get_prev_output(output))
            return _safe_decimal(ind.get_output(output))
        if m.group("field"):
            key = f"_prev_{m.group('field')}" if self._use_prev else m.group("field")
            return _safe_decimal(self._bar_fields.get(key))
        if m.group("param"):
            return _safe_decimal(self._parameters.get(m.group("param")))
        return None

    def evaluate_all(self) -> dict[str, Decimal | None]:
        ordered = self._topo_sort()
        current: dict[str, Decimal | None] = {}
        for fid in ordered:
            expr = next(f["expression"] for f in self._formula_defs if f["id"] == fid)
            current[fid] = evaluate_expression(
                expr, lambda ref, vals=current: self._base_resolver(ref, vals)
            )
        self._prev_values = dict(self._values)
        self._values = current
        return current

    def get(self, formula_id: str) -> Decimal | None:
        return self._values.get(formula_id)

    def get_prev(self, formula_id: str) -> Decimal | None:
        return self._prev_values.get(formula_id)

    def _topo_sort(self) -> list[str]:
        ids = [f["id"] for f in self._formula_defs]
        deps: dict[str, set[str]] = {}
        for f in self._formula_defs:
            fid = f["id"]
            refs: set[str] = set()
            for tok in tokenize(f["expression"]):
                if tok.kind == TokKind.REF and tok.value.startswith("&"):
                    refs.add(tok.value[1:])
            deps[fid] = refs
        ordered: list[str] = []
        temp: set[str] = set()

        def visit(n: str) -> None:
            if n in temp:
                raise FormulaError(f"公式循环引用: {n}")
            if n in ordered:
                return
            temp.add(n)
            for d in deps.get(n, set()):
                if d in ids:
                    visit(d)
            temp.remove(n)
            ordered.append(n)

        for fid in ids:
            visit(fid)
        return ordered
