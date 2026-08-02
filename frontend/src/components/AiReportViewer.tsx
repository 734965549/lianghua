import { Button, Card, Col, Row, Space, Statistic, Typography } from "antd";
import ReactECharts from "echarts-for-react";

export type AiReportDetail = {
  report_id: string;
  range_start: string;
  range_end: string;
  model_name: string;
  generated_at: string;
  scope?: { strategy_ids?: string[]; markets?: string[]; symbols?: string[] };
  metrics: Record<string, unknown>;
  content: string;
  content_format: string;
  metadata?: { feedback?: string };
};

type Props = {
  report: AiReportDetail | null | undefined;
  loading?: boolean;
  selected?: boolean;
  onUseful?: () => void;
  onUseless?: () => void;
  onCopy?: () => void;
  feedbackLoading?: boolean;
};

export default function AiReportViewer({
  report,
  loading,
  selected,
  onUseful,
  onUseless,
  onCopy,
  feedbackLoading,
}: Props) {
  const metrics = (report?.metrics ?? {}) as Record<
    string,
    string | number | boolean | undefined
  >;
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
    <Card
      size="small"
      title="报告详情"
      extra={
        selected ? (
          <Space>
            <Button size="small" loading={feedbackLoading} onClick={onUseful}>
              标记有用
            </Button>
            <Button size="small" loading={feedbackLoading} onClick={onUseless}>
              标记无用
            </Button>
            <Button size="small" onClick={onCopy}>
              复制 Markdown
            </Button>
          </Space>
        ) : null
      }
    >
      {!selected ? (
        <Typography.Text type="secondary">请选择或生成一份报告</Typography.Text>
      ) : loading ? (
        <Typography.Text>加载中…</Typography.Text>
      ) : report ? (
        <Space orientation="vertical" style={{ width: "100%" }} size="middle">
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
              {report.content}
            </pre>
          </Typography.Paragraph>
          {report.metadata?.feedback ? (
            <Typography.Text type="secondary">反馈：{report.metadata.feedback}</Typography.Text>
          ) : null}
        </Space>
      ) : (
        <Typography.Text type="secondary">报告不存在</Typography.Text>
      )}
    </Card>
  );
}
