import { message } from "antd";

const BASE = "/api";

export interface ApiResp<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string; retryable: boolean; debug?: string } | null;
  correlation_id: string;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const body: ApiResp<T> = await res.json();
  if (!body.success) {
    const errMsg = body.error?.message ?? "请求失败";
    const detail = body.error?.debug ? `${errMsg}（${body.error.debug}）` : errMsg;
    message.error(detail);
    throw body.error ?? new Error("请求失败");
  }
  return body.data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(data ?? {}) }),
  put: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(data ?? {}) }),
};
