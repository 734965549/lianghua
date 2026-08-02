import { Alert, Descriptions, Drawer, Space, Table, Typography } from "antd";
import type { ReactNode } from "react";
import { formatDecimal, formatTime } from "../utils/format";
import EnumLabel from "./EnumLabel";

export type HistoricalDataQuality = {
  classification: "historical_test_data" | "simulated_data" | "production_data";
  isolated: boolean;
  issues: string[];
  label: string;
};

export type TradeChainOrder = {
  client_order_id: string;
  sdk_order_id?: string | null;
  symbol: string;
  market: string;
  side: string;
  action: string;
  price: string;
  quantity: string;
  filled_quantity: string;
  status: string;
  strategy_id?: string | null;
  created_at: string;
  last_event_at?: string | null;
  data_quality?: HistoricalDataQuality;
};

export type TradeChainTrade = {
  sdk_trade_id: string;
  client_order_id: string;
  symbol: string;
  market: string;
  side: string;
  price: string;
  quantity: string;
  fee: string;
  trade_time: string;
  strategy_id?: string | null;
  data_quality?: HistoricalDataQuality;
};

export type TradeChainData = {
  order: TradeChainOrder;
  signal: Record<string, unknown> | null;
  risk_checks: Array<{
    id: string;
    result: string;
    rule_code: string;
    reason: string;
    checked_at: string;
  }>;
  trades: TradeChainTrade[];
  data_quality?: HistoricalDataQuality;
  audit_logs: Array<{
    id: number;
    event_time: string;
    action: string;
    module: string;
    result: string;
    reason: string;
  }>;
};

type Props = {
  open: boolean;
  onClose: () => void;
  chainId?: string | null;
  data?: TradeChainData | null;
  loading?: boolean;
  width?: number;
};

function formatChainValue(key: string, value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (key.endsWith("_time") || key.endsWith("_at")) {
    return formatTime(String(value), "MM-DD HH:mm:ss");
  }
  if (["price", "quantity", "filled_quantity", "fee"].includes(key)) {
    return formatDecimal(String(value), key === "quantity" || key === "filled_quantity" ? 0 : 2);
  }
  if (key === "data_quality") {
    return "";
  }
  if (key === "market") return <EnumLabel value={String(value)} kind="market" />;
  if (key === "side") return <EnumLabel value={String(value)} kind="side" />;
  if (key === "action") return <EnumLabel value={String(value)} kind="action" />;
  if (key === "status") return <EnumLabel value={String(value)} kind="status" />;
  if (key === "result") return <EnumLabel value={String(value)} kind="risk" />;
  return String(value ?? "");
}

export default function TradeChainDrawer({
  open,
  onClose,
  chainId,
  data,
  loading,
  width = 640,
}: Props) {
  return (
    <Drawer
      title={`交易链路 ${chainId ?? ""}`}
      size={width > 480 ? "large" : "default"}
      open={open}
      onClose={onClose}
    >
      {loading ? (
        <Typography.Text>加载中…</Typography.Text>
      ) : data ? (
        <Space orientation="vertical" style={{ width: "100%" }} size="large">
          {data.data_quality && data.data_quality.classification !== "production_data" ? (
            <Alert
              type={data.data_quality.isolated ? "error" : "warning"}
              showIcon
              title={data.data_quality.label}
              description={
                data.data_quality.isolated
                  ? `该链路已与可信交易记录隔离：${data.data_quality.issues.join("；")}`
                  : "该链路来自模拟交易通道，不代表真实成交。"
              }
            />
          ) : null}
          <div>
            <Typography.Title level={5}>信号</Typography.Title>
            {data.signal ? (
              <Descriptions size="small" column={1} bordered>
                {Object.entries(data.signal).map(([k, v]) => (
                  <Descriptions.Item key={k} label={k}>
                    {formatChainValue(k, v)}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Typography.Text type="secondary">无关联信号</Typography.Text>
            )}
          </div>
          <div>
            <Typography.Title level={5}>风控</Typography.Title>
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              dataSource={data.risk_checks}
              columns={[
                {
                  title: "时间",
                  dataIndex: "checked_at",
                  render: (value: string) => formatTime(value, "MM-DD HH:mm:ss"),
                },
                {
                  title: "结果",
                  dataIndex: "result",
                  width: 90,
                  render: (value: string) => <EnumLabel value={value} kind="risk" />,
                },
                { title: "规则", dataIndex: "rule_code", width: 140 },
                { title: "原因", dataIndex: "reason" },
              ]}
            />
          </div>
          <div>
            <Typography.Title level={5}>委托</Typography.Title>
            <Descriptions size="small" column={1} bordered>
              {Object.entries(data.order).filter(([k]) => k !== "data_quality").map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>
                  {formatChainValue(k, v)}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </div>
          <div>
            <Typography.Title level={5}>成交</Typography.Title>
            <Table
              size="small"
              pagination={false}
              rowKey="sdk_trade_id"
              dataSource={data.trades}
              columns={[
                {
                  title: "时间",
                  dataIndex: "trade_time",
                  render: (value: string) => formatTime(value, "MM-DD HH:mm:ss"),
                },
                { title: "价格", dataIndex: "price", width: 90, render: (v) => formatDecimal(v, 2) },
                { title: "数量", dataIndex: "quantity", width: 90, render: (v) => formatDecimal(v, 0) },
                { title: "手续费", dataIndex: "fee", width: 90, render: (v) => formatDecimal(v, 2) },
              ]}
            />
          </div>
          <div>
            <Typography.Title level={5}>审计</Typography.Title>
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              dataSource={data.audit_logs}
              columns={[
                {
                  title: "时间",
                  dataIndex: "event_time",
                  render: (value: string) => formatTime(value, "MM-DD HH:mm:ss"),
                },
                { title: "动作", dataIndex: "action", width: 120 },
                {
                  title: "结果",
                  dataIndex: "result",
                  width: 90,
                  render: (value: string) => <EnumLabel value={value} kind="risk" />,
                },
                { title: "原因", dataIndex: "reason" },
              ]}
            />
          </div>
        </Space>
      ) : (
        <Typography.Text type="secondary">无数据</Typography.Text>
      )}
    </Drawer>
  );
}
