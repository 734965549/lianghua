import { useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import RiskCheckDrawer, { type RiskCheckItem } from "../components/RiskCheckDrawer";
import type { Paged } from "../api/types";

type Strategy = {
  strategy_id: string;
  name: string;
  description: string;
  enabled: boolean;
  running: boolean;
  supported_markets: string[];
  parameters: Record<string, unknown>;
};

type Signal = {
  signal_id: string;
  strategy_id: string;
  symbol: string;
  market: string;
  side: string;
  action: string;
  price: string;
  quantity: string;
  reason: string;
  signal_time: string;
};

type StrategyRun = {
  run_id: string;
  strategy_id: string;
  status: string;
  started_at: string | null;
  stopped_at: string | null;
  stop_reason: string;
};

export default function Strategies() {
  const qc = useQueryClient();
  const [paramOpen, setParamOpen] = useState(false);
  const [current, setCurrent] = useState<Strategy | null>(null);
  const [form] = Form.useForm();
  const [checkOpen, setCheckOpen] = useState(false);
  const [activeCheck, setActiveCheck] = useState<RiskCheckItem | null>(null);

  const strategies = useQuery({
    queryKey: ["strategies"],
    queryFn: () => api.get<Strategy[]>("/strategies"),
    refetchInterval: 5000,
  });

  const signals = useQuery({
    queryKey: ["signals"],
    queryFn: () => api.get<Paged<Signal>>("/signals?page=1&page_size=30"),
    refetchInterval: 5000,
  });

  const checks = useQuery({
    queryKey: ["risk-checks"],
    queryFn: () => api.get<Paged<RiskCheckItem>>("/risk/checks?page=1&page_size=50"),
    refetchInterval: 5000,
  });

  const pendingRuns = useQuery({
    queryKey: ["strategy-runs", "pending_confirm"],
    queryFn: () =>
      api.get<Paged<StrategyRun>>("/strategy-runs?status=pending_confirm&page=1&page_size=20"),
    refetchInterval: 5000,
  });

  const pendingByStrategy = useMemo(() => {
    const map = new Map<string, StrategyRun>();
    for (const run of pendingRuns.data?.items ?? []) {
      if (!map.has(run.strategy_id)) map.set(run.strategy_id, run);
    }
    return map;
  }, [pendingRuns.data]);

  const checkBySignal = useMemo(() => {
    const map = new Map<string, RiskCheckItem>();
    for (const c of checks.data?.items ?? []) {
      if (c.signal_id) map.set(c.signal_id, c);
    }
    return map;
  }, [checks.data]);

  const start = useMutation({
    mutationFn: (id: string) =>
      api.post(`/strategies/${id}/start`, { confirm: true, symbols: ["600000.SH"] }),
    onSuccess: () => {
      message.success("策略已启动");
      qc.invalidateQueries({ queryKey: ["strategies"] });
      qc.invalidateQueries({ queryKey: ["strategy-runs"] });
      qc.invalidateQueries({ queryKey: ["system-status"] });
    },
  });

  const confirmRestart = (row: Strategy) => {
    const pending = pendingByStrategy.get(row.strategy_id);
    Modal.confirm({
      title: "确认重启策略？",
      content: pending
        ? `进程重启前策略 ${row.name} 曾运行中（${pending.stop_reason || "待确认"}）。确认环境正常后重新启动。`
        : "确认环境正常后重新启动策略。",
      okText: "确认重启",
      onOk: () => start.mutateAsync(row.strategy_id),
    });
  };

  const stop = useMutation({
    mutationFn: (id: string) => api.post(`/strategies/${id}/stop`, { reason: "用户停止" }),
    onSuccess: () => {
      message.success("策略已停止");
      qc.invalidateQueries({ queryKey: ["strategies"] });
    },
  });

  const saveParams = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      api.put(`/strategies/${current!.strategy_id}/parameters`, {
        parameters: {
          symbols: String(values.symbols || "600000.SH")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          fast: values.fast,
          slow: values.slow,
          interval: values.interval || "1m",
          quantity: String(values.quantity ?? "100"),
        },
      }),
    onSuccess: () => {
      message.success("参数已保存");
      setParamOpen(false);
      qc.invalidateQueries({ queryKey: ["strategies"] });
    },
  });

  const openParams = (s: Strategy) => {
    setCurrent(s);
    const p = s.parameters || {};
    form.setFieldsValue({
      symbols: Array.isArray(p.symbols) ? (p.symbols as string[]).join(",") : "600000.SH",
      fast: Number(p.fast ?? 5),
      slow: Number(p.slow ?? 20),
      interval: String(p.interval ?? "1m"),
      quantity: Number(p.quantity ?? 100),
    });
    setParamOpen(true);
  };

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        策略监控
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        信号生成后强制过风控；进程重启后需确认再启动策略。
      </Typography.Paragraph>

      {(pendingRuns.data?.items.length ?? 0) > 0 ? (
        <Alert
          type="warning"
          showIcon
          banner
          style={{ marginBottom: 16 }}
          message={`${pendingRuns.data?.items.length} 个策略运行实例待确认重启（进程重启后不会自动恢复）`}
        />
      ) : null}

      <Card title="策略列表" size="small" style={{ marginBottom: 16 }}>
        <Table
          rowKey="strategy_id"
          size="small"
          loading={strategies.isLoading}
          dataSource={strategies.data ?? []}
          pagination={false}
          columns={[
            { title: "ID", dataIndex: "strategy_id", width: 120 },
            { title: "名称", dataIndex: "name", width: 140 },
            { title: "说明", dataIndex: "description" },
            {
              title: "状态",
              width: 140,
              render: (_, row) => {
                const pending = pendingByStrategy.get(row.strategy_id);
                if (row.running) {
                  return <Tag color="green">运行中</Tag>;
                }
                if (pending) {
                  return <Tag color="orange">待确认重启</Tag>;
                }
                return <Tag>已停止</Tag>;
              },
            },
            {
              title: "操作",
              width: 300,
              render: (_, row) => {
                const pending = pendingByStrategy.get(row.strategy_id);
                return (
                <Space>
                  <Button size="small" onClick={() => openParams(row)}>
                    参数
                  </Button>
                  {row.running ? (
                    <Button size="small" danger onClick={() => stop.mutate(row.strategy_id)}>
                      停止
                    </Button>
                  ) : pending ? (
                    <Button size="small" type="primary" onClick={() => confirmRestart(row)}>
                      确认重启
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      type="primary"
                      onClick={() =>
                        Modal.confirm({
                          title: "确认启动实盘策略？",
                          content: "启动后系统将进入 trading，信号经风控后自动下单。",
                          onOk: () => start.mutateAsync(row.strategy_id),
                        })
                      }
                    >
                      启动
                    </Button>
                  )}
                </Space>
                );
              },
            },
          ]}
        />
      </Card>

      <Card title="最新信号" size="small">
        <Table
          rowKey="signal_id"
          size="small"
          loading={signals.isLoading}
          dataSource={signals.data?.items ?? []}
          pagination={{ pageSize: 10, total: signals.data?.total }}
          columns={[
            { title: "时间", dataIndex: "signal_time", width: 180 },
            { title: "策略", dataIndex: "strategy_id", width: 100 },
            { title: "标的", dataIndex: "symbol", width: 110 },
            { title: "方向", dataIndex: "side", width: 70 },
            { title: "动作", dataIndex: "action", width: 70 },
            { title: "数量", dataIndex: "quantity", width: 80 },
            { title: "原因", dataIndex: "reason" },
            {
              title: "风控",
              width: 140,
              render: (_, row) => {
                const c = checkBySignal.get(row.signal_id);
                if (!c) return "-";
                return (
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      setActiveCheck(c);
                      setCheckOpen(true);
                    }}
                  >
                    <Tag color={c.result === "passed" ? "green" : "red"}>{c.result}</Tag>
                    {c.rule_code || "详情"}
                  </Button>
                );
              },
            },
          ]}
        />
      </Card>

      <Drawer
        title={`参数 · ${current?.name ?? ""}`}
        open={paramOpen}
        onClose={() => setParamOpen(false)}
        width={420}
      >
        <Form form={form} layout="vertical" onFinish={(v) => saveParams.mutate(v)}>
          <Form.Item name="symbols" label="标的（逗号分隔）" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="fast" label="快线" rules={[{ required: true }]}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="slow" label="慢线" rules={[{ required: true }]}>
            <InputNumber min={2} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="interval" label="周期">
            <Input placeholder="1m / 5m" />
          </Form.Item>
          <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saveParams.isPending} block>
            保存参数
          </Button>
        </Form>
      </Drawer>

      <RiskCheckDrawer open={checkOpen} onClose={() => setCheckOpen(false)} check={activeCheck} />
    </div>
  );
}
