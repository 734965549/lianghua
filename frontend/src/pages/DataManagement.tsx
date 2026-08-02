import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  DownloadOutlined,
  DeleteOutlined,
  RedoOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { api } from "../api/client";
import { useWebSocket } from "../hooks/useWebSocket";
import { formatDecimal, formatTime } from "../utils/format";

type Overview = {
  kline_total: number;
  kline_trusted: number;
  kline_quarantined: number;
  kline_duplicates: number;
  kline_symbols: number;
  snapshot_total: number;
  snapshot_symbols: number;
};

type IntegrityItem = {
  market: string;
  symbol: string;
  interval: string;
  count: number;
  raw_count: number;
  quarantined_count: number;
  duplicate_count: number;
  start: string | null;
  end: string | null;
  missing_days: number;
};

type DownloadProgress = {
  task_id?: string;
  status: string;
  done: number;
  total: number;
  items?: Record<string, {
    status: string;
    symbol?: string;
    interval?: string;
    count?: number;
    received?: number;
    quarantined?: number;
    deduplicated?: number;
    error?: string;
  }>;
  error?: string;
  message?: string;
};

type KlineRow = Record<string, string> & {
  source: string;
  quality_status: "accepted" | "quarantined";
  quality_reasons: string[];
  record_role: "primary" | "duplicate" | "quarantined";
  quarantine_reason?: string | null;
};

type SyncLog = {
  id: string;
  status: string;
  symbols: string[];
  intervals: string[];
  start_date: string;
  end_date: string;
  progress: DownloadProgress;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
};

function healthTag(missing: number) {
  if (missing === 0) return <Tag color="green">正常</Tag>;
  if (missing < 10) return <Tag color="gold">轻微缺失</Tag>;
  return <Tag color="red">缺失较多</Tag>;
}

export default function DataManagement() {
  const [form] = Form.useForm();
  const qc = useQueryClient();
  const [progress, setProgress] = useState<DownloadProgress>({ status: "idle", done: 0, total: 0 });
  const [browseSymbol, setBrowseSymbol] = useState("600000.SH");
  const [browseMarket, setBrowseMarket] = useState("stock");
  const [browseInterval, setBrowseInterval] = useState("1d");
  const [deleteTarget, setDeleteTarget] = useState<IntegrityItem | null>(null);

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["data-overview"],
    queryFn: () => api.get<Overview>("/data/overview"),
    refetchInterval: 30000,
  });

  const { data: integrity, refetch: refetchIntegrity } = useQuery({
    queryKey: ["data-integrity"],
    queryFn: () => api.get<{ items: IntegrityItem[] }>("/data/integrity"),
  });

  const { data: history } = useQuery({
    queryKey: ["download-history"],
    queryFn: () => api.get<SyncLog[]>("/data/download/history"),
    refetchInterval: 10000,
  });

  const { data: klines, refetch: refetchKlines } = useQuery({
    queryKey: ["data-klines", browseMarket, browseSymbol, browseInterval],
    queryFn: () =>
      api.get<KlineRow[]>(
        `/data/klines?market=${browseMarket}&symbol=${browseSymbol}&interval=${browseInterval}&limit=200`
      ),
    enabled: !!browseSymbol,
  });

  useQuery({
    queryKey: ["download-status"],
    queryFn: async () => {
      const s = await api.get<DownloadProgress>("/data/download/status");
      setProgress(s);
      return s;
    },
    refetchInterval: 5000,
  });

  useWebSocket("data.download.progress", (raw) => {
    const next = raw as DownloadProgress;
    setProgress(next);
    if (next.status === "done") {
      void qc.invalidateQueries({ queryKey: ["data-overview"] });
      void qc.invalidateQueries({ queryKey: ["data-integrity"] });
      void qc.invalidateQueries({ queryKey: ["data-klines"] });
    }
  });

  const downloadMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/data/download", body),
    onSuccess: () => {
      message.success("下载任务已启动");
      qc.invalidateQueries({ queryKey: ["download-history"] });
    },
  });

  const qualityMut = useMutation({
    mutationFn: () => api.get("/data/quality"),
    onSuccess: () => message.success("质量检查已完成，请查看系统日志"),
  });

  const deleteMut = useMutation({
    mutationFn: (params: { market: string; symbol: string; interval?: string }) => {
      const qs = new URLSearchParams({ market: params.market, symbol: params.symbol });
      if (params.interval) qs.set("interval", params.interval);
      return api.del(`/data/klines?${qs.toString()}`);
    },
    onSuccess: () => {
      message.success("已删除");
      refetchIntegrity();
      refetchKlines();
      setDeleteTarget(null);
    },
  });

  const cancelMut = useMutation({
    mutationFn: (taskId: string) => api.post(`/data/download/${taskId}/cancel`),
    onSuccess: () => {
      message.info("已请求取消下载任务");
      void qc.invalidateQueries({ queryKey: ["download-status"] });
      void qc.invalidateQueries({ queryKey: ["download-history"] });
    },
  });

  const retryMut = useMutation({
    mutationFn: (taskId: string) => api.post(`/data/download/${taskId}/retry`),
    onSuccess: () => {
      message.success("重试任务已启动");
      void qc.invalidateQueries({ queryKey: ["download-status"] });
      void qc.invalidateQueries({ queryKey: ["download-history"] });
    },
  });

  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const failedItems = Object.values(progress.items ?? {}).filter((item) => item.error);

  const exportCsv = () => {
    if (!klines?.length) {
      message.warning("无数据可导出");
      return;
    }
    const headers = ["bar_time", "open", "high", "low", "close", "volume"];
    const lines = [headers.join(",")];
    for (const row of klines) {
      lines.push(headers.map((h) => row[h] ?? "").join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${browseSymbol}_${browseInterval}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        数据管理
      </Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card size="small" loading={overviewLoading}><Statistic title="K 线总量" value={overview?.kline_total ?? 0} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small" loading={overviewLoading}><Statistic title="K 线标的数" value={overview?.kline_symbols ?? 0} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small" loading={overviewLoading}><Statistic title="快照总量" value={overview?.snapshot_total ?? 0} /></Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small" loading={overviewLoading}><Statistic title="快照标的数" value={overview?.snapshot_symbols ?? 0} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={8}>
          <Card size="small" loading={overviewLoading}>
            <Statistic title="可信 K 线" value={overview?.kline_trusted ?? 0} />
          </Card>
        </Col>
        <Col xs={12} md={8}>
          <Card size="small" loading={overviewLoading}>
            <Statistic
              title="已隔离异常"
              value={overview?.kline_quarantined ?? 0}
              styles={{ content: { color: overview?.kline_quarantined ? "#cf1322" : undefined } }}
            />
          </Card>
        </Col>
        <Col xs={12} md={8}>
          <Card size="small" loading={overviewLoading}>
            <Statistic
              title="重复交易周期"
              value={overview?.kline_duplicates ?? 0}
              styles={{ content: { color: overview?.kline_duplicates ? "#d48806" : undefined } }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card title="历史数据下载" size="small">
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                intervals: ["1d"],
                use_watchlist: true,
                start_date: dayjs().subtract(1, "year"),
              }}
              onFinish={(v) =>
                downloadMut.mutate({
                  intervals: v.intervals,
                  use_watchlist: v.use_watchlist,
                  start_date: v.start_date.format("YYYYMMDD"),
                  end_date: v.end_date ? v.end_date.format("YYYYMMDD") : undefined,
                  symbols: v.symbols
                    ? v.symbols.split(",").map((s: string) => s.trim()).filter(Boolean)
                    : undefined,
                })
              }
            >
              <Form.Item name="intervals" label="周期">
                <Select mode="multiple" options={[
                  { value: "1d", label: "日线" },
                  { value: "1m", label: "1 分钟" },
                  { value: "5m", label: "5 分钟" },
                ]} />
              </Form.Item>
              <Form.Item name="start_date" label="开始日期">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="end_date" label="结束日期">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="symbols" label="指定标的（逗号分隔，留空用股票池）">
                <Input placeholder="600000.SH,000001.SZ" />
              </Form.Item>
              <Space>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<DownloadOutlined />}
                  loading={downloadMut.isPending}
                  disabled={progress.status === "running" || progress.status === "cancelling"}
                >
                  开始下载
                </Button>
                <Button onClick={() => qualityMut.mutate()} loading={qualityMut.isPending}>
                  质量检查
                </Button>
              </Space>
            </Form>
            {progress.status !== "idle" && (
              <div style={{ marginTop: 16 }}>
                <Progress
                  percent={pct}
                  status={
                    progress.status === "done"
                      ? "success"
                      : ["failed", "cancelled"].includes(progress.status)
                        ? "exception"
                        : "active"
                  }
                />
                <Space wrap>
                  <Typography.Text type="secondary">
                    {progress.done}/{progress.total} · {progress.status}
                  </Typography.Text>
                  {progress.task_id &&
                  (progress.status === "running" || progress.status === "cancelling") ? (
                    <Button
                      size="small"
                      danger
                      icon={<StopOutlined />}
                      loading={cancelMut.isPending}
                      disabled={progress.status === "cancelling"}
                      onClick={() => cancelMut.mutate(progress.task_id!)}
                    >
                      取消
                    </Button>
                  ) : null}
                  {progress.task_id &&
                  ["failed", "cancelled"].includes(progress.status) ? (
                    <Button
                      size="small"
                      icon={<RedoOutlined />}
                      loading={retryMut.isPending}
                      onClick={() => retryMut.mutate(progress.task_id!)}
                    >
                      重试
                    </Button>
                  ) : null}
                </Space>
                {progress.error || failedItems.length ? (
                  <Alert
                    type="error"
                    showIcon
                    style={{ marginTop: 8 }}
                    title={progress.error || `${failedItems.length} 个下载项失败`}
                    description={failedItems
                      .map((item) => `${item.symbol ?? "-"} ${item.interval ?? ""}: ${item.error}`)
                      .join("；")}
                  />
                ) : null}
              </div>
            )}
          </Card>

          <Card title="下载历史" size="small" style={{ marginTop: 16 }}>
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={history ?? []}
              columns={[
                { title: "状态", dataIndex: "status", render: (v) => <Tag>{v}</Tag> },
                { title: "标的数", render: (_, r) => r.symbols?.length ?? 0 },
                { title: "周期", render: (_, r) => r.intervals?.join(",") },
                { title: "时间", dataIndex: "created_at", render: (v) => dayjs(v).format("MM-DD HH:mm") },
                {
                  title: "失败原因",
                  dataIndex: "error_message",
                  ellipsis: true,
                  render: (value) => value || "-",
                },
                {
                  title: "操作",
                  render: (_, row) =>
                    ["failed", "cancelled"].includes(row.status) ? (
                      <Button
                        type="link"
                        size="small"
                        icon={<RedoOutlined />}
                        loading={retryMut.isPending}
                        onClick={() => retryMut.mutate(row.id)}
                      >
                        重试
                      </Button>
                    ) : null,
                },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="数据完整性" size="small">
            <Table
              size="small"
              rowKey={(r) => `${r.market}:${r.symbol}:${r.interval}`}
              dataSource={integrity?.items ?? []}
              pagination={{ pageSize: 8 }}
              scroll={{ x: 760 }}
              columns={[
                { title: "标的", dataIndex: "symbol" },
                { title: "周期", dataIndex: "interval" },
                { title: "条数", dataIndex: "count" },
                {
                  title: "原始/可信",
                  render: (_, r) => `${r.raw_count}/${r.count}`,
                },
                {
                  title: "隔离/重复",
                  render: (_, r) => (
                    <Space size={4}>
                      <Tag color={r.quarantined_count ? "red" : "default"}>
                        {r.quarantined_count}
                      </Tag>
                      <Tag color={r.duplicate_count ? "gold" : "default"}>
                        {r.duplicate_count}
                      </Tag>
                    </Space>
                  ),
                },
                {
                  title: "范围",
                  render: (_, r) =>
                    r.start && r.end
                      ? `${dayjs(r.start).format("YYYY-MM-DD")} ~ ${dayjs(r.end).format("YYYY-MM-DD")}`
                      : "-",
                },
                {
                  title: "健康",
                  render: (_, r) => healthTag(r.missing_days),
                },
                {
                  title: "操作",
                  render: (_, r) => (
                    <Space>
                      <Button
                        size="small"
                        onClick={() => {
                          setBrowseSymbol(r.symbol);
                          setBrowseMarket(r.market);
                          setBrowseInterval(r.interval);
                        }}
                      >
                        浏览
                      </Button>
                      <Button size="small" danger icon={<DeleteOutlined />} onClick={() => setDeleteTarget(r)} />
                    </Space>
                  ),
                },
              ]}
            />
          </Card>

          <Card
            title="数据浏览器"
            size="small"
            style={{ marginTop: 16 }}
            extra={
              <Space>
                <Select size="small" value={browseMarket} style={{ width: 90 }} onChange={setBrowseMarket}
                  options={[{ value: "stock", label: "股票" }, { value: "futures", label: "期货" }]} />
                <Input size="small" value={browseSymbol} style={{ width: 120 }} onChange={(e) => setBrowseSymbol(e.target.value)} />
                <Select size="small" value={browseInterval} style={{ width: 80 }} onChange={setBrowseInterval}
                  options={[{ value: "1d", label: "日线" }, { value: "1m", label: "1m" }, { value: "5m", label: "5m" }]} />
                <Button size="small" onClick={exportCsv}>导出 CSV</Button>
              </Space>
            }
          >
            <Table
              size="small"
              rowKey="bar_time"
              dataSource={klines ?? []}
              pagination={{ pageSize: 10 }}
              scroll={{ x: 600 }}
              columns={[
                {
                  title: "时间",
                  dataIndex: "bar_time",
                  width: 180,
                  render: (value) => formatTime(value, "YYYY-MM-DD HH:mm:ss"),
                },
                {
                  title: "来源",
                  dataIndex: "source",
                  width: 100,
                  render: (value) => (
                    <Tag color={value === "unknown" ? "gold" : "blue"}>{value}</Tag>
                  ),
                },
                {
                  title: "记录角色",
                  dataIndex: "record_role",
                  width: 110,
                  render: (value, row) => (
                    <Tag
                      color={
                        value === "primary"
                          ? "green"
                          : value === "duplicate"
                            ? "gold"
                            : "red"
                      }
                      title={row.quarantine_reason || undefined}
                    >
                      {value === "primary"
                        ? "主记录"
                        : value === "duplicate"
                          ? "重复记录"
                          : "隔离记录"}
                    </Tag>
                  ),
                },
                {
                  title: "质量",
                  dataIndex: "quality_status",
                  width: 100,
                  render: (value, row) => (
                    <Tag
                      color={value === "accepted" ? "green" : "red"}
                      title={row.quality_reasons?.join(", ") || undefined}
                    >
                      {value === "accepted" ? "回测可用" : "回测隔离"}
                    </Tag>
                  ),
                },
                { title: "开", dataIndex: "open", align: "right", render: (v) => formatDecimal(v, 2) },
                { title: "高", dataIndex: "high", align: "right", render: (v) => formatDecimal(v, 2) },
                { title: "低", dataIndex: "low", align: "right", render: (v) => formatDecimal(v, 2) },
                { title: "收", dataIndex: "close", align: "right", render: (v) => formatDecimal(v, 2) },
                { title: "量", dataIndex: "volume", align: "right", render: (v) => formatDecimal(v, 0) },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        open={!!deleteTarget}
        title="删除 K 线数据"
        okText="删除"
        okButtonProps={{ danger: true }}
        confirmLoading={deleteMut.isPending}
        onCancel={() => setDeleteTarget(null)}
        onOk={() =>
          deleteTarget &&
          deleteMut.mutate({
            market: deleteTarget.market,
            symbol: deleteTarget.symbol,
            interval: deleteTarget.interval,
          })
        }
      >
        {deleteTarget
          ? `确定删除 ${deleteTarget.symbol} ${deleteTarget.interval} 的全部 K 线？此操作不可恢复。`
          : ""}
      </Modal>
    </div>
  );
}
