import { useEffect, useState } from "react";
import {
  ApiOutlined,
  CheckCircleFilled,
  CloudServerOutlined,
  KeyOutlined,
  RadarChartOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Space,
  Tag,
  Typography,
} from "antd";
import { api, getApiErrorMessage } from "../api/client";
import type { SettingsData } from "../api/types";

type ProviderId =
  | "ifind"
  | "tdx"
  | "akshare"
  | "tushare_pro"
  | "rqdata"
  | "wind"
  | "mock";

type MarketDataValues = {
  provider: ProviderId;
  akshare_poll_seconds?: number;
  tdx_endpoint?: string;
  tdx_poll_seconds?: number;
  ifind_username?: string;
  ifind_password?: string;
  ifind_poll_seconds?: number;
  tushare_token?: string;
  tushare_poll_seconds?: number;
  rqdata_username?: string;
  rqdata_password?: string;
  rqdata_poll_seconds?: number;
  wind_poll_seconds?: number;
};

type MarketDataTestResult = {
  ok: boolean;
  provider: string;
  realtime: boolean;
  message?: string;
  sample_symbol?: string;
  sample_price?: string;
  quote_time?: string;
  latency_ms?: number;
};

type Props = {
  onSaved?: () => void;
};

const FALLBACK_PROVIDERS = [
  {
    id: "ifind",
    label: "同花顺 iFinD",
    tier: "专业",
    coverage: "股票 · 期货",
    mode: "实时",
    description: "官方接口与全市场目录。",
    component_installed: true,
  },
  {
    id: "tdx",
    label: "通达信 TQ",
    tier: "免费接入",
    coverage: "股票 · 期货",
    mode: "准实时",
    description: "连接本机 TQ HTTP 服务。",
    component_installed: true,
  },
  {
    id: "akshare",
    label: "AKShare 聚合",
    tier: "免费",
    coverage: "股票 · 期货",
    mode: "轮询",
    description: "免密钥公开数据聚合。",
    component_installed: true,
  },
  {
    id: "tushare_pro",
    label: "Tushare Pro",
    tier: "免费注册",
    coverage: "股票 · 期货",
    mode: "日频/分钟",
    description: "Token 与积分权限。",
    component_installed: false,
  },
  {
    id: "rqdata",
    label: "RQData",
    tier: "授权",
    coverage: "股票 · 期货",
    mode: "轮询",
    description: "米筐统一行情接口。",
    component_installed: false,
  },
  {
    id: "wind",
    label: "Wind",
    tier: "专业",
    coverage: "股票 · 期货",
    mode: "实时",
    description: "连接本机 Wind 终端。",
    component_installed: false,
  },
  {
    id: "mock",
    label: "Mock 模拟行情",
    tier: "内置",
    coverage: "股票 · 期货",
    mode: "模拟",
    description: "离线演示和开发。",
    component_installed: true,
  },
];

function toPayload(values: MarketDataValues) {
  return {
    ...values,
    ifind_username: values.ifind_username?.trim() ?? "",
    ...(values.ifind_password
      ? { ifind_password: values.ifind_password }
      : {}),
    tdx_endpoint:
      values.tdx_endpoint?.trim() || "http://127.0.0.1:17709/",
    ...(values.tushare_token
      ? { tushare_token: values.tushare_token.trim() }
      : {}),
    rqdata_username: values.rqdata_username?.trim() ?? "",
    ...(values.rqdata_password
      ? { rqdata_password: values.rqdata_password }
      : {}),
    sample_symbol: "600000.SH",
  };
}

export default function MarketDataConfigPanel({ onSaved }: Props) {
  const [form] = Form.useForm<MarketDataValues>();
  const qc = useQueryClient();
  const [saveStage, setSaveStage] = useState<"testing" | "saving" | null>(
    null,
  );
  const [testResult, setTestResult] = useState<MarketDataTestResult | null>(
    null,
  );
  const [testError, setTestError] = useState<string | null>(null);
  const [testedAt, setTestedAt] = useState<string | null>(null);
  const provider = (Form.useWatch("provider", form) ?? "ifind") as ProviderId;

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsData>("/settings"),
  });

  const providers = data?.market_data?.providers ?? FALLBACK_PROVIDERS;
  const selectedProvider = providers.find((item) => item.id === provider);
  const componentReady = selectedProvider?.component_installed !== false;
  const configured = Boolean(
    data?.market_data?.provider === provider && data.market_data.configured,
  );

  useEffect(() => {
    if (!data) return;
    form.setFieldsValue({
      provider: (data.market_data?.provider as ProviderId) ?? "mock",
      akshare_poll_seconds:
        data.market_data?.akshare_poll_seconds ?? 10,
      tdx_endpoint:
        data.market_data?.tdx_endpoint ?? "http://127.0.0.1:17709/",
      tdx_poll_seconds: data.market_data?.tdx_poll_seconds ?? 3,
      ifind_username: data.market_data?.ifind_username_ref ?? "",
      ifind_password: "",
      ifind_poll_seconds: data.market_data?.ifind_poll_seconds ?? 3,
      tushare_token: "",
      tushare_poll_seconds:
        data.market_data?.tushare_poll_seconds ?? 10,
      rqdata_username: data.market_data?.rqdata_username_ref ?? "",
      rqdata_password: "",
      rqdata_poll_seconds: data.market_data?.rqdata_poll_seconds ?? 5,
      wind_poll_seconds: data.market_data?.wind_poll_seconds ?? 5,
    });
  }, [data, form]);

  useEffect(() => {
    setTestResult(null);
    setTestError(null);
    setTestedAt(null);
  }, [provider]);

  const test = useMutation({
    mutationFn: (values: MarketDataValues) =>
      api.post<MarketDataTestResult>("/settings/test-market-data", {
        market_data: toPayload(values),
      }, {
        signal: AbortSignal.timeout(35_000),
        silent: true,
      }),
    onMutate: () => {
      setTestResult(null);
      setTestError(null);
    },
    onSuccess: (result) => {
      setTestedAt(new Date().toLocaleString("zh-CN", { hour12: false }));
      setTestResult(result);
      setTestError(result.ok ? null : result.message ?? "行情源连接测试未通过");
    },
    onError: (error) => {
      setTestedAt(new Date().toLocaleString("zh-CN", { hour12: false }));
      setTestResult(null);
      setTestError(getApiErrorMessage(error, "行情源连接测试未通过"));
    },
  });

  const save = useMutation({
    mutationFn: async (values: MarketDataValues) => {
      if (values.provider !== "mock") {
        setSaveStage("testing");
        const result = await api.post<MarketDataTestResult>(
          "/settings/test-market-data",
          {
            market_data: toPayload(values),
          },
          {
            signal: AbortSignal.timeout(35_000),
            silent: true,
          },
        );
        setTestedAt(new Date().toLocaleString("zh-CN", { hour12: false }));
        setTestResult(result);
        if (!result.ok) {
          throw new Error(result.message ?? "行情源连接测试未通过");
        }
      }
      setSaveStage("saving");
      return api.put<SettingsData>("/settings", {
        market_data: toPayload(values),
      }, {
        signal: AbortSignal.timeout(20_000),
        silent: true,
      });
    },
    onMutate: () => {
      setTestResult(null);
      setTestError(null);
    },
    onSuccess: (next) => {
      setTestedAt(new Date().toLocaleString("zh-CN", { hour12: false }));
      if (next.market_data?.provider === "mock") {
        setTestResult({
          ok: true,
          provider: "mock",
          realtime: false,
          message: "模拟行情已启用，无需连接外部源站。",
        });
      }
      setTestError(null);
      form.setFieldsValue({
        ifind_password: "",
        tushare_token: "",
        rqdata_password: "",
      });
      qc.setQueryData(["settings"], next);
      void qc.invalidateQueries({ queryKey: ["settings"] });
      void qc.invalidateQueries({ queryKey: ["quotes"] });
      void qc.invalidateQueries({ queryKey: ["quote"] });
      void qc.invalidateQueries({ queryKey: ["instruments"] });
      onSaved?.();
    },
    onError: (error) => {
      setTestedAt(new Date().toLocaleString("zh-CN", { hour12: false }));
      if (
        error instanceof DOMException &&
        (error.name === "AbortError" || error.name === "TimeoutError")
      ) {
        setTestError("行情源切换超时，请检查源站网络后重试");
      } else {
        setTestError(getApiErrorMessage(error, "行情源验证或启用失败"));
      }
    },
    onSettled: () => setSaveStage(null),
  });

  const validatePassword = (
    configuredFlag: boolean | undefined,
    label: string,
  ) => (_: unknown, value?: string) =>
    configuredFlag || value
      ? Promise.resolve()
      : Promise.reject(new Error(`首次接入请填写${label}`));

  const validateAndTest = async () => {
    try {
      const values = await form.validateFields();
      test.mutate(values);
    } catch {
      // 字段错误由 Form 就地展示。
    }
  };

  const pollField = (
    {
      ifind: "ifind_poll_seconds",
      tdx: "tdx_poll_seconds",
      akshare: "akshare_poll_seconds",
      tushare_pro: "tushare_poll_seconds",
      rqdata: "rqdata_poll_seconds",
      wind: "wind_poll_seconds",
    } as Partial<Record<ProviderId, keyof MarketDataValues>>
  )[provider];
  const testDescription = testResult
    ? [
        testResult.sample_symbol
          ? `样本 ${testResult.sample_symbol} · ${testResult.sample_price ?? "暂无价格"}`
          : null,
        testResult.latency_ms !== undefined
          ? `延迟 ${testResult.latency_ms}ms`
          : null,
        testResult.message,
        testedAt ? `最近测试 ${testedAt}` : null,
      ]
        .filter(Boolean)
        .join("；")
    : "";

  return (
    <Card
      className={`market-data-config-card${configured ? " market-data-config-card--ready" : ""}`}
      loading={isLoading}
      title={
        <div className="panel-title">
          <div className="panel-title__copy">
            <i />
            <strong>多源行情接入</strong>
            <small>MARKET DATA ROUTER</small>
          </div>
          <span
            className={`status-chip ${
              configured ? "status-chip--success" : "status-chip--warning"
            }`}
          >
            {configured
              ? `${selectedProvider?.label ?? provider} 已启用`
              : "等待配置"}
          </span>
        </div>
      }
    >
      <div className="market-data-intro">
        <div className="market-data-intro__icon">
          {configured ? <CheckCircleFilled /> : <RadarChartOutlined />}
        </div>
        <div>
          <strong>按场景选择行情源，不把“免费”误标成交易级数据</strong>
          <p>
            免费源适合研究和看盘；实盘策略建议保留 iFinD、Wind
            等授权源，并通过连接测试确认延迟。
          </p>
        </div>
        <div className="market-data-security">
          <SafetyCertificateOutlined />
          CREDENTIALS ENCRYPTED
        </div>
      </div>

      <Form<MarketDataValues>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => save.mutate(values)}
      >
        <Form.Item name="provider" hidden>
          <Input />
        </Form.Item>

        <div className="market-provider-grid">
          {providers.map((item) => {
            const active = item.id === provider;
            return (
              <button
                key={item.id}
                type="button"
                className={`market-provider-card${active ? " is-active" : ""}`}
                onClick={() =>
                  form.setFieldValue("provider", item.id as ProviderId)
                }
              >
                <span className="market-provider-card__top">
                  <strong>{item.label}</strong>
                  <Tag color={item.tier.includes("免费") ? "green" : undefined}>
                    {item.tier}
                  </Tag>
                </span>
                <span>{item.description}</span>
                <small>
                  {item.coverage} · {item.mode}
                  {!item.component_installed ? " · 组件未安装" : ""}
                </small>
              </button>
            );
          })}
        </div>

        {!componentReady ? (
          <Alert
            type="warning"
            showIcon
            title={`${selectedProvider?.label ?? provider} 本地组件尚未安装`}
            description="配置入口已经开放；安装对应官方 Python 组件或客户端后即可测试并启用。"
            style={{ marginBottom: 14 }}
          />
        ) : null}

        <div className="market-provider-config">
          <Row gutter={12}>
            {provider === "ifind" ? (
              <>
                <Col span={12}>
                  <Form.Item
                    name="ifind_username"
                    label="iFinD 接口账号"
                    rules={[{ required: true, message: "请填写接口账号" }]}
                  >
                    <Input
                      prefix={<UserOutlined />}
                      placeholder="iFinD 数据接口账号"
                      autoComplete="username"
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="ifind_password"
                    label="iFinD 接口密码"
                    rules={[
                      {
                        validator: validatePassword(
                          data?.market_data?.ifind_credentials_configured,
                          " iFinD 密码",
                        ),
                      },
                    ]}
                  >
                    <Input.Password
                      prefix={<KeyOutlined />}
                      placeholder={
                        data?.market_data?.ifind_credentials_configured
                          ? "••••••••  已安全保存"
                          : "请输入接口密码"
                      }
                      autoComplete="new-password"
                    />
                  </Form.Item>
                </Col>
              </>
            ) : null}

            {provider === "tdx" ? (
              <Col span={24}>
                <Form.Item
                  name="tdx_endpoint"
                  label="通达信 TQ 本地地址"
                  extra="先启动支持 TQ 的通达信客户端，并开启本地 HTTP 服务。"
                  rules={[
                    { required: true, message: "请填写 TQ 本地接口地址" },
                    { type: "url", message: "请输入完整的 HTTP 地址" },
                  ]}
                >
                  <Input
                    prefix={<CloudServerOutlined />}
                    placeholder="http://127.0.0.1:17709/"
                  />
                </Form.Item>
              </Col>
            ) : null}

            {provider === "tushare_pro" ? (
              <Col span={24}>
                <Form.Item
                  name="tushare_token"
                  label="Tushare Token"
                  rules={[
                    {
                      validator: validatePassword(
                        data?.market_data?.tushare_token_configured,
                        " Tushare Token",
                      ),
                    },
                  ]}
                >
                  <Input.Password
                    prefix={<KeyOutlined />}
                    placeholder={
                      data?.market_data?.tushare_token_configured
                        ? "••••••••  已安全保存"
                        : "请输入个人 Token"
                    }
                  />
                </Form.Item>
              </Col>
            ) : null}

            {provider === "rqdata" ? (
              <>
                <Col span={12}>
                  <Form.Item
                    name="rqdata_username"
                    label="RQData 账号"
                    rules={[{ required: true, message: "请填写 RQData 账号" }]}
                  >
                    <Input prefix={<UserOutlined />} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="rqdata_password"
                    label="RQData 密码"
                    rules={[
                      {
                        validator: validatePassword(
                          data?.market_data?.rqdata_credentials_configured,
                          " RQData 密码",
                        ),
                      },
                    ]}
                  >
                    <Input.Password
                      prefix={<KeyOutlined />}
                      placeholder={
                        data?.market_data?.rqdata_credentials_configured
                          ? "••••••••  已安全保存"
                          : "请输入密码"
                      }
                    />
                  </Form.Item>
                </Col>
              </>
            ) : null}

            {provider === "akshare" ? (
              <Col span={24}>
                <Alert
                  type="success"
                  showIcon
                  title="免账号、免密钥"
                  description="数据来自公开财经网站，源站限流或结构调整时可能短暂不可用，不建议单独作为自动实盘的唯一行情源。"
                  style={{ marginBottom: 12 }}
                />
              </Col>
            ) : null}

            {provider === "wind" ? (
              <Col span={24}>
                <Alert
                  type="info"
                  showIcon
                  title="使用本机 Wind 终端授权"
                  description="无需在网页填写账号密码，但必须已登录 Wind 终端并安装 WindPy。"
                  style={{ marginBottom: 12 }}
                />
              </Col>
            ) : null}

            {provider === "mock" ? (
              <Col span={24}>
                <Alert
                  type="info"
                  showIcon
                  title="模拟行情不会连接外部市场"
                  description="适合功能演示、策略开发和离线验证。"
                  style={{ marginBottom: 12 }}
                />
              </Col>
            ) : null}

            {pollField ? (
              <Col span={8}>
                <Form.Item
                  name={pollField}
                  label="刷新周期"
                  extra={
                    provider === "akshare"
                      ? "建议不少于 10 秒，降低公开源限流风险。"
                      : "周期越短，接口调用量越高。"
                  }
                >
                  <InputNumber
                    min={1}
                    max={120}
                    suffix="秒"
                    style={{ width: "100%" }}
                  />
                </Form.Item>
              </Col>
            ) : null}
          </Row>
        </div>

        <Alert
          type="warning"
          showIcon
          title="关于文华财经赢顺"
          description="赢顺属于交易客户端；在没有厂商或期货公司授权行情接口的情况下，本系统不采用抓包、注入或网页爬取方式接入。拿到正式 API 后可沿用本行情路由直接新增。"
          style={{ marginBottom: 14 }}
        />

        {test.isPending || saveStage === "testing" ? (
          <Alert
            type="info"
            showIcon
            title={`正在验证 ${selectedProvider?.label ?? provider}`}
            description="正在读取单个样本行情，不会触发全市场下载。"
            style={{ marginBottom: 14 }}
          />
        ) : saveStage === "saving" ? (
          <Alert
            type="info"
            showIcon
            title="连接验证已通过，正在启用"
            description={testDescription || "正在保存配置并恢复后台订阅。"}
            style={{ marginBottom: 14 }}
          />
        ) : testError ? (
          <Alert
            type="error"
            showIcon
            title={`${selectedProvider?.label ?? provider} 验证未通过`}
            description={`${testError}${testedAt ? `；最近测试 ${testedAt}` : ""}`}
            style={{ marginBottom: 14 }}
          />
        ) : testResult?.ok ? (
          <Alert
            type="success"
            showIcon
            title={`${selectedProvider?.label ?? provider} ${
              configured ? "验证通过并已启用" : "连接测试通过"
            }`}
            description={testDescription || "行情源连接正常。"}
            style={{ marginBottom: 14 }}
          />
        ) : configured ? (
          <Alert
            type="success"
            showIcon
            title={`${selectedProvider?.label ?? provider} 当前已启用`}
            description="配置已生效；如需重新确认源站连通性，请点击“测试连接”。"
            style={{ marginBottom: 14 }}
          />
        ) : null}

        <Space wrap>
          <Button
            type="primary"
            htmlType="submit"
            loading={save.isPending}
            disabled={!componentReady || test.isPending}
          >
            {saveStage === "testing"
              ? "正在验证单股行情"
              : saveStage === "saving"
                ? "正在启用，订阅后台恢复"
                : provider === "mock"
                  ? "启用模拟行情"
                  : "验证并启用"}
          </Button>
          <Button
            icon={<ApiOutlined />}
            loading={test.isPending}
            onClick={() => void validateAndTest()}
            disabled={!componentReady || save.isPending}
          >
            {testResult?.ok ? "重新测试" : "测试连接"}
          </Button>
          <Typography.Text className="market-data-config-hint">
            保存成功后立即返回，行情热重连与订阅恢复在后台完成。
          </Typography.Text>
        </Space>
      </Form>
    </Card>
  );
}
