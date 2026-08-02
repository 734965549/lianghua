import { api } from "./client";

export interface StrategyItem {
  strategy_id: string;
  name: string;
  description: string;
  enabled: boolean;
  running: boolean;
  supported_markets: string[];
  parameters: Record<string, unknown>;
  parameters_schema?: Record<string, unknown>;
  kind: "builtin" | "rule";
  status: "draft" | "published" | "archived";
  current_version: number | null;
  editable: boolean;
  validation_errors: string[];
  definition_schema_version?: number;
}

export interface IndicatorCatalog {
  indicators: Array<{
    type: string;
    name: string;
    outputs: string[];
    params: Array<{ name: string; type: string; min?: number; max?: number }>;
    sources: string[];
  }>;
  operators: Array<{ operator: string; label: string; arity: number }>;
  fields: string[];
  formula_operators?: string[];
  formula_ref_help?: string;
  schema_version: number;
}

export interface StrategyVersionItem {
  version: number;
  status: string;
  checksum: string;
  published_at: string | null;
  created_at: string | null;
  change_note: string;
}

export interface StrategyDefinition {
  schema_version: number;
  market: string;
  interval: string;
  parameters: Record<string, unknown>;
  indicators: Array<Record<string, unknown>>;
  entry_rule: Record<string, unknown>;
  exit_rule: Record<string, unknown>;
  execution: Record<string, unknown>;
  risk: Record<string, unknown>;
  symbols?: {
    mode: "fixed" | "runtime";
    list?: string[];
    max_concurrent?: number;
  };
  formulas?: Array<{ id: string; expression: string }>;
}

export const DEFAULT_DEFINITION: StrategyDefinition = {
  schema_version: 1,
  market: "stock",
  interval: "1d",
  parameters: {
    fast: { type: "integer", default: 5, min: 2, max: 100 },
    slow: { type: "integer", default: 20, min: 3, max: 300 },
    quantity: { type: "decimal", default: "100" },
  },
  indicators: [
    { id: "fast_ma", type: "sma", source: "close", period: { parameter: "fast" } },
    { id: "slow_ma", type: "sma", source: "close", period: { parameter: "slow" } },
  ],
  entry_rule: {
    all: [
      {
        operator: "cross_above",
        left: { indicator: "fast_ma" },
        right: { indicator: "slow_ma" },
      },
    ],
  },
  exit_rule: {
    any: [
      {
        operator: "cross_below",
        left: { indicator: "fast_ma" },
        right: { indicator: "slow_ma" },
      },
    ],
  },
  execution: { quantity: { parameter: "quantity" }, cooldown_bars: 1 },
  symbols: { mode: "runtime", list: [], max_concurrent: 5 },
  formulas: [],
  risk: { stop_loss_pct: "5", take_profit_pct: "10", max_position_pct: "30" },
};

export function getIndicatorCatalog() {
  return api.get<IndicatorCatalog>("/indicator-catalog");
}

export function createStrategy(data: {
  name: string;
  description?: string;
  definition?: StrategyDefinition;
  parameters?: Record<string, unknown>;
}) {
  return api.post<StrategyItem>("/strategies", data);
}

export function updateStrategy(
  strategyId: string,
  data: {
    name?: string;
    description?: string;
    definition?: StrategyDefinition;
    parameters?: Record<string, unknown>;
  },
) {
  return api.put<StrategyItem>(`/strategies/${strategyId}`, data);
}

export function validateStrategyDefinition(strategyId: string, definition: StrategyDefinition) {
  return api.post<{ valid: boolean; errors: string[] }>(
    `/strategies/${strategyId}/validate`,
    { definition },
  );
}

export function publishStrategy(strategyId: string, changeNote = "") {
  return api.post<StrategyItem>(`/strategies/${strategyId}/publish`, { change_note: changeNote });
}

export function cloneStrategy(strategyId: string, name?: string) {
  return api.post<StrategyItem>(`/strategies/${strategyId}/clone`, { name });
}

export function archiveStrategy(strategyId: string) {
  return api.post<StrategyItem>(`/strategies/${strategyId}/archive`, {});
}

export function listStrategyVersions(strategyId: string) {
  return api.get<StrategyVersionItem[]>(`/strategies/${strategyId}/versions`);
}

export function getStrategyVersion(strategyId: string, version: number) {
  return api.get<{ definition: StrategyDefinition; version: number; checksum: string }>(
    `/strategies/${strategyId}/versions/${version}`,
  );
}

export function getStrategy(strategyId: string) {
  return api.get<StrategyItem>(`/strategies/${strategyId}`);
}

export interface AiStrategyGenerateResult {
  /** 建议的策略名称 */
  name: string;
  /** 建议的策略描述 */
  description: string;
  /** 完整规则 DSL，可直接写入 StrategyBuilder */
  definition: StrategyDefinition;
  validation: { valid: boolean; errors: string[] };
  model_name: string;
}

/** AI 自然语言生成策略 definition（不自动创建策略，需用户保存） */
export function generateStrategyFromPrompt(data: {
  prompt: string;
  market?: string;
  interval?: string;
}) {
  return api.post<AiStrategyGenerateResult>("/ai/strategies/generate", data, {
    signal: AbortSignal.timeout(130_000),
  });
}
