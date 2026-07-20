import { useEffect, useState } from "react";
import { Button, Card, Form, Input, Space, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SettingsData } from "../api/types";

export default function Settings() {
  const [form] = Form.useForm();
  const qc = useQueryClient();
  const [passwordHint, setPasswordHint] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsData>("/settings"),
  });

  useEffect(() => {
    if (!data) return;
    form.setFieldsValue({
      stock_path: data.stock_sdk.path ?? "",
      stock_account: data.stock_sdk.account_ref ?? "",
      futures_path: data.futures_sdk.path ?? "",
      futures_account: data.futures_sdk.account_ref ?? "",
      backup_dir: data.backup_dir ?? "",
      ai_provider: data.ai.provider ?? "",
    });
    setPasswordHint(
      data.stock_sdk.configured || data.futures_sdk.configured
        ? "已配置（不回显明文）"
        : "未配置"
    );
  }, [data, form]);

  const save = useMutation({
    mutationFn: (values: Record<string, string>) =>
      api.put<SettingsData>("/settings", {
        stock_sdk: {
          path: values.stock_path,
          account: values.stock_account,
          ...(values.stock_password ? { password: values.stock_password } : {}),
        },
        futures_sdk: {
          path: values.futures_path,
          account: values.futures_account,
          ...(values.futures_password ? { password: values.futures_password } : {}),
        },
        backup_dir: values.backup_dir,
        ai: { provider: values.ai_provider },
      }),
    onSuccess: () => {
      message.success("配置已保存");
      form.setFieldValue("stock_password", "");
      form.setFieldValue("futures_password", "");
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  const testDb = useMutation({
    mutationFn: () => api.post<{ ok: boolean; server_version: string }>("/settings/test-database", {}),
    onSuccess: (res) => message.success(`数据库连接成功：${res.server_version}`),
  });

  const testSdk = useMutation({
    mutationFn: (market: string) =>
      api.post<{ ok: boolean; account_no: string; latency_ms: number }>("/settings/test-sdk", {
        market,
      }),
    onSuccess: (res) =>
      message.success(`SDK 测试成功（账户 ${res.account_no}，延迟 ${res.latency_ms}ms）`),
  });

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        系统设置
      </Typography.Title>
      <Card loading={isLoading}>
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => save.mutate(values)}
          style={{ maxWidth: 720 }}
        >
          <Typography.Title level={5}>股票 SDK</Typography.Title>
          <Form.Item name="stock_path" label="SDK 路径">
            <Input placeholder="C:/ths/stock_sdk" />
          </Form.Item>
          <Form.Item name="stock_account" label="账号标识">
            <Input />
          </Form.Item>
          <Form.Item
            name="stock_password"
            label="密码"
            extra={`敏感字段：${passwordHint}。留空表示不修改。`}
          >
            <Input.Password placeholder="不回显明文" autoComplete="new-password" />
          </Form.Item>

          <Typography.Title level={5}>期货 SDK</Typography.Title>
          <Form.Item name="futures_path" label="SDK 路径">
            <Input placeholder="C:/ths/futures_sdk" />
          </Form.Item>
          <Form.Item name="futures_account" label="账号标识">
            <Input />
          </Form.Item>
          <Form.Item name="futures_password" label="密码" extra="留空表示不修改">
            <Input.Password placeholder="不回显明文" autoComplete="new-password" />
          </Form.Item>

          <Typography.Title level={5}>其他</Typography.Title>
          <Form.Item name="backup_dir" label="备份目录">
            <Input />
          </Form.Item>
          <Form.Item name="ai_provider" label="AI Provider">
            <Input placeholder="留空则规则化报告" />
          </Form.Item>

          <Space wrap>
            <Button type="primary" htmlType="submit" loading={save.isPending}>
              保存配置
            </Button>
            <Button onClick={() => testDb.mutate()} loading={testDb.isPending}>
              测试数据库
            </Button>
            <Button onClick={() => testSdk.mutate("stock")} loading={testSdk.isPending}>
              测试股票 SDK
            </Button>
            <Button onClick={() => testSdk.mutate("futures")} loading={testSdk.isPending}>
              测试期货 SDK
            </Button>
          </Space>
        </Form>
        {data && (
          <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
            数据库：{data.database.host}:{data.database.port}/{data.database.dbname} · SDK 模式：
            {data.sdk_mode ?? "mock"}
          </Typography.Paragraph>
        )}
      </Card>
    </div>
  );
}
