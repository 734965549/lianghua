import { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Form, Input, Row, Space, Tabs, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getApiErrorMessage } from "../api/client";
import type { SettingsData } from "../api/types";
import AiConfigPanel from "../components/AiConfigPanel";
import MarketDataConfigPanel from "../components/MarketDataConfigPanel";
import PageHeader from "../components/PageHeader";

export default function Settings() {
  const [brokerForm] = Form.useForm();
  const [runtimeForm] = Form.useForm();
  const qc = useQueryClient();
  const [passwordHint, setPasswordHint] = useState("");
  const [testState, setTestState] = useState<
    Record<string, { ok: boolean; testedAt: string; detail: string }>
  >({});

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsData>("/settings"),
  });

  useEffect(() => {
    if (!data) return;
    brokerForm.setFieldsValue({
      stock_path: data.stock_sdk.path ?? "",
      stock_account: data.stock_sdk.account_ref ?? "",
      futures_path: data.futures_sdk.path ?? "",
      futures_account: data.futures_sdk.account_ref ?? "",
    });
    runtimeForm.setFieldsValue({
      backup_dir: data.backup_dir ?? "",
    });
    setPasswordHint(
      data.stock_sdk.configured || data.futures_sdk.configured
        ? "已配置（不回显明文）"
        : "未配置"
    );
  }, [brokerForm, data, runtimeForm]);

  const saveBroker = useMutation({
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
      }),
    onSuccess: () => {
      message.success("交易通道配置已保存");
      brokerForm.setFieldValue("stock_password", "");
      brokerForm.setFieldValue("futures_password", "");
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  const saveRuntime = useMutation({
    mutationFn: (values: Record<string, string>) =>
      api.put<SettingsData>("/settings", { backup_dir: values.backup_dir }),
    onSuccess: () => {
      message.success("运行环境配置已保存");
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  const testDb = useMutation({
    mutationFn: async () => {
      const startedAt = performance.now();
      const result = await api.post<{ ok: boolean; server_version: string }>(
        "/settings/test-database",
        {},
      );
      return { ...result, latency_ms: Math.round(performance.now() - startedAt) };
    },
    onSuccess: (res) => {
      setTestState((state) => ({
        ...state,
        database: {
          ok: true,
          testedAt: new Date().toLocaleString("zh-CN", { hour12: false }),
          detail: `${res.latency_ms}ms · ${res.server_version}`,
        },
      }));
      message.success(`数据库连接成功：${res.server_version}`);
    },
    onError: (error) =>
      setTestState((state) => ({
        ...state,
        database: {
          ok: false,
          testedAt: new Date().toLocaleString("zh-CN", { hour12: false }),
          detail: getApiErrorMessage(error, "数据库连接失败"),
        },
      })),
  });

  const testSdk = useMutation({
    mutationFn: (market: string) =>
      api.post<{ ok: boolean; account_no: string; latency_ms: number }>("/settings/test-sdk", {
        market,
      }),
    onSuccess: (res, market) => {
      setTestState((state) => ({
        ...state,
        [market]: {
          ok: true,
          testedAt: new Date().toLocaleString("zh-CN", { hour12: false }),
          detail: `${res.latency_ms}ms · 账户 ${res.account_no}`,
        },
      }));
      message.success(`SDK 测试成功（账户 ${res.account_no}，延迟 ${res.latency_ms}ms）`);
    },
    onError: (error, market) =>
      setTestState((state) => ({
        ...state,
        [market]: {
          ok: false,
          testedAt: new Date().toLocaleString("zh-CN", { hour12: false }),
          detail: getApiErrorMessage(error, "SDK 连接失败"),
        },
      })),
  });

  const testNotice = (key: string) => {
    const result = testState[key];
    if (!result) {
      return <Alert type="info" showIcon title="尚未在本次会话中测试" />;
    }
    return (
      <Alert
        type={result.ok ? "success" : "error"}
        showIcon
        title={`最近测试：${result.testedAt}`}
        description={result.detail}
      />
    );
  };

  return (
    <div className="settings-page">
      <PageHeader
        eyebrow="SYSTEM / CONTROL PLANE"
        title="系统设置"
        description="集中管理 AI 分析引擎、交易通道与本地运行环境。敏感字段只在服务端加密保存。"
        meta={
          <span className={`status-chip ${data?.ai.configured ? "status-chip--success" : "status-chip--warning"}`}>
            AI {data?.ai.configured ? "ONLINE" : "OFFLINE"}
          </span>
        }
      />

      <Tabs
        defaultActiveKey="market-data"
        items={[
          {
            key: "market-data",
            label: "行情源",
            children: <MarketDataConfigPanel />,
          },
          {
            key: "ai",
            label: "AI",
            children: <AiConfigPanel />,
          },
          {
            key: "broker",
            label: "交易通道",
            children: (
              <Card className="settings-runtime-card" loading={isLoading} title="股票 / 期货 SDK">
                <Form
                  form={brokerForm}
                  layout="vertical"
                  onFinish={(values) => saveBroker.mutate(values)}
                >
                  <Row gutter={20}>
                    <Col xs={24} lg={12}>
                      <section className="settings-channel">
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
                        {testNotice("stock")}
                      </section>
                    </Col>
                    <Col xs={24} lg={12}>
                      <section className="settings-channel">
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
                        {testNotice("futures")}
                      </section>
                    </Col>
                  </Row>
                  <Space wrap style={{ marginTop: 16 }}>
                    <Button type="primary" htmlType="submit" loading={saveBroker.isPending}>
                      保存交易通道
                    </Button>
                    <Button onClick={() => testSdk.mutate("stock")} loading={testSdk.isPending}>
                      测试股票 SDK
                    </Button>
                    <Button onClick={() => testSdk.mutate("futures")} loading={testSdk.isPending}>
                      测试期货 SDK
                    </Button>
                  </Space>
                </Form>
              </Card>
            ),
          },
          {
            key: "runtime",
            label: "运行环境",
            children: (
              <Card className="settings-runtime-card" loading={isLoading} title="数据库与本地运行环境">
                <Form
                  form={runtimeForm}
                  layout="vertical"
                  onFinish={(values) => saveRuntime.mutate(values)}
                >
                  <Form.Item name="backup_dir" label="备份目录" className="settings-backup-field">
                    <Input />
                  </Form.Item>
                  {testNotice("database")}
                  <Space wrap style={{ marginTop: 16 }}>
                    <Button type="primary" htmlType="submit" loading={saveRuntime.isPending}>
                      保存运行环境
                    </Button>
                    <Button onClick={() => testDb.mutate()} loading={testDb.isPending}>
                      测试数据库
                    </Button>
                  </Space>
                </Form>
                {data && (
                  <Typography.Paragraph className="settings-runtime-meta">
                    数据库：{data.database.host}:{data.database.port}/{data.database.dbname} · SDK 模式：
                    {data.sdk_mode ?? "mock"}
                  </Typography.Paragraph>
                )}
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
