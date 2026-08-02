import { api } from "./client";

export interface BacktestItem {
  id: string;
  strategy_id: string;
  status: "pending" | "running" | "completed" | "failed";
  parameters: Record<string, unknown>;
  symbols: string[];
  start_time: string;
  end_time: string;
  granularity: string;
  fill_model: string;
  initial_cash: string;
  final_equity: string | null;
  metrics: BacktestMetrics | null;
  created_at: string;
  updated_at: string;
  provenance: {
    recorded: boolean;
    strategy_version: string;
    code_hash: string;
    data_snapshot: string;
    bar_count?: number | null;
    first_bar?: string | null;
    last_bar?: string | null;
    sources?: string[];
  };
}

export interface BacktestMetrics {
  total_return_pct: string;
  annualized_return_pct: string;
  sharpe_ratio: string;
  max_drawdown_pct: string;
  win_rate_pct: string;
  profit_factor: string;
  total_trades: number;
}

export interface BacktestResult extends BacktestItem {
  trades: BacktestTrade[];
  equity_curve: EquityPoint[];
  error_message: string | null;
}

export interface BacktestTrade {
  trade_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: string;
  price: string;
  commission: string;
  tax: string;
  trade_time: string;
}

export interface EquityPoint {
  time: string;
  equity: string;
}

export interface BacktestListResponse {
  items: BacktestItem[];
  total: number;
}

export interface CreateBacktestRequest {
  strategy_id: string;
  symbols: string[];
  start_time: string;
  end_time: string;
  initial_cash: string;
  granularity: "kline" | "simulated_tick" | "tick";
  fill_model: "next_open" | "next_close" | "vwap" | "tick_price";
  interval: string;
  parameters: Record<string, unknown>;
  strategy_version?: number;
  commission_rate: string;
  stamp_tax_rate: string;
  slippage: string;
}

export function listBacktests(offset = 0, limit = 20) {
  return api.get<BacktestListResponse>(`/backtests?offset=${offset}&limit=${limit}`);
}

export function getBacktest(id: string) {
  return api.get<BacktestResult>(`/backtests/${id}`);
}

export function createBacktest(data: CreateBacktestRequest) {
  return api.post<BacktestResult>("/backtests", data);
}

export function deleteBacktest(id: string) {
  return api.del<{ deleted: boolean }>(`/backtests/${id}`);
}
