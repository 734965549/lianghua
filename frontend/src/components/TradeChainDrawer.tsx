import { Descriptions, Drawer, Space, Table, Typography } from "antd";

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

export default function TradeChainDrawer({
  open,
  onClose,
  chainId,
  data,
  loading,
  width = 640,
}: Props) {
  return (
    <Drawer title={`交易链路 ${chainId ?? ""}`} width={width} open={open} onClose={onClose}>
      {loading ? (
        <Typography.Text>加载中…</Typography.Text>
      ) : data ? (
        <Space direction="vertical" style={{ width: "100%" }} size="large">
          <div>
            <Typography.Title level={5}>信号</Typography.Title>
            {data.signal ? (
              <Descriptions size="small" column={1} bordered>
                {Object.entries(data.signal).map(([k, v]) => (
                  <Descriptions.Item key={k} label={k}>
                    {String(v ?? "")}
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
                { title: "时间", dataIndex: "checked_at" },
                { title: "结果", dataIndex: "result", width: 90 },
                { title: "规则", dataIndex: "rule_code", width: 140 },
                { title: "原因", dataIndex: "reason" },
              ]}
            />
          </div>
          <div>
            <Typography.Title level={5}>委托</Typography.Title>
            <Descriptions size="small" column={1} bordered>
              {Object.entries(data.order).map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>
                  {String(v ?? "")}
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
                { title: "时间", dataIndex: "trade_time" },
                { title: "价格", dataIndex: "price", width: 90 },
                { title: "数量", dataIndex: "quantity", width: 90 },
                { title: "手续费", dataIndex: "fee", width: 90 },
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
                { title: "时间", dataIndex: "event_time" },
                { title: "动作", dataIndex: "action", width: 120 },
                { title: "结果", dataIndex: "result", width: 90 },
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
