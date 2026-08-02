import { useEffect, useMemo, useState } from "react";
import { Button, Input, Segmented, Space, Table, Tag } from "antd";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  Instrument,
  QuoteHealthReport,
  QuoteHealthState,
  QuoteSnapshot,
} from "../api/types";
import { useWebSocket } from "../hooks/useWebSocket";
import {
  formatChangeColor,
  formatDecimal,
  formatPercent,
  formatTime,
} from "../utils/format";

const PAGE_SIZE = 20;

const HEALTH_META: Record<
  QuoteHealthState,
  { label: string; color?: string; rowTone?: string }
> = {
  healthy: { label: "实时", color: "success" },
  market_closed: { label: "休市" },
  feed_stale: {
    label: "停更",
    color: "warning",
    rowTone: "rgba(255,181,71,.035)",
  },
  source_disconnected: {
    label: "行情源断线",
    color: "error",
    rowTone: "rgba(255,77,79,.055)",
  },
  subscription_disconnected: {
    label: "订阅断线",
    color: "error",
    rowTone: "rgba(255,77,79,.055)",
  },
  not_monitored: { label: "待监测" },
};

type Props = {
  instruments: Instrument[];
  counts?: { stock: number; futures: number };
  watchlistKeys: Set<string>;
  selected?: QuoteSnapshot | null;
  onSelect?: (quote: QuoteSnapshot) => void;
  onAdd?: (item: Instrument) => void;
  onRemove?: (item: Instrument) => void;
  adding?: boolean;
  removing?: boolean;
  loading?: boolean;
};

export default function AllInstrumentsTable({
  instruments,
  counts,
  watchlistKeys,
  selected,
  onSelect,
  onAdd,
  onRemove,
  adding,
  removing,
  loading,
}: Props) {
  const [search, setSearch] = useState("");
  const [marketFilter, setMarketFilter] = useState<"all" | "stock" | "futures">(
    "all",
  );
  const [page, setPage] = useState(1);
  const qc = useQueryClient();

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return instruments.filter(
      (i) =>
        (marketFilter === "all" || i.market === marketFilter) &&
        (!q ||
          i.symbol.toLowerCase().includes(q) ||
          i.name.toLowerCase().includes(q) ||
          i.exchange.toLowerCase().includes(q))
    );
  }, [instruments, marketFilter, search]);

  const paged = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, page]);

  useEffect(() => {
    if (!paged.length) return;
    const byMarket = new Map<string, string[]>();
    paged.forEach((item) => {
      const symbols = byMarket.get(item.market) ?? [];
      symbols.push(item.symbol);
      byMarket.set(item.market, symbols);
    });
    const controllers: AbortController[] = [];
    byMarket.forEach((symbols, market) => {
      const controller = new AbortController();
      controllers.push(controller);
      api
        .post(
          "/quotes/subscriptions",
          {
            market,
            symbols,
            subscriber_id: "market-browser-visible-page",
          },
          { signal: controller.signal, silent: true },
        )
        .catch(() => undefined);
    });
    return () => {
      controllers.forEach((controller) => controller.abort());
      byMarket.forEach((symbols, market) => {
        api
          .del("/quotes/subscriptions", {
            body: JSON.stringify({
              market,
              symbols,
              subscriber_id: "market-browser-visible-page",
            }),
            silent: true,
          })
          .catch(() => undefined);
      });
    };
  }, [paged]);

  useWebSocket("quote.update", (raw) => {
    const quote = raw as QuoteSnapshot;
    qc.setQueryData(["quote", quote.market, quote.symbol], quote);
  });

  const quoteQueries = useQueries({
    queries: paged.map((i) => ({
      queryKey: ["quote", i.market, i.symbol],
      queryFn: async () => {
        try {
          return await api.get<QuoteSnapshot>(
            `/quotes/${i.market}/${i.symbol}`,
            { silent: true },
          );
        } catch {
          return null;
        }
      },
      refetchInterval: 15_000,
      staleTime: 5_000,
    })),
  });

  const quoteMap = useMemo(() => {
    const map = new Map<string, QuoteSnapshot>();
    paged.forEach((i, idx) => {
      const q = quoteQueries[idx]?.data;
      if (q) map.set(`${i.market}:${i.symbol}`, q);
    });
    return map;
  }, [paged, quoteQueries]);

  const healthTargets = useMemo(
    () => paged.map((item) => `${item.market}:${item.symbol}`).join(","),
    [paged],
  );

  const healthQuery = useQuery({
    queryKey: ["quotes", "health", "visible", healthTargets],
    queryFn: () =>
      api.get<QuoteHealthReport>(
        `/quotes/health?targets=${encodeURIComponent(healthTargets)}`,
        { silent: true },
      ),
    enabled: Boolean(healthTargets),
    refetchInterval: 5_000,
    retry: 1,
  });

  const healthByKey = useMemo(
    () =>
      new Map(
        (healthQuery.data?.items ?? []).map((item) => [
          `${item.market}:${item.symbol}`,
          item.state,
        ]),
      ),
    [healthQuery.data],
  );

  const rows = useMemo(
    () =>
      paged.map((i) => {
        const q = quoteMap.get(`${i.market}:${i.symbol}`);
        const healthState = (healthByKey.get(`${i.market}:${i.symbol}`) ??
          "not_monitored") as QuoteHealthState;
        return {
          instrument: i,
          quote: q,
          healthState,
        };
      }),
    [healthByKey, paged, quoteMap],
  );

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Space className="instrument-browser-toolbar" wrap>
        <Segmented
          value={marketFilter}
          onChange={(value) => {
            setMarketFilter(value as "all" | "stock" | "futures");
            setPage(1);
          }}
          options={[
            { value: "all", label: `全部 ${instruments.length}` },
            { value: "stock", label: `股票 ${counts?.stock ?? 0}` },
            { value: "futures", label: `期货 ${counts?.futures ?? 0}` },
          ]}
        />
        <Input.Search
          placeholder="搜索代码、名称或交易所"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          allowClear
        />
      </Space>
      <Table
        loading={loading}
        size="small"
        rowKey={(r) => `${r.instrument.market}:${r.instrument.symbol}`}
        dataSource={rows}
        style={{ flex: 1, minHeight: 0 }}
        scroll={{ x: "max-content", y: "100%" }}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: filtered.length,
          onChange: setPage,
          simple: true,
          style: { marginBottom: 0 },
        }}
        onRow={(record) => ({
          onClick: () => record.quote && onSelect?.(record.quote),
          style: {
            cursor: record.quote ? "pointer" : "default",
            background:
              selected?.symbol === record.instrument.symbol &&
              selected?.market === record.instrument.market
                ? "#1b2a39"
                : HEALTH_META[record.healthState].rowTone,
          },
        })}
        columns={[
          {
            title: "标的",
            render: (_: unknown, r) => (
              <span>
                {r.instrument.symbol}{" "}
                <Tag>{r.instrument.market === "stock" ? "股票" : "期货"}</Tag>
                {r.healthState !== "healthy" && (
                  <Tag color={HEALTH_META[r.healthState].color}>
                    {HEALTH_META[r.healthState].label}
                  </Tag>
                )}
              </span>
            ),
          },
          {
            title: "名称",
            dataIndex: ["instrument", "name"],
          },
          {
            title: "最新价",
            align: "right",
            render: (_: unknown, r) =>
              r.quote ? formatDecimal(r.quote.last_price, 2) : "-",
          },
          {
            title: "涨跌幅",
            align: "right",
            render: (_: unknown, r) =>
              r.quote ? (
                <span style={{ color: formatChangeColor(r.quote.change_rate) }}>
                  {formatPercent(r.quote.change_rate)}
                </span>
              ) : (
                "-"
              ),
          },
          {
            title: "成交量",
            align: "right",
            render: (_: unknown, r) =>
              r.quote ? formatDecimal(r.quote.volume, 0) : "-",
          },
          {
            title: "更新时间",
            width: 170,
            render: (_: unknown, r) =>
              r.quote ? formatTime(r.quote.quote_time) : "-",
          },
          {
            title: "操作",
            align: "center",
            render: (_: unknown, r) => {
              const key = `${r.instrument.market}:${r.instrument.symbol}`;
              const added = watchlistKeys.has(key);
              return added ? (
                <Button
                  size="small"
                  danger
                  loading={removing}
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove?.(r.instrument);
                  }}
                >
                  移除
                </Button>
              ) : (
                <Button
                  size="small"
                  loading={adding}
                  onClick={(e) => {
                    e.stopPropagation();
                    onAdd?.(r.instrument);
                  }}
                >
                  加入自选
                </Button>
              );
            },
          },
        ]}
      />
    </div>
  );
}
