import { useEffect, useState } from "react";
import {
  ApiOutlined,
  CheckCircleFilled,
  CloudServerOutlined,
  KeyOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Typography, message } from "antd";
import { api, getApiErrorMessage } from "../api/client";
import type { SettingsData } from "../api/types";

type AiConfigValues = {
  ai_provider: string;
  ai_api_key?: string;
  ai_base_url?: string;
  ai_model: string;
};

type AiTestResult = {
  ok: boolean;
  provider: string;
  model: string;
  model_available: boolean;
  latency_ms: number;
};

function toPayload(values: AiConfigValues) {
  return {
    provider: values.ai_provider,
    ...(values.ai_api_key ? { api_key: values.ai_api_key.trim() } : {}),
    base_url: values.ai_base_url?.trim() ?? "",
    model: values.ai_model?.trim() || "gpt-4o-mini",
  };
}

export default function AiConfigPanel() {
  const [form] = Form.useForm<AiConfigValues>();
  const qc = useQueryClient();
  const [testStatus, setTestStatus] = useState<{
    ok: boolean;
    testedAt: string;
    detail: string;
  } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsData>("/settings"),
  });

  useEffect(() => {
    if (!data) return;
    form.setFieldsValue({
      ai_provider: data.ai.provider || "openai",
      ai_api_key: "",
      ai_base_url: data.ai.base_url ?? "",
      ai_model: data.ai.model || "gpt-4o-mini",
    });
  }, [data, form]);

  const save = useMutation({
    mutationFn: (values: AiConfigValues) =>
      api.put<SettingsData>("/settings", { ai: toPayload(values) }),
    onSuccess: (next) => {
      message.success("AI 接入配置已加密保存，立即生效");
      form.setFieldValue("ai_api_key", "");
      qc.setQueryData(["settings"], next);
      void qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const test = useMutation({
    mutationFn: (values: AiConfigValues) =>
      api.post<AiTestResult>("/settings/test-ai", { ai: toPayload(values) }),
    onSuccess: (result) => {
      const modelTip = result.model_available ? "模型可用" : "鉴权成功，模型未出现在模型列表中";
      setTestStatus({
        ok: result.ok,
        testedAt: new Date().toLocaleString("zh-CN", { hour12: false }),
        detail: `${result.latency_ms}ms · ${modelTip}`,
      });
      message.success(`连接成功 · ${result.latency_ms}ms · ${modelTip}`);
    },
    onError: (error) =>
      setTestStatus({
        ok: false,
        testedAt: new Date().toLocaleString("zh-CN", { hour12: false }),
        detail: getApiErrorMessage(error, "AI 连接测试失败"),
      }),
  });

  const validateApiKey = (_: unknown, value?: string) => {
    if (data?.ai.configured || value?.trim()) return Promise.resolve();
    return Promise.reject(new Error("首次接入请填写 API Key"));
  };

  const runTest = async () => {
    try {
      const values = await form.validateFields();
      test.mutate(values);
    } catch {
      // Ant Design 已在字段下展示校验信息，无需再抛出未处理异常。
    }
  };

  const configured = Boolean(data?.ai.configured);

  return (
    <Card
      className={`ai-config-card${configured ? " ai-config-card--ready" : ""}`}
      loading={isLoading}
      title={
        <div className="panel-title">
          <div className="panel-title__copy">
            <i />
            <strong>AI 分析引擎</strong>
            <small>OPENAI-COMPATIBLE RUNTIME</small>
          </div>
          <span className={`status-chip ${configured ? "status-chip--success" : "status-chip--warning"}`}>
            {configured ? "已接入" : "等待配置"}
          </span>
        </div>
      }
    >
      <div className="ai-config-intro">
        <div className="ai-config-intro__icon">
          {configured ? <CheckCircleFilled /> : <ApiOutlined />}
        </div>
        <div>
          <strong>{configured ? "AI 复盘已启用" : "连接你的大模型"}</strong>
          <p>
            支持 OpenAI 及兼容接口。API Key 只在服务端加密保存、不回显，调用时仅用于目标 AI 服务鉴权。
          </p>
        </div>
        <div className="ai-config-security">
          <SafetyCertificateOutlined />
          SERVER-SIDE ENCRYPTED
        </div>
      </div>

      <Form<AiConfigValues>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => save.mutate(values)}
      >
        <Row gutter={12}>
          <Col span={6}>
            <Form.Item
              name="ai_provider"
              label="服务协议"
              rules={[{ required: true, message: "请选择服务协议" }]}
            >
              <Select
                options={[
                  { value: "openai", label: "OpenAI / 兼容接口" },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item
              name="ai_model"
              label="模型名称"
              rules={[{ required: true, message: "请填写模型名称" }]}
            >
              <Input prefix={<CloudServerOutlined />} placeholder="gpt-4o-mini" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="ai_base_url"
              label="API Base URL"
              extra="OpenAI 官方接口可留空；兼容服务填写其 /v1 地址。"
            >
              <Input prefix={<ApiOutlined />} placeholder="https://api.openai.com/v1" />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          name="ai_api_key"
          label="API Key"
          extra={configured ? "Key 已保存。留空表示继续使用当前 Key；填写新值会覆盖。" : "首次接入必须填写。"}
          rules={[{ validator: validateApiKey }]}
        >
          <Input.Password
            prefix={<KeyOutlined />}
            placeholder={configured ? "••••••••••••••••  已安全保存" : "sk-..."}
            autoComplete="new-password"
          />
        </Form.Item>

        <Space wrap>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            保存并启用
          </Button>
          <Button
            icon={<ApiOutlined />}
            loading={test.isPending}
            onClick={() => void runTest()}
          >
            测试连接
          </Button>
          <Typography.Text className="ai-config-hint">
            配置保存后无需重启，下一份复盘报告立即使用新模型。
          </Typography.Text>
        </Space>
        {testStatus ? (
          <Alert
            type={testStatus.ok ? "success" : "error"}
            showIcon
            title={`最近测试：${testStatus.testedAt}`}
            description={testStatus.detail}
            style={{ marginTop: 14 }}
          />
        ) : null}
      </Form>
    </Card>
  );
}
