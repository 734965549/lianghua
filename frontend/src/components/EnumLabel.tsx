import { Tooltip } from "antd";

export type EnumKind =
  | "market"
  | "side"
  | "action"
  | "status"
  | "risk"
  | "severity";

const LABELS: Record<EnumKind, Record<string, string>> = {
  market: {
    stock: "股票",
    futures: "期货",
  },
  side: {
    buy: "买入",
    sell: "卖出",
  },
  action: {
    open: "开仓",
    close: "平仓",
    close_today: "平今",
    close_yesterday: "平昨",
  },
  status: {
    pending_risk: "待风控",
    pending_submit: "待提交",
    submitting: "提交中",
    submitted: "已报",
    partially_filled: "部分成交",
    filled: "已成交",
    cancelled: "已撤销",
    failed: "失败",
    risk_rejected: "风控拒绝",
    unknown: "状态未知",
    running: "运行中",
    completed: "已完成",
    pending_confirm: "待确认",
    stopped: "已停止",
  },
  risk: {
    success: "成功",
    passed: "通过",
    rejected: "拒绝",
    failed: "失败",
  },
  severity: {
    info: "信息",
    warning: "警告",
    error: "错误",
    critical: "严重",
  },
};

export function enumLabel(value: string | null | undefined, kind: EnumKind): string {
  if (!value) return "-";
  return LABELS[kind][value.toLowerCase()] ?? value;
}

export default function EnumLabel({
  value,
  kind,
}: {
  value: string | null | undefined;
  kind: EnumKind;
}) {
  if (!value) return <>-</>;
  return (
    <Tooltip title={`内部枚举：${value}`}>
      <span>{enumLabel(value, kind)}</span>
    </Tooltip>
  );
}
