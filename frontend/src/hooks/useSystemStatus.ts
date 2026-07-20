import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { HealthData, SystemStatus } from "../api/types";

export function useSystemStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthData>("/health"),
    refetchInterval: 10000,
  });
  const status = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api.get<SystemStatus>("/system/status"),
    refetchInterval: 10000,
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
