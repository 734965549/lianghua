import { Card, Col, Row, Table, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import AssetCurveChart from "../components/AssetCurveChart";
import MetricCard from "../components/MetricCard";

type PositionRow = {
  id: string;
  symbol: string;
  market: string;
  direction: string;
  quantity: string;
  available_quantity: string;
  avg_cost: string;
  market_value: string;
  pnl: string;
  snapshot_time: string;
};

type AssetRow = {
  id: string;
  total_asset: string;
  available_cash: string;
  frozen_cash: string;
  market_value: string;
  pnl: string;
  snapshot_time: string;
};

export default function Positions() {
  const positions = useQuery({
    queryKey: ["positions"],
    queryFn: () => api.get<{ items: PositionRow[] }>("/positions"),
    refetchInterval: 15000,
  });
  const assets = useQuery({
    queryKey: ["assets"],
    queryFn: () => api.get<{ items: AssetRow[] }>("/assets"),
    refetchInterval: 15000,
  });

  const latest = assets.data?.items?.[0];

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        持仓与账户
      </Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <MetricCard title="总资产" value={latest?.total_asset ?? "-"} />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard title="可用资金" value={latest?.available_cash ?? "-"} />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard title="市值" value={latest?.market_value ?? "-"} />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard title="盈亏" value={latest?.pnl ?? "-"} />
        </Col>
      </Row>

      <Card title="资金曲线" size="small" style={{ marginBottom: 16 }}>
        <AssetCurveChart />
      </Card>

      <Card title="持仓" size="small">
        <Table
          rowKey="id"
          size="small"
          loading={positions.isLoading}
          dataSource={positions.data?.items ?? []}
          pagination={false}
          locale={{ emptyText: "暂无持仓（Mock 默认可为空，资金快照仍会同步）" }}
          columns={[
            { title: "标的", dataIndex: "symbol" },
            { title: "市场", dataIndex: "market", width: 90 },
            { title: "方向", dataIndex: "direction", width: 80 },
            { title: "数量", dataIndex: "quantity", width: 90 },
            { title: "可用", dataIndex: "available_quantity", width: 90 },
            { title: "成本", dataIndex: "avg_cost", width: 100 },
            { title: "市值", dataIndex: "market_value", width: 110 },
            { title: "盈亏", dataIndex: "pnl", width: 100 },
            { title: "快照时间", dataIndex: "snapshot_time", width: 180 },
          ]}
        />
      </Card>
    </div>
  );
}
