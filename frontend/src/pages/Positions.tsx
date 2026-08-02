import { Alert, Card, Col, Row, Space, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import AssetCurveChart from "../components/AssetCurveChart";
import MetricCard from "../components/MetricCard";
import PositionTable, { type PositionRow } from "../components/PositionTable";
import { formatTime } from "../utils/format";

type AccountSnapshot = {
  snapshot_id: string;
  snapshot_time?: string | null;
  total_asset: string;
  available_cash: string;
  frozen_cash: string;
  market_value: string;
  reported_market_value: string;
  other_equity: string;
  pnl: string;
  market_value_delta: string;
  reconciled: boolean;
  positions: PositionRow[];
};

export default function Positions() {
  const snapshot = useQuery({
    queryKey: ["account-snapshot"],
    queryFn: () => api.get<AccountSnapshot>("/account-snapshot"),
    refetchInterval: 15000,
  });
  const latest = snapshot.data;

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        持仓与账户
      </Typography.Title>

      <Space style={{ marginBottom: 12 }} wrap>
        <Tag color={latest?.reconciled ? "green" : "orange"}>
          {latest?.reconciled ? "账户已核平" : "账户待核对"}
        </Tag>
        <Typography.Text type="secondary">
          快照 {latest?.snapshot_id || "-"} ·{" "}
          {formatTime(latest?.snapshot_time, "YYYY-MM-DD HH:mm:ss")}
        </Typography.Text>
      </Space>

      {latest && !latest.reconciled && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="资金快照与持仓推导市值不一致"
          description={`通道市值 ${latest.reported_market_value}，持仓推导市值 ${latest.market_value}，差额 ${latest.market_value_delta}`}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={8} lg={4}>
          <MetricCard title="总资产" value={latest?.total_asset ?? "-"} />
        </Col>
        <Col xs={12} md={8} lg={4}>
          <MetricCard title="可用资金" value={latest?.available_cash ?? "-"} />
        </Col>
        <Col xs={12} md={8} lg={4}>
          <MetricCard title="冻结资金" value={latest?.frozen_cash ?? "-"} />
        </Col>
        <Col xs={12} md={8} lg={4}>
          <MetricCard title="市值" value={latest?.market_value ?? "-"} />
        </Col>
        <Col xs={12} md={8} lg={4}>
          <MetricCard title="其他权益" value={latest?.other_equity ?? "-"} />
        </Col>
        <Col xs={12} md={8} lg={4}>
          <MetricCard title="盈亏" value={latest?.pnl ?? "-"} />
        </Col>
      </Row>

      <Card title="资金曲线" size="small" style={{ marginBottom: 16 }}>
        <AssetCurveChart />
      </Card>

      <Card title="持仓" size="small">
        <PositionTable
          dataSource={latest?.positions ?? []}
          loading={snapshot.isLoading}
        />
      </Card>
    </div>
  );
}
