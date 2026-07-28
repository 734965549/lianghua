import { useMemo, useState } from "react";
import {
  Button,
  DatePicker,
  Form,
  Input,
  Select,
  Space,
  Table,
  Tabs,
  Typography,
  message,
} from "antd";
import { useQuery } from "@tanstack/react-query";
import { type Dayjs } from "dayjs";
import { api } from "../api/client";
import type { Paged } from "../api/types";
import TradeChainDrawer, {
  type TradeChainData,
  type TradeChainOrder,
  type TradeChainTrade,
} from "../components/TradeChainDrawer";

type OrderRow = TradeChainOrder;
type TradeRow = TradeChainTrade;

type FilterState = {
  range: [Dayjs, Dayjs] | null;
  market?: string;
  symbol?: string;
  strategy_id?: string;
  status?: string;
};

function buildQuery(f: FilterState, page: number, pageSize: number) {
  const qs = new URLSearchParams();
  qs.set("page", String(page));
  qs.set("page_size", String(pageSize));
  if (f.market) qs.set("market", f.market);
  if (f.symbol) qs.set("symbol", f.symbol);
  if (f.strategy_id) qs.set("strategy_id", f.strategy_id);
  if (f.status) qs.set("status", f.status);
  if (f.range?.[0]) qs.set("start", f.range[0].startOf("day").toISOString());
  if (f.range?.[1]) qs.set("end", f.range[1].endOf("day").toISOString());
  return qs.toString();
}

async function downloadCsv(path: string, filename: string) {
  const res = await fetch(`/api${path}`, {
    headers: { Accept: "text/csv" },
  });
  if (!res.ok) {
    message.error("导出失败");
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function History() {
  const [filters, setFilters] = useState<FilterState>({ range: null });
  const [applied, setApplied] = useState<FilterState>({ range: null });
  const [page, setPage] = useState(1);
  const [chainId, setChainId] = useState<string | null>(null);

  const orderQs = useMemo(() => buildQuery(applied, page, 20), [applied, page]);
  const tradeQs = useMemo(() => buildQuery(applied, page, 20), [applied, page]);

  const orders = useQuery({
    queryKey: ["history-orders", orderQs],
    queryFn: () => api.get<Paged<OrderRow>>(`/history/orders?${orderQs}`),
  });

  const trades = useQuery({
    queryKey: ["history-trades", tradeQs],
    queryFn: () => api.get<Paged<TradeRow>>(`/history/trades?${tradeQs}`),
  });

  const chain = useQuery({
    queryKey: ["history-chain", chainId],
    queryFn: () => api.get<TradeChainData>(`/history/orders/${encodeURIComponent(chainId!)}/chain`),
    enabled: !!chainId,
  });

  const onSearch = () => {
    setPage(1);
    setApplied({ ...filters });
  };

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        历史交易
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        按日期、标的、策略、市场、状态筛选；支持 CSV 导出与单笔交易链路查看。
      </Typography.Paragraph>

      <Form layout="inline" style={{ marginBottom: 16, rowGap: 8 }}>
        <Form.Item label="日期">
          <DatePicker.RangePicker
            value={filters.range}
            onChange={(v) => setFilters((s) => ({ ...s, range: v as [Dayjs, Dayjs] | null }))}
          />
        </Form.Item>
        <Form.Item label="市场">
          <Select
            allowClear
            style={{ width: 120 }}
            value={filters.market}
            onChange={(v) => setFilters((s) => ({ ...s, market: v }))}
            options={[
              { value: "stock", label: "股票" },
              { value: "futures", label: "期货" },
            ]}
          />
        </Form.Item>
        <Form.Item label="标的">
          <Input
            allowClear
            style={{ width: 140 }}
            value={filters.symbol}
            onChange={(e) => setFilters((s) => ({ ...s, symbol: e.target.value || undefined }))}
          />
        </Form.Item>
        <Form.Item label="策略">
          <Input
            allowClear
            style={{ width: 140 }}
            value={filters.strategy_id}
            onChange={(e) => setFilters((s) => ({ ...s, strategy_id: e.target.value || undefined }))}
          />
        </Form.Item>
        <Form.Item label="状态">
          <Select
            allowClear
            style={{ width: 140 }}
            value={filters.status}
            onChange={(v) => setFilters((s) => ({ ...s, status: v }))}
            options={[
              "filled",
              "cancelled",
              "failed",
              "submitted",
              "partially_filled",
              "risk_rejected",
              "unknown",
            ].map((v) => ({ value: v, label: v }))}
          />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" onClick={onSearch}>
              查询
            </Button>
            <Button
              onClick={() =>
                void downloadCsv(`/history/orders?${buildQuery(applied, 1, 20)}`, "history_orders.csv")
              }
            >
              导出委托 CSV
            </Button>
            <Button
              onClick={() =>
                void downloadCsv(`/history/trades?${buildQuery(applied, 1, 20)}`, "history_trades.csv")
              }
            >
              导出成交 CSV
            </Button>
          </Space>
        </Form.Item>
      </Form>

      <Tabs
        items={[
          {
            key: "orders",
            label: "委托",
            children: (
              <Table
                rowKey="client_order_id"
                size="small"
                loading={orders.isLoading}
                dataSource={orders.data?.items ?? []}
                pagination={{
                  current: page,
                  pageSize: 20,
                  total: orders.data?.total ?? 0,
                  onChange: setPage,
                }}
                columns={[
                  { title: "时间", dataIndex: "created_at", width: 180 },
                  { title: "标的", dataIndex: "symbol", width: 110 },
                  { title: "市场", dataIndex: "market", width: 80 },
                  { title: "方向", dataIndex: "side", width: 70 },
                  { title: "动作", dataIndex: "action", width: 70 },
                  { title: "价格", dataIndex: "price", width: 90 },
                  { title: "数量", dataIndex: "quantity", width: 90 },
                  { title: "成交量", dataIndex: "filled_quantity", width: 90 },
                  { title: "状态", dataIndex: "status", width: 110 },
                  { title: "策略", dataIndex: "strategy_id", width: 100 },
                  {
                    title: "操作",
                    width: 100,
                    render: (_, row) => (
                      <Button type="link" size="small" onClick={() => setChainId(row.client_order_id)}>
                        链路
                      </Button>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "trades",
            label: "成交",
            children: (
              <Table
                rowKey="sdk_trade_id"
                size="small"
                loading={trades.isLoading}
                dataSource={trades.data?.items ?? []}
                pagination={{
                  current: page,
                  pageSize: 20,
                  total: trades.data?.total ?? 0,
                  onChange: setPage,
                }}
                columns={[
                  { title: "成交时间", dataIndex: "trade_time", width: 180 },
                  { title: "标的", dataIndex: "symbol", width: 110 },
                  { title: "方向", dataIndex: "side", width: 70 },
                  { title: "价格", dataIndex: "price", width: 90 },
                  { title: "数量", dataIndex: "quantity", width: 90 },
                  { title: "手续费", dataIndex: "fee", width: 90 },
                  { title: "委托号", dataIndex: "client_order_id", width: 180 },
                  { title: "策略", dataIndex: "strategy_id", width: 100 },
                  {
                    title: "操作",
                    width: 100,
                    render: (_, row) => (
                      <Button type="link" size="small" onClick={() => setChainId(row.client_order_id)}>
                        链路
                      </Button>
                    ),
                  },
                ]}
              />
            ),
          },
        ]}
      />

      <TradeChainDrawer
        open={!!chainId}
        chainId={chainId}
        data={chain.data}
        loading={chain.isLoading}
        onClose={() => setChainId(null)}
      />
    </div>
  );
}
