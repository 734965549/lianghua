import { useQueryClient } from "@tanstack/react-query";
import { useHealth, useSystemStatusQuery } from "../api/hooks";
import type { SystemStatus } from "../api/types";
import { useWebSocket } from "./useWebSocket";

export function useSystemStatus() {
  const qc = useQueryClient();
  const health = useHealth();
  const status = useSystemStatusQuery();

  useWebSocket("system.status", (data) => {
    const payload = data as { status?: string; reason?: string; since?: string };
    if (!payload?.status) return;
    qc.setQueryData<SystemStatus>(["system-status"], (prev) => ({
      status: payload.status!,
      status_reason: payload.reason ?? prev?.status_reason ?? "",
      status_since: payload.since ?? prev?.status_since ?? "",
      breaker_reason:
        payload.status === "circuit_breaker"
          ? payload.reason ?? prev?.breaker_reason ?? null
          : null,
    }));
    void qc.invalidateQueries({ queryKey: ["health"] });
  });

  return {
    status: status.data?.status ?? health.data?.system_status ?? "unknown",
    statusReason: status.data?.status_reason ?? "",
    dbOk: health.data?.database === "connected",
    stockSdk: health.data?.stock_sdk ?? "unknown",
    futuresSdk: health.data?.futures_sdk ?? "unknown",
    loading: health.isLoading || status.isLoading,
  };
}
