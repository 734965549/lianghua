import { Col, Row, Table, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { DashboardData, HealthData } from "../api/types";
import MetricCard from "../components/MetricCard";
import { SYSTEM_STATUS_LABEL, connColor } from "../utils/status";

export default function Dashboard() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthData>("/health"),
    refetchInterval: 10000,
  });
  const dash = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardData>("/dashboard"),
    refetchInterval: 10000,
  });

  const h = health.data;
  const d = dash.data;

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        仪表盘
      </Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <MetricCard
            title="API"
            value={h?.api ?? "-"}
            status={connColor(h?.api === "ok" ? "connected" : "disconnected") as "success" | "error"}
          />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard
            title="数据库"
            value={h?.database ?? "-"}
            status={connColor(h?.database ?? "") as "success" | "error" | "warning"}
          />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard
            title="股票 SDK"
            value={h?.stock_sdk ?? "-"}
            status={connColor(h?.stock_sdk ?? "") as "success" | "error" | "warning"}
          />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard
            title="期货 SDK"
            value={h?.futures_sdk ?? "-"}
            status={connColor(h?.futures_sdk ?? "") as "success" | "error" | "warning"}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <MetricCard
            title="系统状态"
            value={SYSTEM_STATUS_LABEL[d?.system_status ?? ""] ?? d?.system_status ?? "-"}
          />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard title="当日盈亏" value={d?.daily_pnl ?? "0"} />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard title="持仓市值" value={d?.position_value ?? "0"} />
        </Col>
        <Col xs={12} md={6}>
          <MetricCard title="可用资金" value={d?.available_cash ?? "0"} />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Typography.Title level={5}>最新告警</Typography.Title>
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            loading={dash.isLoading}
            dataSource={d?.latest_alerts ?? []}
            columns={[
              { title: "时间", dataIndex: "event_time", width: 180 },
              { title: "级别", dataIndex: "severity", width: 90 },
              { title: "模块", dataIndex: "module", width: 100 },
              { title: "消息", dataIndex: "message" },
            ]}
          />
        </Col>
        <Col xs={24} md={12}>
          <Typography.Title level={5}>运行摘要</Typography.Title>
          <Row gutter={[12, 12]}>
            <Col span={12}>
              <MetricCard title="当日成交笔数" value={d?.daily_trade_count ?? 0} />
            </Col>
            <Col span={12}>
              <MetricCard title="风控拒绝" value={d?.risk_reject_count ?? 0} />
            </Col>
            <Col span={12}>
              <MetricCard
                title="熔断"
                value={d?.breaker_active ? "是" : "否"}
                status={d?.breaker_active ? "error" : "success"}
              />
            </Col>
            <Col span={12}>
              <MetricCard title="运行中策略" value={d?.running_strategies ?? 0} />
            </Col>
          </Row>
        </Col>
      </Row>
    </div>
  );
}
