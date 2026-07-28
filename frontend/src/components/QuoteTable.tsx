import { useEffect, useMemo, useState } from "react";
import { Alert, Table, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { api } from "../api/client";
import type { QuoteSnapshot } from "../api/types";
import { useWebSocket } from "../hooks/useWebSocket";
import {
  formatChangeColor,
  formatDecimal,
  formatPercent,
  formatTime,
} from "../utils/format";

const STALE_MS = 10_000;

type Props = {
  watchlist?: { market: string; symbol: string }[];
  selected?: QuoteSnapshot | null;
  onSelect?: (quote: QuoteSnapshot) => void;
};

function isStale(quoteTime: string): boolean {
  return Date.now() - dayjs(quoteTime).valueOf() > STALE_MS;
}

export default function QuoteTable({ watchlist, selected, onSelect }: Props) {
  const [quotes, setQuotes] = useState<QuoteSnapshot[]>([]);
  const [tick, setTick] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["quotes", watchlist?.map((w) => `${w.market}:${w.symbol}`).join(",")],
    queryFn: async () => {
      if (watchlist?.length) {
        const results: QuoteSnapshot[] = [];
        for (const w of watchlist) {
          try {
            const q = await api.get<QuoteSnapshot>(`/quotes/${w.market}/${w.symbol}`);
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

  useEffect(() => {
    const timer = window.setInterval(() => setTick((t) => t + 1), 2000);
    return () => clearInterval(timer);
  }, []);

  const rows = useMemo(
    () =>
      quotes.map((q) => ({
        ...q,
        stale: isStale(q.quote_time),
      })),
    // tick 驱动停更着色刷新
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [quotes, tick]
  );

  const staleCount = rows.filter((r) => r.stale).length;

  return (
    <div>
      {staleCount > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`${staleCount} 个标的行情停更（>${STALE_MS / 1000}s 无更新）`}
        />
      )}
      <Table
        size="small"
        rowKey={(r) => `${r.market}:${r.symbol}`}
        loading={isLoading}
        dataSource={rows}
        pagination={false}
        onRow={(record) => ({
          onClick: () => onSelect?.(record),
          style: {
            cursor: "pointer",
            background:
              selected?.symbol === record.symbol && selected?.market === record.market
                ? "#e6f4ff"
                : record.stale
                  ? "#fffbe6"
                  : undefined,
          },
        })}
        columns={[
          {
            title: "标的",
            dataIndex: "symbol",
            render: (v: string, r) => (
              <span>
                {v}{" "}
                <Tag>{r.market}</Tag>
                {r.stale && <Tag color="warning">停更</Tag>}
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
