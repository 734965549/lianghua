export type HealthData = {
  api: string;
  database: string;
  stock_sdk: string;
  futures_sdk: string;
  system_status: string;
  version: string;
};

export type SystemStatus = {
  status: string;
  status_reason: string;
  status_since: string;
  breaker_reason: string | null;
};

export type DashboardData = {
  system_status: string;
  daily_pnl: string;
  position_value: string;
  available_cash: string;
  daily_trade_count: number;
  risk_reject_count: number;
  breaker_active: boolean;
  running_strategies: number;
  latest_orders: unknown[];
  latest_alerts: SystemEvent[];
};

export type SettingsData = {
  database: { configured: boolean; host?: string; port?: number; dbname?: string };
  stock_sdk: { configured: boolean; path?: string; account_ref?: string };
  futures_sdk: { configured: boolean; path?: string; account_ref?: string };
  ai: { provider: string; configured: boolean };
  backup_dir: string;
  sensitive_fields: string[];
  sdk_mode?: string;
};

export type AuditLog = {
  id: number;
  event_time: string;
  action: string;
  module: string;
  object_type: string;
  object_id: string;
  result: string;
  reason: string;
  correlation_id: string;
  operator: string;
};

export type SystemEvent = {
  id: number;
  event_time: string;
  severity: string;
  module: string;
  event_code: string;
  message: string;
  resolved: boolean;
};

export type Paged<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type QuoteSnapshot = {
  symbol: string;
  market: string;
  last_price: string;
  change_rate: string;
  volume: string;
  bid_price?: string | null;
  ask_price?: string | null;
  bid_volume?: string | null;
  ask_volume?: string | null;
  quote_time: string;
  stale?: boolean;
};

export type KlineBar = {
  bar_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
};
