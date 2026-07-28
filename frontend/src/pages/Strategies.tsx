import { useMemo, useState } from "react";
import { Alert, Card, Drawer, Form, Table, Tag, Typography, Button, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import ConfirmDialog from "../components/ConfirmDialog";
import RiskCheckDrawer, { type RiskCheckItem } from "../components/RiskCheckDrawer";
import StrategyTable, { type StrategyRow } from "../components/StrategyTable";
import StrategyParamForm, {
  buildParametersFromForm,
  getInitialFormValues,
} from "../components/StrategyParamForm";
import type { Paged } from "../api/types";

type Strategy = StrategyRow;

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
  const [paramInitial, setParamInitial] = useState<Record<string, unknown>>({});
  const [checkOpen, setCheckOpen] = useState(false);
  const [activeCheck, setActiveCheck] = useState<RiskCheckItem | null>(null);
  const [startTarget, setStartTarget] = useState<Strategy | null>(null);
  const [startMode, setStartMode] = useState<"start" | "restart">("start");

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
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.post(`/strategies/${id}/start`, { confirm: true, reason }),
    onSuccess: () => {
      message.success("策略已启动");
      qc.invalidateQueries({ queryKey: ["strategies"] });
      qc.invalidateQueries({ queryKey: ["strategy-runs"] });
      qc.invalidateQueries({ queryKey: ["system-status"] });
    },
  });

  const openStartConfirm = (row: Strategy, mode: "start" | "restart" = "start") => {
    setStartMode(mode);
    setStartTarget(row);
  };

  const stop = useMutation({
    mutationFn: (id: string) => api.post(`/strategies/${id}/stop`, { reason: "用户停止" }),
    onSuccess: () => {
      message.success("策略已停止");
      qc.invalidateQueries({ queryKey: ["strategies"] });
    },
  });

  const saveParams = useMutation({
    mutationFn: (values: Record<string, unknown>) => {
      const parameters = buildParametersFromForm(current?.parameters_schema, values);
      return api.put(`/strategies/${current!.strategy_id}/parameters`, { parameters });
    },
    onSuccess: () => {
      message.success("参数已保存");
      setParamOpen(false);
      qc.invalidateQueries({ queryKey: ["strategies"] });
    },
  });

  const openParams = (s: Strategy) => {
    setCurrent(s);
    const initial = getInitialFormValues(s.parameters_schema, s.parameters || {});
    setParamInitial(initial);
    form.setFieldsValue(initial);
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
        <StrategyTable
          dataSource={strategies.data ?? []}
          loading={strategies.isLoading}
          pendingByStrategy={pendingByStrategy}
          onOpenParams={openParams}
          onStart={(row) => openStartConfirm(row, "start")}
          onRestart={(row) => openStartConfirm(row, "restart")}
          onStop={(row) => stop.mutate(row.strategy_id)}
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
        <StrategyParamForm
          schema={current?.parameters_schema}
          form={form}
          initialValues={paramInitial}
          loading={saveParams.isPending}
          onFinish={(v) => saveParams.mutate(v)}
        />
      </Drawer>

      <RiskCheckDrawer open={checkOpen} onClose={() => setCheckOpen(false)} check={activeCheck} />

      <ConfirmDialog
        open={!!startTarget}
        title={startMode === "restart" ? "确认重启策略？" : "确认启动实盘策略？"}
        impact={
          startMode === "restart"
            ? (() => {
                const pending = startTarget
                  ? pendingByStrategy.get(startTarget.strategy_id)
                  : undefined;
                return pending
                  ? `进程重启前策略 ${startTarget?.name} 曾运行中（${pending.stop_reason || "待确认"}）。将启动实盘策略，可能产生真实委托。`
                  : "将启动实盘策略，可能产生真实委托。确认环境正常后重新启动。";
              })()
            : "将启动实盘策略，可能产生真实委托。启动后系统将进入 trading，信号经风控后自动下单。"
        }
        okText={startMode === "restart" ? "确认重启" : "确认启动"}
        danger
        confirmLoading={start.isPending}
        onCancel={() => setStartTarget(null)}
        onConfirm={async (reason) => {
          if (!startTarget) return;
          await start.mutateAsync({ id: startTarget.strategy_id, reason });
          setStartTarget(null);
        }}
      />
    </div>
  );
}
