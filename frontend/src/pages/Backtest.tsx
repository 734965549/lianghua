import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import {
  ExperimentOutlined,
  FundProjectionScreenOutlined,
  PercentageOutlined,
  RiseOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import ReactECharts from "echarts-for-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BacktestItem, BacktestResult, CreateBacktestRequest } from "../api/backtest";
import {
  createBacktest,
  deleteBacktest,
  getBacktest,
  listBacktests,
} from "../api/backtest";
import MetricCard from "../components/MetricCard";
import PageHeader from "../components/PageHeader";
import EnumLabel from "../components/EnumLabel";
import {
  buildParametersFromForm,
  getInitialFormValues,
  StrategyParamFields,
} from "../components/StrategyParamForm";

interface StrategyOption {
  strategy_id: string;
  name: string;
  kind?: "builtin" | "rule";
  current_version?: number | null;
  status?: string;
  parameters?: Record<string, unknown>;
  parameters_schema?: Record<string, unknown>;
}

const granularityOptions = [
  { value: "kline", label: "K 线级别" },
  { value: "simulated_tick", label: "模拟 Tick" },
  { value: "tick", label: "真实 Tick（预留）" },
];

const fillModelOptions = [
  { value: "next_open", label: "下一根 Bar 开盘价" },
  { value: "next_close", label: "下一根 Bar 收盘价" },
  { value: "vwap", label: "VWAP" },
  { value: "tick_price", label: "Tick 价" },
];

function panelTitle(title: string, hint: string) {
  return (
    <div className="panel-title">
      <div className="panel-title__copy">
        <i />
        <strong>{title}</strong>
      </div>
      <small>{hint}</small>
    </div>
  );
}

export default function BacktestPage() {
  const [form] = Form.useForm();
  const [selected, setSelected] = useState<BacktestResult | null>(null);
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data: strategies } = useQuery({
    queryKey: ["strategies"],
    queryFn: () => api.get<StrategyOption[]>("/strategies"),
  });

  const builtinStrategies = useMemo(
    () => (strategies ?? []).filter((s) => s.kind !== "rule"),
    [strategies],
  );
  const userStrategies = useMemo(
    () => (strategies ?? []).filter((s) => s.kind === "rule" && s.status === "published"),
    [strategies],
  );

  const strategyOptions = useMemo(
    () => [
      {
        label: "内置策略",
        options: builtinStrategies.map((s) => ({
          value: s.strategy_id,
          label: `${s.name} · ${s.strategy_id}`,
        })),
      },
      {
        label: "我的策略",
        options: userStrategies.map((s) => ({
          value: s.strategy_id,
          label: `${s.name} · v${s.current_version ?? "?"}`,
        })),
      },
    ],
    [builtinStrategies, userStrategies],
  );

  const selectedStrategyId = Form.useWatch("strategy_id", form);
  const selectedVersion = Form.useWatch("strategy_version", form);

  const { data: listData, isLoading } = useQuery({
    queryKey: ["backtests"],
    queryFn: () => listBacktests(0, 50),
  });

  const selectedStrategy = useMemo(
    () => strategies?.find((strategy) => strategy.strategy_id === selectedStrategyId),
    [selectedStrategyId, strategies],
  );

  useEffect(() => {
    if (!selectedStrategy) return;
    form.setFieldValue(
      "strategy_parameters",
      getInitialFormValues(
        selectedStrategy.parameters_schema,
        selectedStrategy.parameters ?? {},
      ),
    );
  }, [form, selectedStrategy]);

  const createMutation = useMutation({
    mutationFn: createBacktest,
    onSuccess: (result) => {
      message.success("回测已完成");
      setSelected(result);
      void queryClient.invalidateQueries({ queryKey: ["backtests"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBacktest,
    onSuccess: () => {
      message.success("回测记录已删除");
      void queryClient.invalidateQueries({ queryKey: ["backtests"] });
    },
  });

  const records = listData?.items ?? [];
  const completed = records.filter((item) => item.status === "completed");
  const failed = records.filter((item) => item.status === "failed");
  const bestSharpe = completed.reduce(
    (best, item) => Math.max(best, Number(item.metrics?.sharpe_ratio ?? 0)),
    0,
  );
  const avgReturn = completed.length
    ? completed.reduce((sum, item) => sum + Number(item.metrics?.total_return_pct ?? 0), 0) /
      completed.length
    : 0;

  const chartOption = useMemo(() => {
    if (!selected?.equity_curve?.length) return null;
    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: { color: "#8291a3" },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#111923",
        borderColor: "#2c3c4d",
        textStyle: { color: "#e7edf5" },
      },
      grid: { left: 55, right: 20, top: 20, bottom: 34 },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: selected.equity_curve.map((point) => dayjs(point.time).format("MM-DD HH:mm")),
        axisLine: { lineStyle: { color: "#334356" } },
        axisLabel: { color: "#667587", fontSize: 9 },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: "#667587", fontSize: 9 },
        splitLine: { lineStyle: { color: "#1d2937" } },
      },
      series: [
        {
          name: "权益",
          type: "line",
          data: selected.equity_curve.map((point) => Number(point.equity)),
          smooth: true,
          showSymbol: false,
          lineStyle: { color: "#ff4d57", width: 2 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(255,77,87,.24)" },
                { offset: 1, color: "rgba(255,77,87,0)" },
              ],
            },
          },
        },
      ],
    };
  }, [selected]);

  const handleCreate = (values: Record<string, unknown>) => {
    const parameters = buildParametersFromForm(
      selectedStrategy?.parameters_schema,
      (values.strategy_parameters as Record<string, unknown> | undefined) ?? {},
    );

    const payload: CreateBacktestRequest = {
      strategy_id: values.strategy_id as string,
      strategy_version: selectedStrategy?.kind === "rule" ? selectedVersion : undefined,
      symbols: (values.symbols as string)
        .split(",")
        .map((symbol) => symbol.trim())
        .filter(Boolean),
      start_time: (values.start_time as dayjs.Dayjs).toISOString(),
      end_time: (values.end_time as dayjs.Dayjs).toISOString(),
      initial_cash: String(values.initial_cash),
      granularity: values.granularity as CreateBacktestRequest["granularity"],
      fill_model: values.fill_model as CreateBacktestRequest["fill_model"],
      interval: values.interval as string,
      parameters,
      commission_rate: String(values.commission_rate),
      stamp_tax_rate: String(values.stamp_tax_rate),
      slippage: String(values.slippage),
    };
    createMutation.mutate(payload);
  };

  const openDetail = async (record: BacktestItem) => {
    setDetailLoadingId(record.id);
    try {
      setSelected(await getBacktest(record.id));
    } catch {
      message.error("回测详情加载失败");
    } finally {
      setDetailLoadingId(null);
    }
  };

  const columns = [
    {
      title: "策略 / 实验",
      dataIndex: "strategy_id",
      key: "strategy_id",
      render: (value: string, row: BacktestItem) => (
        <span>
          <strong>{value}</strong>
          <small style={{ display: "block", color: "#667587" }}>
            {dayjs(row.created_at).format("MM-DD HH:mm")}
          </small>
        </span>
      ),
    },
    {
      title: "标的",
      dataIndex: "symbols",
      key: "symbols",
      render: (value: string[]) => value.join(", "),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (value: BacktestItem["status"]) => (
        <Tag color={value === "completed" ? "success" : value === "failed" ? "error" : "processing"}>
          <EnumLabel value={value} kind="status" />
        </Tag>
      ),
    },
    {
      title: "总收益",
      dataIndex: "metrics",
      key: "return",
      align: "right" as const,
      render: (metrics: BacktestItem["metrics"]) => (
        <span className={Number(metrics?.total_return_pct ?? 0) < 0 ? "market-down" : "market-up"}>
          {metrics ? `${Number(metrics.total_return_pct).toFixed(4)}%` : "-"}
        </span>
      ),
    },
    {
      title: "夏普",
      dataIndex: "metrics",
      key: "sharpe",
      align: "right" as const,
      render: (metrics: BacktestItem["metrics"]) =>
        metrics ? Number(metrics.sharpe_ratio).toFixed(2) : "-",
    },
    {
      title: "最大回撤",
      dataIndex: "metrics",
      key: "drawdown",
      align: "right" as const,
      render: (metrics: BacktestItem["metrics"]) =>
        metrics ? `${Number(metrics.max_drawdown_pct).toFixed(4)}%` : "-",
    },
    {
      title: "交易数",
      dataIndex: "metrics",
      key: "trades",
      align: "right" as const,
      render: (metrics: BacktestItem["metrics"]) => metrics?.total_trades ?? "-",
    },
    {
      title: "操作",
      key: "action",
      width: 120,
      render: (_: unknown, record: BacktestItem) => (
        <Space size={2}>
          <Button
            type="link"
            size="small"
            loading={detailLoadingId === record.id}
            onClick={() => void openDetail(record)}
          >
            分析
          </Button>
          <Button danger type="link" size="small" onClick={() => deleteMutation.mutate(record.id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="RESEARCH / BACKTEST LAB"
        title="策略研究实验室"
        description="统一设置数据粒度、撮合模型和交易成本；每次实验保留参数、结果、权益曲线与失败原因。"
        meta={<span className="status-chip status-chip--success">{records.length} 个实验</span>}
      />

      <section className="research-summary">
        <MetricCard
          title="实验总数"
          value={records.length}
          loading={isLoading}
          hint="可追溯回测记录"
          icon={<ExperimentOutlined />}
        />
        <MetricCard
          title="完成率"
          value={records.length ? `${((completed.length / records.length) * 100).toFixed(0)}%` : "-"}
          loading={isLoading}
          hint={`${completed.length} 完成 / ${failed.length} 失败`}
          icon={<PercentageOutlined />}
          status={failed.length ? "warning" : "success"}
        />
        <MetricCard
          title="最佳夏普"
          value={bestSharpe.toFixed(2)}
          loading={isLoading}
          hint="已完成实验中的最高值"
          icon={<FundProjectionScreenOutlined />}
          status={bestSharpe > 0 ? "success" : "default"}
        />
        <MetricCard
          title="平均收益"
          value={`${avgReturn.toFixed(4)}%`}
          loading={isLoading}
          hint="已完成实验算术平均"
          icon={<RiseOutlined />}
          status={avgReturn < 0 ? "error" : "success"}
        />
      </section>

      <section className="research-workspace">
        <div className="research-form">
          <Card size="small" title={panelTitle("新建研究实验", "EXPERIMENT CONFIG")}>
            <Form
              form={form}
              layout="vertical"
              onFinish={handleCreate}
              initialValues={{
                initial_cash: 100000,
                granularity: "kline",
                fill_model: "next_close",
                interval: "1m",
                commission_rate: 0.0003,
                stamp_tax_rate: 0.001,
                slippage: 0,
              }}
            >
              <div className="research-form-grid">
                <Form.Item className="span-2" name="strategy_id" label="策略" rules={[{ required: true }]}>
                  <Select
                    options={strategyOptions}
                    placeholder="选择待验证策略"
                    showSearch
                    optionFilterProp="label"
                  />
                </Form.Item>
                {selectedStrategy?.kind === "rule" ? (
                  <Form.Item name="strategy_version" label="策略版本" rules={[{ required: true }]}>
                    <InputNumber
                      min={1}
                      placeholder={`当前 v${selectedStrategy.current_version ?? "?"}`}
                      style={{ width: "100%" }}
                    />
                  </Form.Item>
                ) : null}
                <Form.Item className="span-2" name="symbols" label="标的" rules={[{ required: true }]}>
                  <Input placeholder="600519.SH, 000001.SZ" />
                </Form.Item>
                <Form.Item name="start_time" label="开始时间" rules={[{ required: true }]}>
                  <DatePicker showTime format="YYYY-MM-DD HH:mm" />
                </Form.Item>
                <Form.Item name="end_time" label="结束时间" rules={[{ required: true }]}>
                  <DatePicker showTime format="YYYY-MM-DD HH:mm" />
                </Form.Item>
                <Form.Item name="initial_cash" label="初始资金" rules={[{ required: true }]}>
                  <InputNumber min={0} />
                </Form.Item>
                <Form.Item name="interval" label="K 线周期" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
                <Form.Item name="granularity" label="回放粒度" rules={[{ required: true }]}>
                  <Select options={granularityOptions} />
                </Form.Item>
                <Form.Item name="fill_model" label="撮合模型" rules={[{ required: true }]}>
                  <Select options={fillModelOptions} />
                </Form.Item>
                <Form.Item
                  name="commission_rate"
                  label="佣金率（成交金额比例）"
                  extra="示例：0.0003 = 万分之 3"
                >
                  <InputNumber min={0} max={1} step={0.0001} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item
                  name="stamp_tax_rate"
                  label="印花税率（卖出金额比例）"
                  extra="示例：0.001 = 千分之 1"
                >
                  <InputNumber min={0} max={1} step={0.0001} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item
                  name="slippage"
                  label="滑点（成交价比例）"
                  extra="示例：0.0001 = 1 bp；买入上浮、卖出下调"
                >
                  <InputNumber min={0} max={1} step={0.0001} style={{ width: "100%" }} />
                </Form.Item>
                <div className="span-2">
                  <div className="panel-title" style={{ marginBottom: 12 }}>
                    <div className="panel-title__copy">
                      <i />
                      <strong>策略参数</strong>
                    </div>
                    <small>由策略 Schema 自动生成</small>
                  </div>
                  <StrategyParamFields
                    schema={selectedStrategy?.parameters_schema}
                    namePrefix="strategy_parameters"
                    showFallback={false}
                  />
                </div>
                <Button
                  className="span-2"
                  type="primary"
                  htmlType="submit"
                  block
                  loading={createMutation.isPending}
                >
                  运行研究实验
                </Button>
              </div>
            </Form>
          </Card>
        </div>

        <div className="research-results">
          <Card size="small" title={panelTitle("实验记录", "PERFORMANCE LEDGER")}>
            <Table
              rowKey="id"
              size="small"
              loading={isLoading}
              dataSource={records}
              columns={columns}
              pagination={{ pageSize: 12, size: "small" }}
              scroll={{ x: 920 }}
            />
          </Card>
        </div>
      </section>

      <Drawer
        title="回测实验分析"
        size="large"
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
      >
        {selected ? (
          <div style={{ display: "grid", gap: 12 }}>
            <Card size="small" title={panelTitle(selected.strategy_id, selected.symbols.join(", "))}>
              <Space wrap>
                <Tag color={selected.status === "completed" ? "success" : "error"}>
                  <EnumLabel value={selected.status} kind="status" />
                </Tag>
                <Tag>{selected.granularity}</Tag>
                <Tag>{selected.fill_model}</Tag>
                <Tag>初始资金 {selected.initial_cash}</Tag>
              </Space>
              {selected.error_message ? (
                <p style={{ marginBottom: 0, color: "#ff6d76" }}>错误：{selected.error_message}</p>
              ) : null}
              <Descriptions
                size="small"
                column={1}
                bordered
                style={{ marginTop: 12 }}
                items={[
                  {
                    key: "strategy-version",
                    label: "策略版本",
                    children: selected.provenance?.strategy_version ?? "历史未记录",
                  },
                  {
                    key: "data-snapshot",
                    label: "数据快照",
                    children: selected.provenance?.data_snapshot ?? "历史未记录",
                  },
                  {
                    key: "code-hash",
                    label: "代码哈希",
                    children: selected.provenance?.code_hash ?? "历史未记录",
                  },
                  {
                    key: "bars",
                    label: "可信 Bar",
                    children:
                      selected.provenance?.bar_count == null
                        ? "历史未记录"
                        : `${selected.provenance.bar_count} 条 · ${
                            selected.provenance.sources?.join(", ") || "unknown"
                          }`,
                  },
                ]}
              />
            </Card>
            {selected.metrics ? (
              <div className="research-summary">
                <MetricCard title="总收益" value={`${Number(selected.metrics.total_return_pct).toFixed(4)}%`} />
                <MetricCard title="夏普" value={Number(selected.metrics.sharpe_ratio).toFixed(2)} />
                <MetricCard title="最大回撤" value={`${Number(selected.metrics.max_drawdown_pct).toFixed(4)}%`} />
                <MetricCard title="胜率" value={`${Number(selected.metrics.win_rate_pct).toFixed(2)}%`} />
              </div>
            ) : null}
            {chartOption ? (
              <Card size="small" title={panelTitle("权益曲线", "EQUITY CURVE")}>
                <ReactECharts option={chartOption} style={{ height: 360 }} />
              </Card>
            ) : null}
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
