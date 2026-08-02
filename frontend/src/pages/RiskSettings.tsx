import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatDecimal } from "../utils/format";
import ConfirmDialog from "../components/ConfirmDialog";
import EmergencyStopButton from "../components/EmergencyStopButton";

type RiskSettings = {
  allowed_symbols: string[];
  blocked_symbols: string[];
  trading_sessions: unknown[];
  max_order_amount: string | number;
  max_order_quantity: string | number;
  max_symbol_position: string | number;
  max_total_position: string | number;
  daily_loss_limit: string | number;
  daily_trade_count_limit: number;
  sdk_disconnect_timeout_seconds: number;
  quote_stale_timeout_seconds: number;
  consecutive_order_fail_limit: number;
  duplicate_signal_window_seconds: number;
  auto_cancel_on_breaker: boolean;
};

type RiskStatus = {
  system_status: string;
  status_reason?: string;
  breaker_active: boolean;
  breaker_reason?: string;
  daily_loss: string;
  daily_loss_limit: string;
  daily_trade_count: number;
  consecutive_order_fail: number;
  unknown_order_count: number;
};

type ResumeChecklist = {
  all_passed: boolean;
  checked_at: string;
  checks: Array<{
    code: string;
    label: string;
    passed: boolean;
    detail: string;
  }>;
};

type PendingAction =
  | { type: "save"; values: Record<string, unknown> }
  | { type: "resume" };

export default function RiskSettings() {
  const [form] = Form.useForm();
  const qc = useQueryClient();
  const [pending, setPending] = useState<PendingAction | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["risk-settings"],
    queryFn: () => api.get<RiskSettings>("/risk/settings"),
  });

  const status = useQuery({
    queryKey: ["risk-status"],
    queryFn: () => api.get<RiskStatus>("/risk/status"),
    refetchInterval: 5000,
  });

  useEffect(() => {
    if (!data) return;
    form.setFieldsValue({
      ...data,
      allowed_symbols: (data.allowed_symbols ?? []).join(","),
      blocked_symbols: (data.blocked_symbols ?? []).join(","),
      max_order_amount: Number(data.max_order_amount),
      max_order_quantity: Number(data.max_order_quantity),
      max_symbol_position: Number(data.max_symbol_position),
      max_total_position: Number(data.max_total_position),
      daily_loss_limit: Number(data.daily_loss_limit),
    });
  }, [data, form]);

  const save = useMutation({
    mutationFn: ({ values, reason }: { values: Record<string, unknown>; reason: string }) =>
      api.put("/risk/settings", {
        confirm: true,
        allowed_symbols: String(values.allowed_symbols || "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        blocked_symbols: String(values.blocked_symbols || "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        max_order_amount: String(values.max_order_amount),
        max_order_quantity: String(values.max_order_quantity),
        max_symbol_position: String(values.max_symbol_position),
        max_total_position: String(values.max_total_position),
        daily_loss_limit: String(values.daily_loss_limit),
        daily_trade_count_limit: values.daily_trade_count_limit,
        sdk_disconnect_timeout_seconds: values.sdk_disconnect_timeout_seconds,
        quote_stale_timeout_seconds: values.quote_stale_timeout_seconds,
        consecutive_order_fail_limit: values.consecutive_order_fail_limit,
        duplicate_signal_window_seconds: values.duplicate_signal_window_seconds,
        auto_cancel_on_breaker: values.auto_cancel_on_breaker,
        reason,
      }),
    onSuccess: () => {
      message.success("风控参数已保存");
      qc.invalidateQueries({ queryKey: ["risk-settings"] });
    },
  });

  const resume = useMutation({
    mutationFn: (reason: string) => api.post("/risk/resume", { confirm: true, reason }),
    onSuccess: () => {
      message.success("已恢复交易");
      qc.invalidateQueries({ queryKey: ["risk-status"] });
      qc.invalidateQueries({ queryKey: ["system-status"] });
      qc.invalidateQueries({ queryKey: ["risk-resume-checklist"] });
    },
    onError: (err: { message?: string; debug?: string; code?: string }) => {
      const detail = err?.debug || err?.message || "恢复失败";
      message.error(detail);
    },
  });

  const st = status.data;
  const unknownCount = st?.unknown_order_count ?? 0;
  const checklist = useQuery({
    queryKey: ["risk-resume-checklist"],
    queryFn: () =>
      api.get<ResumeChecklist>("/risk/resume-checklist"),
    enabled: Boolean(st?.breaker_active),
    refetchInterval: st?.breaker_active ? 5000 : false,
  });

  const dialogMeta =
    pending?.type === "save"
      ? {
          title: "确认保存风控参数？",
          impact: "风控参数变更可能影响交易安全与可成交范围。",
          okText: "确认保存",
          danger: false,
        }
      : pending?.type === "resume"
        ? {
            title: "确认恢复交易？",
            impact:
              unknownCount > 0
                ? `当前有 ${unknownCount} 笔未知订单，恢复将被拒绝。将解除熔断/紧急停止前，请确认 SDK 与账户正常。`
                : "将解除熔断/紧急停止，恢复交易前请确认 SDK 与账户正常。",
            okText: "确认恢复",
            danger: false,
          }
        : null;

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        风控设置
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        当前状态：{st?.system_status ?? "-"}
        {st?.breaker_active ? " · 熔断/停止中" : ""} · 当日亏损{" "}
        {formatDecimal(st?.daily_loss)} / {formatDecimal(st?.daily_loss_limit)} · 连续失败{" "}
        {st?.consecutive_order_fail ?? 0} · 未知订单{" "}
        {unknownCount}
      </Typography.Paragraph>

      {st?.breaker_active ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title={st.system_status === "emergency_stopped" ? "紧急停止中" : "熔断中"}
          description={
            checklist.data?.all_passed
              ? `历史触发原因：${st.breaker_reason || st.status_reason || "未记录"}。当前恢复检查已全部通过，仍需人工确认后恢复。`
              : st.breaker_reason || st.status_reason || "禁止新委托，需满足前置条件后手动恢复"
          }
        />
      ) : null}

      {unknownCount > 0 ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title={`存在 ${unknownCount} 笔未知状态订单`}
          description="恢复交易前必须人工确认或处理全部 unknown 订单。"
        />
      ) : null}

      {st?.breaker_active ? (
        <Card
          size="small"
          title="恢复交易检查清单"
          style={{ marginBottom: 16 }}
          extra={
            <Tag color={checklist.data?.all_passed ? "green" : "red"}>
              {checklist.data?.all_passed ? "全部通过" : "存在阻断项"}
            </Tag>
          }
          loading={checklist.isLoading}
        >
          <div role="list" style={{ display: "grid", gap: 8 }}>
            {(checklist.data?.checks ?? []).map((item) => (
              <div
                key={item.code}
                role="listitem"
                style={{
                  alignItems: "center",
                  borderBottom: "1px solid #1d2937",
                  display: "flex",
                  gap: 16,
                  justifyContent: "space-between",
                  padding: "8px 0",
                }}
              >
                <div>
                  <Typography.Text strong>{item.label}</Typography.Text>
                  <Typography.Text type="secondary" style={{ display: "block" }}>
                    {item.detail}
                  </Typography.Text>
                </div>
                <Tag color={item.passed ? "green" : "red"}>
                  {item.passed ? "通过" : "阻断"}
                </Tag>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <Card loading={isLoading} size="small">
        <Form
          form={form}
          layout="vertical"
          style={{ maxWidth: 720 }}
          onFinish={(values) => setPending({ type: "save", values })}
        >
          <Form.Item name="allowed_symbols" label="白名单（逗号分隔，空=不限制）">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="blocked_symbols" label="黑名单（逗号分隔）">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="max_order_amount" label="单笔最大金额">
            <InputNumber style={{ width: "100%" }} min={0} />
          </Form.Item>
          <Form.Item name="max_order_quantity" label="单笔最大数量">
            <InputNumber style={{ width: "100%" }} min={0} />
          </Form.Item>
          <Form.Item name="max_symbol_position" label="单标的最大仓位">
            <InputNumber style={{ width: "100%" }} min={0} />
          </Form.Item>
          <Form.Item name="max_total_position" label="总仓位上限">
            <InputNumber style={{ width: "100%" }} min={0} />
          </Form.Item>
          <Form.Item name="daily_loss_limit" label="当日亏损阈值">
            <InputNumber style={{ width: "100%" }} min={0} />
          </Form.Item>
          <Form.Item name="daily_trade_count_limit" label="当日交易次数上限">
            <InputNumber style={{ width: "100%" }} min={0} />
          </Form.Item>
          <Form.Item name="quote_stale_timeout_seconds" label="行情停更秒数">
            <InputNumber style={{ width: "100%" }} min={1} />
          </Form.Item>
          <Form.Item name="duplicate_signal_window_seconds" label="重复信号窗口（秒）">
            <InputNumber style={{ width: "100%" }} min={0} />
          </Form.Item>
          <Form.Item name="sdk_disconnect_timeout_seconds" label="SDK 断线超时（秒）">
            <InputNumber style={{ width: "100%" }} min={1} />
          </Form.Item>
          <Form.Item name="consecutive_order_fail_limit" label="连续下单失败上限">
            <InputNumber style={{ width: "100%" }} min={1} />
          </Form.Item>
          <Form.Item name="auto_cancel_on_breaker" label="熔断自动撤单" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Space wrap>
            <Button type="primary" htmlType="submit" loading={save.isPending}>
              保存风控参数
            </Button>
            <EmergencyStopButton />
            <Button
              disabled={
                Boolean(st?.breaker_active) &&
                checklist.data?.all_passed === false
              }
              onClick={() => setPending({ type: "resume" })}
            >
              恢复交易
            </Button>
          </Space>
        </Form>
      </Card>

      <ConfirmDialog
        open={!!pending && !!dialogMeta}
        title={dialogMeta?.title ?? ""}
        impact={dialogMeta?.impact}
        okText={dialogMeta?.okText}
        danger={dialogMeta?.danger}
        confirmLoading={save.isPending || resume.isPending}
        onCancel={() => setPending(null)}
        onConfirm={async (reason) => {
          if (!pending) return;
          if (pending.type === "save") {
            await save.mutateAsync({ values: pending.values, reason });
          } else {
            await resume.mutateAsync(reason);
          }
          setPending(null);
        }}
      />
    </div>
  );
}
