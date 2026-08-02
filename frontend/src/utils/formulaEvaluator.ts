/** 安全公式求值（与后端 formula_evaluator.py 对齐，禁止 eval）。 */

export type FormulaPreviewContext = {
  indicators: Record<string, number | Record<string, number>>;
  parameters: Record<string, number>;
  barFields: Record<string, number>;
  formulas: Record<string, number | null>;
};

export class FormulaError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FormulaError";
  }
}

const TokKind = {
  NUMBER: "number",
  REF: "ref",
  PLUS: "+",
  MINUS: "-",
  STAR: "*",
  SLASH: "/",
  LPAREN: "(",
  RPAREN: ")",
  EOF: "eof",
} as const;

type TokKind = (typeof TokKind)[keyof typeof TokKind];

type Token = { kind: TokKind; value: string };

function tokenize(expr: string): Token[] {
  const trimmed = expr.trim();
  if (!trimmed) throw new FormulaError("公式不能为空");
  const tokens: Token[] = [];
  let i = 0;
  while (i < trimmed.length) {
    const ch = trimmed[i];
    if (/\s/.test(ch)) {
      i += 1;
      continue;
    }
    if ("+*/()".includes(ch)) {
      tokens.push({ kind: ch as TokKind, value: ch });
      i += 1;
      continue;
    }
    if (ch === "-") {
      tokens.push({ kind: TokKind.MINUS, value: "-" });
      i += 1;
      continue;
    }
    if ("@$#&".includes(ch)) {
      let j = i;
      while (j < trimmed.length && /[\w.$#@&]/.test(trimmed[j])) j += 1;
      tokens.push({ kind: TokKind.REF, value: trimmed.slice(i, j) });
      i = j;
      continue;
    }
    if (/[\d.]/.test(ch)) {
      let j = i;
      while (j < trimmed.length && /[\d.]/.test(trimmed[j])) j += 1;
      tokens.push({ kind: TokKind.NUMBER, value: trimmed.slice(i, j) });
      i = j;
      continue;
    }
    throw new FormulaError(`非法字符: ${ch}`);
  }
  tokens.push({ kind: TokKind.EOF, value: "" });
  return tokens;
}

function resolveRef(ref: string, ctx: FormulaPreviewContext): number | null {
  if (ref.startsWith("&")) {
    const id = ref.slice(1);
    const val = ctx.formulas[id];
    return val === undefined || val === null ? null : val;
  }
  if (ref.startsWith("@")) {
    const body = ref.slice(1);
    const dot = body.indexOf(".");
    const id = dot >= 0 ? body.slice(0, dot) : body;
    const output = dot >= 0 ? body.slice(dot + 1) : "value";
    const ind = ctx.indicators[id];
    if (ind === undefined) return null;
    if (typeof ind === "number") return output === "value" ? ind : null;
    const val = ind[output];
    return val === undefined ? null : val;
  }
  if (ref.startsWith("$")) {
    const field = ref.slice(1);
    const val = ctx.barFields[field];
    return val === undefined ? null : val;
  }
  if (ref.startsWith("#")) {
    const param = ref.slice(1);
    const val = ctx.parameters[param];
    return val === undefined ? null : val;
  }
  return null;
}

class Evaluator {
  private pos = 0;
  private tokens: Token[];
  private resolver: (ref: string) => number | null;

  constructor(tokens: Token[], resolver: (ref: string) => number | null) {
    this.tokens = tokens;
    this.resolver = resolver;
  }

  evaluate(): number | null {
    const val = this.expr();
    if (this.cur().kind !== TokKind.EOF) throw new FormulaError("表达式未预期结束");
    return val;
  }

  private cur(): Token {
    return this.tokens[this.pos];
  }

  private eat(kind?: TokKind): Token {
    const tok = this.cur();
    if (kind && tok.kind !== kind) {
      throw new FormulaError(`语法错误，期望 ${kind}，实际 ${tok.kind}`);
    }
    this.pos += 1;
    return tok;
  }

  private expr(): number | null {
    let val = this.term();
    while (this.cur().kind === TokKind.PLUS || this.cur().kind === TokKind.MINUS) {
      const op = this.eat().kind;
      const rhs = this.term();
      if (val === null || rhs === null) return null;
      val = op === TokKind.PLUS ? val + rhs : val - rhs;
    }
    return val;
  }

  private term(): number | null {
    let val = this.factor();
    while (this.cur().kind === TokKind.STAR || this.cur().kind === TokKind.SLASH) {
      const op = this.eat().kind;
      const rhs = this.factor();
      if (val === null || rhs === null) return null;
      if (op === TokKind.STAR) val = val * rhs;
      else {
        if (rhs === 0) return null;
        val = val / rhs;
      }
    }
    return val;
  }

  private factor(): number | null {
    if (this.cur().kind === TokKind.MINUS) {
      this.eat(TokKind.MINUS);
      const val = this.factor();
      return val === null ? null : -val;
    }
    if (this.cur().kind === TokKind.NUMBER) {
      const n = Number(this.eat(TokKind.NUMBER).value);
      return Number.isFinite(n) ? n : null;
    }
    if (this.cur().kind === TokKind.REF) {
      return this.resolver(this.eat(TokKind.REF).value);
    }
    if (this.cur().kind === TokKind.LPAREN) {
      this.eat(TokKind.LPAREN);
      const val = this.expr();
      this.eat(TokKind.RPAREN);
      return val;
    }
    throw new FormulaError(`语法错误: ${this.cur().kind}`);
  }
}

export function evaluateExpression(
  expression: string,
  resolver: (ref: string) => number | null,
): number | null {
  const tokens = tokenize(expression);
  return new Evaluator(tokens, resolver).evaluate();
}

function topoSort(formulas: Array<{ id: string; expression: string }>): string[] {
  const ids = formulas.map((f) => f.id);
  const deps: Record<string, Set<string>> = {};
  for (const f of formulas) {
    const refs = new Set<string>();
    for (const tok of tokenize(f.expression)) {
      if (tok.kind === TokKind.REF && tok.value.startsWith("&")) {
        refs.add(tok.value.slice(1));
      }
    }
    deps[f.id] = refs;
  }
  const ordered: string[] = [];
  const temp = new Set<string>();

  const visit = (n: string) => {
    if (temp.has(n)) throw new FormulaError(`公式循环引用: ${n}`);
    if (ordered.includes(n)) return;
    temp.add(n);
    for (const d of deps[n] ?? []) {
      if (ids.includes(d)) visit(d);
    }
    temp.delete(n);
    ordered.push(n);
  };

  for (const id of ids) visit(id);
  return ordered;
}

export function evaluateFormulas(
  formulas: Array<{ id: string; expression: string }>,
  ctx: Omit<FormulaPreviewContext, "formulas">,
): { values: Record<string, number | null>; error?: string } {
  const values: Record<string, number | null> = {};
  try {
    const ordered = topoSort(formulas);
    for (const id of ordered) {
      const expr = formulas.find((f) => f.id === id)!.expression;
      values[id] = evaluateExpression(expr, (ref) =>
        resolveRef(ref, { ...ctx, formulas: values }),
      );
    }
    return { values };
  } catch (err) {
    return {
      values,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

/** 预览用示例上下文（基于当前指标/参数生成占位值）。 */
export function buildSamplePreviewContext(
  indicatorIds: string[],
  indicatorOutputs: Record<string, string[]>,
  parameters: Record<string, unknown>,
): Omit<FormulaPreviewContext, "formulas"> {
  const indicators: Record<string, number | Record<string, number>> = {};
  indicatorIds.forEach((id, idx) => {
    const outputs = indicatorOutputs[id] ?? ["value"];
    if (outputs.length === 1) {
      indicators[id] = 10 + idx * 2;
    } else {
      const obj: Record<string, number> = {};
      outputs.forEach((out, oi) => {
        obj[out] = 10 + idx * 2 + oi;
      });
      indicators[id] = obj;
    }
  });
  const params: Record<string, number> = {};
  for (const [k, v] of Object.entries(parameters)) {
    if (typeof v === "object" && v !== null && "default" in (v as object)) {
      params[k] = Number((v as { default: unknown }).default);
    } else if (typeof v === "number") {
      params[k] = v;
    }
  }
  return {
    indicators,
    parameters: params,
    barFields: { close: 12, open: 11, high: 13, low: 10, volume: 10000 },
  };
}
