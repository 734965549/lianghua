export function connColor(s: string): string {
  if (s === "ok" || s === "connected") return "success";
  if (s === "disconnected" || s === "not_configured") return "error";
  return "warning";
}

export function systemStatusColor(status: string): string {
  if (status === "trading" || status === "ready") return "success";
  if (
    status === "circuit_breaker" ||
    status === "emergency_stopped" ||
    status === "offline"
  ) {
    return "error";
  }
  return "warning";
}

export const SYSTEM_STATUS_LABEL: Record<string, string> = {
  initializing: "初始化",
  ready: "就绪",
  trading: "交易中",
  paused: "已暂停",
  circuit_breaker: "熔断",
  emergency_stopped: "紧急停止",
  degraded: "降级",
  offline: "离线",
};
