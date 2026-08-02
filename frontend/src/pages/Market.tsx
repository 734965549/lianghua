import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Modal, Select, Space, Tabs, Tooltip, message } from "antd";
import {
  CloudSyncOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AllInstrumentsTable from "../components/AllInstrumentsTable";
import QuoteTable from "../components/QuoteTable";
import KlineChart from "../components/KlineChart";
import type { KlineIntegrity } from "../components/KlineChart";
import ManualOrderForm from "../components/ManualOrderForm";
import MarketDataConfigPanel from "../components/MarketDataConfigPanel";
import PageHeader from "../components/PageHeader";
import { api } from "../api/client";
import type {
  InstrumentCatalog,
  InstrumentSyncResult,
  QuoteSnapshot,
  SettingsData,
} from "../api/types";
import { formatDecimal, formatPercent, formatTime } from "../utils/format";

const SUBSCRIBE_BATCH_SIZE = 100;

type WatchlistItem = { id: string; symbol: string; market: string; alias: string; enabled: boolean };

type RiskStatus = {
  breaker_active: boolean;
  breaker_reason?: string;
  allowed_symbols: string[];
  blocked_symbols: string[];
};

function panelTitle(title: string, hint: string) {
  return (
    <div className="panel-title">
      <div className="panel-title__copy">
        <i />
        <strong>{title}</strong>
      </div>
      <small>{hint}</small>
    </div>
  );
}

export default function Market() {
  const [selected, setSelected] = useState<QuoteSnapshot | null>(null);
  const [interval, setInterval] = useState("1m");
  const [klineIntegrity, setKlineIntegrity] = useState<KlineIntegrity | null>(null);
  const [marketSettingsOpen, setMarketSettingsOpen] = useState(false);
  const qc = useQueryClient();

  const { data: watchlist } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist"),
  });

  const {
    data: catalog,
    isLoading: catalogLoading,
    isFetching: catalogFetching,
  } = useQuery({
    queryKey: ["instruments", "catalog"],
    queryFn: () => api.get<InstrumentCatalog>("/instruments?limit=10000"),
  });

  const { data: settingsData } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsData>("/settings"),
  });

  const riskStatus = useQuery({
    queryKey: ["risk-status"],
    queryFn: () => api.get<RiskStatus>("/risk/status"),
    refetchInterval: 5000,
  });

  const addMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/watchlist", body),
    onSuccess: () => {
      message.success("已加入股票池");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const removeMut = useMutation({
    mutationFn: ({ market, symbol }: { market: string; symbol: string }) =>
      api.del(`/watchlist/${market}/${symbol}`),
    onSuccess: () => {
      message.success("已从股票池移除");
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const syncCatalog = useMutation({
    mutationFn: () => api.post<InstrumentSyncResult>("/instruments/sync"),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: ["instruments"] });
      const stock = result.counts.stock ?? 0;
      const futures = result.counts.futures ?? 0;
      if (result.status === "ok") {
        message.success(`全市场目录同步完成：股票 ${stock}，期货 ${futures}`);
      } else if (result.status === "running") {
        message.info("全市场目录正在后台同步，请稍后刷新");
      } else {
        message.warning(
          `目录${result.status === "partial" ? "部分" : ""}同步失败：${result.errors.join("；")}`,
          8,
        );
      }
    },
  });

  const watchlistSymbols = useMemo(
    () =>
      (watchlist ?? [])
        .filter((item) => item.enabled)
        .map((item) => ({ market: item.market, symbol: item.symbol })),
    [watchlist],
  );

  const watchlistKeySet = useMemo(
    () => new Set((watchlist ?? []).map((item) => `${item.market}:${item.symbol}`)),
    [watchlist],
  );

  useEffect(() => {
    if (!watchlistSymbols.length) return;
    const byMarket = new Map<string, string[]>();
    watchlistSymbols.forEach((item) => {
      const list = byMarket.get(item.market) ?? [];
      list.push(item.symbol);
      byMarket.set(item.market, list);
    });
    const controllers: AbortController[] = [];
    byMarket.forEach((symbols, market) => {
      for (let index = 0; index < symbols.length; index += SUBSCRIBE_BATCH_SIZE) {
        const batch = symbols.slice(index, index + SUBSCRIBE_BATCH_SIZE);
        const controller = new AbortController();
        controllers.push(controller);
        api
          .post(
            "/quotes/subscriptions",
            { market, symbols: batch, subscriber_id: "market-page" },
            { signal: controller.signal, silent: true },
          )
          .catch(() => undefined);
      }
    });
    return () => {
      controllers.forEach((controller) => controller.abort());
      byMarket.forEach((symbols, market) => {
        api
          .del("/quotes/subscriptions", {
            body: JSON.stringify({ market, symbols, subscriber_id: "market-page" }),
            silent: true,
          })
          .catch(() => undefined);
      });
    };
  }, [watchlistSymbols]);

  const market = selected?.market ?? watchlistSymbols[0]?.market ?? "stock";
  const symbol = selected?.symbol ?? watchlistSymbols[0]?.symbol ?? "600000.SH";
  const focusQuote = useQuery({
    queryKey: ["quote", market, symbol],
    queryFn: () =>
      api.get<QuoteSnapshot>(`/quotes/${market}/${symbol}`, { silent: true }),
    enabled: Boolean(market && symbol),
    refetchInterval: 10_000,
  });
  const activeQuote = selected ?? focusQuote.data;
  const change = Number(activeQuote?.change_rate ?? 0);
  const allowedSymbols = riskStatus.data?.allowed_symbols ?? [];
  const blockedSymbols = riskStatus.data?.blocked_symbols ?? [];
  const outsideWhitelist = allowedSymbols.length > 0 && !allowedSymbols.includes(symbol);
  const blacklisted = blockedSymbols.includes(symbol);
  const orderBlockReason = !klineIntegrity?.trusted
    ? klineIntegrity?.reason || "正在核对行情卡与 K 线数据源"
    : riskStatus.isLoading
      ? "正在确认风控状态"
      : riskStatus.isError
        ? "无法读取风控状态，请稍后重试"
        : riskStatus.data?.breaker_active
          ? `系统处于交易保护状态：${riskStatus.data.breaker_reason || "请先在风险指挥台完成恢复"}`
          : blacklisted
            ? `${symbol} 位于交易黑名单`
            : outsideWhitelist
              ? `${symbol} 不在当前交易白名单`
              : null;
  const providerInfo = settingsData?.market_data?.providers?.find(
    (item) => item.id === settingsData.market_data?.provider,
  );
  const catalogInitialLoading = catalogLoading && !catalog;
  const catalogHint = catalogInitialLoading
    ? "正在加载 / 同步全市场目录…"
    : `${catalog?.total ?? 0} INSTRUMENTS · ${
        catalog?.source === "mixed"
          ? "LIVE + FALLBACK"
          : catalog?.source && catalog.source !== "bundled"
            ? `${catalog.source.toUpperCase()} LIVE CATALOG`
            : "BUILT-IN FALLBACK"
      }`;

  useEffect(() => {
    setKlineIntegrity(null);
  }, [market, symbol, interval]);

  return (
    <div>
      <PageHeader
        eyebrow="MARKET / LIVE DESK"
        title="行情工作台"
        description="以标的为中心联动行情、K 线、股票池与交易票据；红涨绿跌遵循 A 股交易习惯。"
        meta={
          <span
            className={`status-chip ${
              settingsData?.market_data?.realtime
                ? "status-chip--success"
                : "status-chip--warning"
            }`}
          >
            {settingsData?.market_data?.realtime
              ? `${providerInfo?.label ?? settingsData.market_data.provider} · ${watchlistSymbols.length} 个订阅`
              : `${providerInfo?.label ?? "MOCK"} · ${watchlistSymbols.length} 个订阅`}
          </span>
        }
        actions={
          <Space>
            <Tooltip
              title={
                settingsData?.market_data?.realtime
                  ? settingsData.market_data.catalog_sync_supported
                    ? "从当前行情源重新拉取股票和期货目录"
                    : "当前行情源负责报价，标的目录沿用上次成功同步结果"
                  : "请先启用支持目录同步的真实行情源"
              }
            >
              <Button
                icon={<CloudSyncOutlined />}
                loading={syncCatalog.isPending || catalogFetching}
                disabled={
                  !settingsData?.market_data?.catalog_sync_supported
                }
                onClick={() => syncCatalog.mutate()}
              >
                同步全市场
              </Button>
            </Tooltip>
            <Button
              icon={<SettingOutlined />}
              onClick={() => setMarketSettingsOpen(true)}
            >
              行情源设置
            </Button>
          </Space>
        }
      />

      <Modal
        title="实时行情源设置"
        open={marketSettingsOpen}
        footer={null}
        width={860}
        destroyOnHidden
        onCancel={() => setMarketSettingsOpen(false)}
      >
        <MarketDataConfigPanel />
      </Modal>

      <section className="market-workspace">
        <div className="market-browser">
          <Card
            size="small"
            className="workspace-card"
            title={panelTitle(
              "市场浏览器",
              catalogHint,
            )}
            styles={{ body: { padding: "0 11px 10px" } }}
          >
            <Tabs
              defaultActiveKey="all"
              items={[
                {
                  key: "all",
                  label: catalogInitialLoading
                    ? "全部标的 · 加载中"
                    : `全部标的 ${catalog?.total ?? 0}`,
                  children: (
                    <AllInstrumentsTable
                      loading={catalogInitialLoading}
                      instruments={catalog?.items ?? []}
                      counts={catalog?.counts}
                      watchlistKeys={watchlistKeySet}
                      selected={activeQuote}
                      onSelect={setSelected}
                      onAdd={(item) =>
                        addMut.mutate({
                          symbol: item.symbol,
                          market: item.market,
                          alias: item.name,
                          enabled: true,
                          download_1d: true,
                          download_1m: false,
                        })
                      }
                      onRemove={(item) => removeMut.mutate({ market: item.market, symbol: item.symbol })}
                      adding={addMut.isPending}
                      removing={removeMut.isPending}
                    />
                  ),
                },
                {
                  key: "watchlist",
                  label: `我的股票池 ${watchlistSymbols.length}`,
                  children: (
                    <QuoteTable
                      watchlist={watchlistSymbols}
                      selected={activeQuote}
                      onSelect={setSelected}
                    />
                  ),
                },
              ]}
            />
          </Card>
        </div>

        <div className="market-stage">
          <div className="quote-focus">
            <div className="quote-focus__symbol">
              <small>{market.toUpperCase()} · ACTIVE INSTRUMENT</small>
              <strong>{symbol}</strong>
            </div>
            <div className="quote-focus__price">
              <strong className={change < 0 ? "market-down" : "market-up"}>
                {formatDecimal(activeQuote?.last_price, 2)}
              </strong>
              <span className={change < 0 ? "market-down" : "market-up"}>
                {change > 0 ? "+" : ""}
                {formatPercent(activeQuote?.change_rate)}
              </span>
            </div>
            <div className="quote-focus__meta">
              <span>买一<strong>{formatDecimal(activeQuote?.bid_price, 2)}</strong></span>
              <span>卖一<strong>{formatDecimal(activeQuote?.ask_price, 2)}</strong></span>
              <span>成交量<strong>{formatDecimal(activeQuote?.volume, 0)}</strong></span>
              <span>更新<strong>{formatTime(activeQuote?.quote_time)}</strong></span>
            </div>
          </div>

          <Card
            size="small"
            className="chart-card"
            title={panelTitle(`${symbol} · K 线`, "PRICE ACTION")}
            extra={
              <Select
                size="small"
                value={interval}
                style={{ width: 92 }}
                onChange={setInterval}
                options={[
                  { value: "1m", label: "1 分钟" },
                  { value: "5m", label: "5 分钟" },
                  { value: "1d", label: "日线" },
                ]}
              />
            }
          >
            <KlineChart
              market={market}
              symbol={symbol}
              interval={interval}
              quote={activeQuote}
              onIntegrityChange={setKlineIntegrity}
            />
          </Card>

          <Card
            size="small"
            className="order-ticket-card"
            title={panelTitle("快捷交易票据", "RISK CHECKED ORDER")}
            extra={<ThunderboltOutlined className="muted" />}
          >
            {orderBlockReason ? (
              <Alert
                type="error"
                showIcon
                title="快捷下单已锁定"
                description={orderBlockReason}
                style={{ marginBottom: 10 }}
              />
            ) : null}
            <ManualOrderForm
              symbol={symbol}
              market={market as "stock" | "futures"}
              disabled={Boolean(orderBlockReason)}
            />
          </Card>
        </div>
      </section>
    </div>
  );
}
