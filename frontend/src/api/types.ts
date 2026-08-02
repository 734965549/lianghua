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
  market_data?: {
    provider: string;
    configured: boolean;
    realtime: boolean;
    catalog_sync_supported?: boolean;
    providers?: Array<{
      id: string;
      label: string;
      tier: string;
      coverage: string;
      mode: string;
      description: string;
      component_installed: boolean;
    }>;
    akshare_poll_seconds?: number;
    tdx_endpoint?: string;
    tdx_poll_seconds?: number;
    ifind_username_ref?: string;
    ifind_credentials_configured: boolean;
    ifind_component_installed: boolean;
    ifind_poll_seconds: number;
    tushare_token_configured?: boolean;
    tushare_poll_seconds?: number;
    rqdata_username_ref?: string;
    rqdata_credentials_configured?: boolean;
    rqdata_poll_seconds?: number;
    wind_poll_seconds?: number;
  };
  ai: {
    provider: string;
    base_url?: string;
    model?: string;
    configured: boolean;
  };
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
  source?: string;
  simulated?: boolean;
  stale?: boolean;
};

export type QuoteHealthState =
  | "healthy"
  | "market_closed"
  | "feed_stale"
  | "source_disconnected"
  | "subscription_disconnected"
  | "not_monitored";

export type QuoteHealthItem = {
  symbol: string;
  market: string;
  state: Exclude<QuoteHealthState, "not_monitored">;
  blocking: boolean;
  reason?: string;
  quote_time?: string;
  age_seconds?: number;
};

export type QuoteHealthReport = {
  state: QuoteHealthState;
  breaker_required: boolean;
  trade_ready: boolean;
  checked_at: string;
  timeout_seconds: number;
  items: QuoteHealthItem[];
};

export type KlineBar = {
  symbol?: string;
  market?: string;
  interval?: string;
  bar_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  source?: string;
  simulated?: boolean;
  market_date?: string;
  quality_status?: "accepted" | "quarantined";
  quality_reasons?: string[];
};

export type Instrument = {
  symbol: string;
  market: "stock" | "futures";
  name: string;
  exchange: string;
  source?: string;
};

export type InstrumentCatalog = {
  items: Instrument[];
  total: number;
  counts: {
    stock: number;
    futures: number;
  };
  source: "ifind" | "bundled" | "mixed" | string;
  last_synced_at?: string | null;
};

export type InstrumentSyncResult = {
  status: "ok" | "partial" | "failed" | "running";
  counts: {
    stock?: number;
    futures?: number;
  };
  errors: string[];
};
