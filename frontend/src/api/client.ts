import { message } from "antd";

const BASE = "/api";

export interface ApiResp<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string; retryable: boolean; debug?: string } | null;
  correlation_id: string;
}

export type ApiRequestInit = RequestInit & {
  /** 后台轮询等预期可失败请求不触发全局浮动提示，由调用页面就地展示。 */
  silent?: boolean;
};

export function getApiErrorMessage(error: unknown, fallback = "请求失败"): string {
  if (error instanceof Error && error.message) return error.message;
  if (
    error &&
    typeof error === "object" &&
    "message" in error &&
    typeof error.message === "string"
  ) {
    return error.message;
  }
  return fallback;
}

export async function request<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const { silent = false, ...fetchInit } = init ?? {};
  const res = await fetch(`${BASE}${path}`, {
    ...fetchInit,
    headers: {
      "Content-Type": "application/json",
      ...(fetchInit.headers || {}),
    },
  });
  const body: ApiResp<T> = await res.json();
  if (!body.success) {
    const errMsg = body.error?.message ?? "请求失败";
    const detail = body.error?.debug ? `${errMsg}（${body.error.debug}）` : errMsg;
    if (!silent) message.error(detail);
    throw body.error ?? new Error("请求失败");
  }
  return body.data as T;
}

export const api = {
  get: <T>(path: string, init?: ApiRequestInit) =>
    request<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, data?: unknown, init?: ApiRequestInit) =>
    request<T>(path, { ...init, method: "POST", body: JSON.stringify(data ?? {}) }),
  put: <T>(path: string, data?: unknown, init?: ApiRequestInit) =>
    request<T>(path, { ...init, method: "PUT", body: JSON.stringify(data ?? {}) }),
  del: <T>(path: string, init?: ApiRequestInit) =>
    request<T>(path, { ...init, method: "DELETE" }),
  patch: <T>(path: string, data?: unknown, init?: ApiRequestInit) =>
    request<T>(path, { ...init, method: "PATCH", body: JSON.stringify(data ?? {}) }),
};
