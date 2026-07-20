import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Dayjs } from "dayjs";
import ReactECharts from "echarts-for-react";
import { api } from "../api/client";
import type { Paged } from "../api/types";

type ReportSummary = {
  report_id: string;
  range_start: string;
  range_end: string;
  model_name: string;
  generated_at: string;
  metrics_summary: {
    has_data?: boolean;
    total_pnl?: string;
    trade_count?: number;
    win_rate?: string;
  };
  metadata?: { feedback?: string };
};

type ReportDetail = ReportSummary & {
  scope: { strategy_ids?: string[]; markets?: string[]; symbols?: string[] };
  metrics: Record<string, unknown>;
  content: string;
  content_format: string;
};

export default function AiReports() {
  const qc = useQueryClient();
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [markets, setMarkets] = useState<string[]>([]);
  const [strategyId, setStrategyId] = useState<string>("");
  const [symbol, setSymbol] = useState<string>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ["ai-reports"],
    queryFn: () => api.get<Paged<ReportSummary>>("/ai/reports?page=1&page_size=50"),
  });

  const detail = useQuery({
    queryKey: ["ai-report", selectedId],
    queryFn: () => api.get<ReportDetail>(`/ai/reports/${selectedId}`),
    enabled: !!selectedId,
  });

  const generate = useMutation({
    mutationFn: () => {
      if (!range?.[0] || !range?.[1]) {
        return Promise.reject(new Error("请选择时间范围"));
      }
      return api.post<{ report_id: string }>("/ai/reports", {
        range_start: range[0].startOf("day").toISOString(),
        range_end: range[1].endOf("day").toISOString(),
        strategy_ids: strategyId ? [strategyId] : [],
        markets,
        symbols: symbol ? [symbol] : [],
      });
    },
    onSuccess: (data) => {
      message.success("报告已生成");
      setSelectedId(data.report_id);
      void qc.invalidateQueries({ queryKey: ["ai-reports"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "生成失败";
      if (msg.includes("请选择")) message.warning(msg);
    },
  });

  const feedback = useMutation({
    mutationFn: (useful: boolean) =>
      api.post(`/ai/reports/${selectedId}/feedback`, { useful }),
    onSuccess: () => {
      message.success("已记录反馈");
      void qc.invalidateQueries({ queryKey: ["ai-report", selectedId] });
      void qc.invalidateQueries({ queryKey: ["ai-reports"] });
    },
  });

  const metrics = (detail.data?.metrics ?? {}) as Record<string, string | number | boolean | undefined>;
  const dailyPnl = (metrics.daily_pnl as Record<string, string> | undefined) ?? {};
  const chartOption = {
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: Object.keys(dailyPnl) },
    yAxis: { type: "value" },
    series: [
      {
        type: "bar",
        data: Object.values(dailyPnl).map((v) => Number(v)),
        name: "日盈亏",
      },
    ],
  };

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        AI 复盘
      </Typography.Title>

      <Alert
        type="warning"
        showIcon
        banner
        style={{ marginBottom: 16 }}
        message="AI 报告仅用于复盘参考，不提供直接下单入口"
        description="可选接入外部 AI 时仅发送聚合指标与必要明细，不发送 SDK 密码等敏感字段。未配置 AI 时使用本地规则化模板。"
      />

      <Card size="small" title="生成报告" style={{ marginBottom: 16 }}>
        <Form layout="inline" style={{ rowGap: 8 }}>
          <Form.Item label="范围" required>
            <DatePicker.RangePicker value={range} onChange={(v) => setRange(v as [Dayjs, Dayjs] | null)} />
          </Form.Item>
          <Form.Item label="市场">
            <Select
              mode="multiple"
              allowClear
              style={{ width: 180 }}
              value={markets}
              onChange={setMarkets}
              options={[
                { value: "stock", label: "股票" },
                { value: "futures", label: "期货" },
              ]}
            />
          </Form.Item>
          <Form.Item label="策略">
            <Input
              allowClear
              style={{ width: 140 }}
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              placeholder="strategy_id"
            />
          </Form.Item>
          <Form.Item label="标的">
            <Input
              allowClear
              style={{ width: 140 }}
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" loading={generate.isPending} onClick={() => generate.mutate()}>
              生成复盘报告
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Row gutter={16}>
        <Col span={10}>
          <Card size="small" title="历史报告">
            <Table
              rowKey="report_id"
              size="small"
              loading={list.isLoading}
              dataSource={list.data?.items ?? []}
              pagination={false}
              onRow={(row) => ({
                onClick: () => setSelectedId(row.report_id),
                style: {
                  cursor: "pointer",
                  background: selectedId === row.report_id ? "#e6f4ff" : undefined,
                },
              })}
              columns={[
                { title: "生成时间", dataIndex: "generated_at", width: 170 },
                { title: "模型", dataIndex: "model_name", width: 100 },
                {
                  title: "盈亏",
                  dataIndex: ["metrics_summary", "total_pnl"],
                  width: 90,
                },
                {
                  title: "笔数",
                  dataIndex: ["metrics_summary", "trade_count"],
                  width: 60,
                },
              ]}
            />
          </Card>
        </Col>
        <Col span={14}>
          <Card
            size="small"
            title="报告详情"
            extra={
              selectedId ? (
                <Space>
                  <Button size="small" onClick={() => feedback.mutate(true)}>
                    标记有用
                  </Button>
                  <Button size="small" onClick={() => feedback.mutate(false)}>
                    标记无用
                  </Button>
                  <Button
                    size="small"
                    onClick={() => {
                      if (detail.data?.content) {
                        void navigator.clipboard.writeText(detail.data.content);
                        message.success("已复制 Markdown");
                      }
                    }}
                  >
                    复制 Markdown
                  </Button>
                </Space>
              ) : null
            }
          >
            {!selectedId ? (
              <Typography.Text type="secondary">请选择或生成一份报告</Typography.Text>
            ) : detail.isLoading ? (
              <Typography.Text>加载中…</Typography.Text>
            ) : detail.data ? (
              <Space direction="vertical" style={{ width: "100%" }} size="middle">
                <Row gutter={12}>
                  <Col span={6}>
                    <Statistic title="总盈亏" value={String(metrics.total_pnl ?? "-")} />
                  </Col>
                  <Col span={6}>
                    <Statistic title="胜率" value={String(metrics.win_rate ?? "-")} />
                  </Col>
                  <Col span={6}>
                    <Statistic title="盈亏比" value={String(metrics.profit_loss_ratio ?? "-")} />
                  </Col>
                  <Col span={6}>
                    <Statistic title="最大回撤" value={String(metrics.max_drawdown ?? "-")} />
                  </Col>
                </Row>
                {Object.keys(dailyPnl).length > 0 ? (
                  <ReactECharts style={{ height: 220 }} option={chartOption} />
                ) : null}
                <Typography.Paragraph>
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      background: "#fafafa",
                      padding: 12,
                      borderRadius: 6,
                      maxHeight: 480,
                      overflow: "auto",
                      margin: 0,
                    }}
                  >
                    {detail.data.content}
                  </pre>
                </Typography.Paragraph>
                {detail.data.metadata?.feedback ? (
                  <Typography.Text type="secondary">
                    反馈：{detail.data.metadata.feedback}
                  </Typography.Text>
                ) : null}
              </Space>
            ) : (
              <Typography.Text type="secondary">报告不存在</Typography.Text>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
