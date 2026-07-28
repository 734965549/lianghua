import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import type { DashboardData, HealthData, Paged, SystemStatus } from "./types";

export function useHealth(refetchInterval = 10000) {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthData>("/health"),
    refetchInterval,
  });
}

export function useDashboard(refetchInterval = 10000) {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardData>("/dashboard"),
    refetchInterval,
  });
}

export function useSystemStatusQuery(refetchInterval = 10000) {
  return useQuery({
    queryKey: ["system-status"],
    queryFn: () => api.get<SystemStatus>("/system/status"),
    refetchInterval,
  });
}

export function useOrders<T = Record<string, unknown>>(
  page = 1,
  pageSize = 50,
  refetchInterval = 8000,
) {
  return useQuery({
    queryKey: ["orders", page, pageSize],
    queryFn: () =>
      api.get<Paged<T>>(`/orders?page=${page}&page_size=${pageSize}`),
    refetchInterval,
  });
}
