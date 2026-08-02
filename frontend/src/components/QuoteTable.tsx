import { useEffect, useMemo, useState } from "react";
import { Alert, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  QuoteHealthReport,
  QuoteHealthState,
  QuoteSnapshot,
} from "../api/types";
import { useWebSocket } from "../hooks/useWebSocket";
import EnumLabel from "./EnumLabel";
import {
  formatChangeColor,
  formatDecimal,
  formatPercent,
  formatTime,
} from "../utils/format";

type Props = {
  watchlist?: { market: string; symbol: string }[];
  selected?: QuoteSnapshot | null;
  onSelect?: (quote: QuoteSnapshot) => void;
};

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

export default function QuoteTable({ watchlist, selected, onSelect }: Props) {
  const [quotes, setQuotes] = useState<QuoteSnapshot[]>([]);

  const { data, isLoading } = useQuery({
    queryKey: ["quotes", watchlist?.map((w) => `${w.market}:${w.symbol}`).join(",")],
    queryFn: async () => {
      if (watchlist?.length) {
        const results: QuoteSnapshot[] = [];
        for (const w of watchlist) {
          try {
            const q = await api.get<QuoteSnapshot>(
              `/quotes/${w.market}/${w.symbol}`,
              { silent: true },
            );
            results.push(q);
          } catch {
            /* 暂无行情 */
          }
        }
        return results;
      }
      return api.get<QuoteSnapshot[]>("/quotes");
    },
    refetchInterval: 15000,
  });

  const healthTargets = useMemo(
    () =>
      (watchlist?.length ? watchlist : quotes)
        .map((item) => `${item.market}:${item.symbol}`)
        .join(","),
    [quotes, watchlist],
  );

  const healthQuery = useQuery({
    queryKey: ["quotes", "health", healthTargets],
    queryFn: () =>
      api.get<QuoteHealthReport>(
        `/quotes/health?targets=${encodeURIComponent(healthTargets)}`,
        { silent: true },
      ),
    enabled: Boolean(healthTargets),
    refetchInterval: 5000,
    retry: 1,
  });

  useEffect(() => {
    if (data) setQuotes(data);
  }, [data]);

  useWebSocket("quote.update", (raw) => {
    const q = raw as QuoteSnapshot;
    setQuotes((prev) => {
      const idx = prev.findIndex((x) => x.symbol === q.symbol && x.market === q.market);
      if (idx < 0) return [...prev, q];
      const next = [...prev];
      next[idx] = { ...next[idx], ...q };
      return next;
    });
  });

  const healthByKey = useMemo(
    () =>
      new Map(
        (healthQuery.data?.items ?? []).map((item) => [
          `${item.market}:${item.symbol}`,
          item,
        ]),
      ),
    [healthQuery.data],
  );

  const rows = useMemo(
    () =>
      quotes.map((quote) => {
        const health = healthByKey.get(`${quote.market}:${quote.symbol}`);
        return {
          ...quote,
          healthState: (health?.state ?? "not_monitored") as QuoteHealthState,
          healthReason: health?.reason,
          ageSeconds: health?.age_seconds,
        };
      }),
    [healthByKey, quotes],
  );

  const disconnectedCount = rows.filter((row) =>
    ["source_disconnected", "subscription_disconnected"].includes(row.healthState),
  ).length;
  const staleCount = rows.filter((row) => row.healthState === "feed_stale").length;
  const closedCount = rows.filter((row) => row.healthState === "market_closed").length;

  const healthAlert = healthQuery.isError
    ? { type: "warning" as const, title: "暂时无法读取后端行情健康状态" }
    : disconnectedCount > 0
      ? { type: "error" as const, title: `${disconnectedCount} 个标的行情链路已断开` }
      : staleCount > 0
        ? {
            type: "warning" as const,
            title: `${staleCount} 个标的在交易时段内行情停更（>${healthQuery.data?.timeout_seconds ?? 10}s）`,
          }
        : closedCount > 0
          ? {
              type: "info" as const,
              title: `${closedCount} 个标的当前休市，正在展示最后有效行情`,
            }
          : null;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {healthAlert && (
        <Alert
          type={healthAlert.type}
          showIcon
          style={{ marginBottom: 12, flexShrink: 0 }}
          title={healthAlert.title}
        />
      )}
      <Table
        size="small"
        rowKey={(r) => `${r.market}:${r.symbol}`}
        loading={isLoading}
        dataSource={rows}
        style={{ flex: 1, minHeight: 0 }}
        scroll={{ x: "max-content", y: "100%" }}
        pagination={false}
        onRow={(record) => ({
          onClick: () => onSelect?.(record),
          style: {
            cursor: "pointer",
            background:
              selected?.symbol === record.symbol && selected?.market === record.market
                ? "#1b2a39"
                : HEALTH_META[record.healthState].rowTone,
          },
        })}
        columns={[
          {
            title: "标的",
            dataIndex: "symbol",
            render: (v: string, r) => (
              <span>
                {v}{" "}
                <Tag><EnumLabel value={r.market} kind="market" /></Tag>
                {r.healthState !== "healthy" && (
                  <Tag color={HEALTH_META[r.healthState].color}>
                    {HEALTH_META[r.healthState].label}
                  </Tag>
                )}
              </span>
            ),
          },
          {
            title: "最新价",
            dataIndex: "last_price",
            align: "right",
            render: (v: string) => formatDecimal(v, 2),
          },
          {
            title: "涨跌幅",
            dataIndex: "change_rate",
            align: "right",
            render: (v: string) => (
              <span style={{ color: formatChangeColor(v) }}>{formatPercent(v)}</span>
            ),
          },
          {
            title: "成交量",
            dataIndex: "volume",
            align: "right",
            render: (v: string) => formatDecimal(v, 0),
          },
          {
            title: "更新时间",
            dataIndex: "quote_time",
            width: 170,
            render: (v: string) => formatTime(v),
          },
        ]}
      />
    </div>
  );
}
