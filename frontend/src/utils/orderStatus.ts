export function orderStatusColor(status: string): string {
  if (status === "filled") return "success";
  if (status === "risk_rejected" || status === "failed") return "error";
  if (status === "unknown") return "error";
  if (status === "cancelled") return "default";
  return "processing";
}

export const ORDER_STATUS_LABEL: Record<string, string> = {
  pending_risk: "待风控",
  risk_rejected: "风控拒绝",
  submitting: "提交中",
  submitted: "已报",
  partially_filled: "部分成交",
  filled: "已成交",
  cancelled: "已撤",
  failed: "失败",
  unknown: "未知",
};
