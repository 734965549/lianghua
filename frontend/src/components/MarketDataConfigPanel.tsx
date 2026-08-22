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
  | "tqsdk"
  | "mock";

type MarketDataValues = {
  provider: ProviderId;
  stock_provider: ProviderId;
  futures_provider: ProviderId;
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
  tqsdk_auth_user?: string;
  tqsdk_auth_password?: string;
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
    id: "tqsdk",
    label: "天勤 TqSdk",
    tier: "免费实时",
    coverage: "期货专用",
    mode: "实时",
    description: "快期免费实时期货行情。",
    component_installed: true,
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

const FUTURES_ONLY = new Set<ProviderId>(["tqsdk"]);

function toPayload(values: MarketDataValues, testMarket?: "stock" | "futures") {
  const sampleSymbol =
    testMarket === "futures" || values.futures_provider === "tqsdk"
      ? "RB0"
      : "600000.SH";
  return {
    ...values,
    provider: values.stock_provider,
    stock_provider: values.stock_provider,
    futures_provider: values.futures_provider,
    ifind_username: values.ifind_username?.trim() ?? "",
    ...(values.ifind_password ? { ifind_password: values.ifind_password } : {}),
    tdx_endpoint: values.tdx_endpoint?.trim() || "http://127.0.0.1:17709/",
    ...(values.tushare_token
      ? { tushare_token: values.tushare_token.trim() }
      : {}),
    rqdata_username: values.rqdata_username?.trim() ?? "",
    ...(values.rqdata_password
      ? { rqdata_password: values.rqdata_password }
      : {}),
    tqsdk_auth_user: values.tqsdk_auth_user?.trim() ?? "",
    ...(values.tqsdk_auth_password
      ? { tqsdk_auth_password: values.tqsdk_auth_password }
      : {}),
    sample_symbol: sampleSymbol,
    ...(testMarket ? { test_market: testMarket } : {}),
  };
}

function ProviderGrid({
  title,
  providers,
  activeId,
  onSelect,
}: {
  title: string;
  providers: typeof FALLBACK_PROVIDERS;
  activeId: ProviderId;
  onSelect: (id: ProviderId) => void;
}) {
  return (
    <div className="market-provider-section">
      <Typography.Text strong>{title}</Typography.Text>
      <div className="market-provider-grid" style={{ marginTop: 8 }}>
        {providers.map((item) => {
          const active = item.id === activeId;
          return (
            <button
              key={`${title}-${item.id}`}
              type="button"
              className={`market-provider-card${active ? " is-active" : ""}`}
              onClick={() => onSelect(item.id as ProviderId)}
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
    </div>
  );
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
  const stockProvider = (Form.useWatch("stock_provider", form) ??
    "akshare") as ProviderId;
  const futuresProvider = (Form.useWatch("futures_provider", form) ??
    "mock") as ProviderId;

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<SettingsData>("/settings"),
  });

  const providers = data?.market_data?.providers ?? FALLBACK_PROVIDERS;
  const stockProviders = providers.filter(
    (item) => !FUTURES_ONLY.has(item.id as ProviderId),
  );
  const futuresProviders = providers;
  const selectedFutures = providers.find((item) => item.id === futuresProvider);
  const selectedStock = providers.find((item) => item.id === stockProvider);
  const needsTqsdk =
    stockProvider === "tqsdk" || futuresProvider === "tqsdk";
  const needsIfind =
    stockProvider === "ifind" || futuresProvider === "ifind";
  const needsTdx = stockProvider === "tdx" || futuresProvider === "tdx";
  const needsTushare =
    stockProvider === "tushare_pro" || futuresProvider === "tushare_pro";
  const needsRqdata =
    stockProvider === "rqdata" || futuresProvider === "rqdata";
  const needsAkshare =
    stockProvider === "akshare" || futuresProvider === "akshare";
  const needsWind =
    stockProvider === "wind" || futuresProvider === "wind";
  const componentReady =
    (selectedStock?.component_installed !== false) &&
    (selectedFutures?.component_installed !== false);
  const configured = Boolean(
    data?.market_data?.stock_configured &&
      data?.market_data?.futures_configured,
  );

  useEffect(() => {
    if (!data) return;
    const stock =
      (data.market_data?.stock_provider as ProviderId) ||
      (data.market_data?.provider as ProviderId) ||
      "mock";
    const futures =
      (data.market_data?.futures_provider as ProviderId) ||
      (data.market_data?.provider as ProviderId) ||
      "mock";
    form.setFieldsValue({
      provider: stock,
      stock_provider: stock,
      futures_provider: futures,
      akshare_poll_seconds: data.market_data?.akshare_poll_seconds ?? 10,
      tdx_endpoint:
        data.market_data?.tdx_endpoint ?? "http://127.0.0.1:17709/",
      tdx_poll_seconds: data.market_data?.tdx_poll_seconds ?? 3,
      ifind_username: data.market_data?.ifind_username_ref ?? "",
      ifind_password: "",
      ifind_poll_seconds: data.market_data?.ifind_poll_seconds ?? 3,
      tushare_token: "",
      tushare_poll_seconds: data.market_data?.tushare_poll_seconds ?? 10,
      rqdata_username: data.market_data?.rqdata_username_ref ?? "",
      rqdata_password: "",
      rqdata_poll_seconds: data.market_data?.rqdata_poll_seconds ?? 5,
      wind_poll_seconds: data.market_data?.wind_poll_seconds ?? 5,
      tqsdk_auth_user: data.market_data?.tqsdk_auth_user_ref ?? "",
      tqsdk_auth_password: "",
    });
  }, [data, form]);

  useEffect(() => {
    setTestResult(null);
    setTestError(null);
    setTestedAt(null);
  }, [stockProvider, futuresProvider]);

  const test = useMutation({
    mutationFn: async (values: MarketDataValues) => {
      const results: MarketDataTestResult[] = [];
      if (values.stock_provider !== "mock") {
        results.push(
          await api.post<MarketDataTestResult>(
            "/settings/test-market-data",
            { market_data: toPayload(values, "stock") },
            { signal: AbortSignal.timeout(35_000), silent: true },
          ),
        );
      }
      if (values.futures_provider !== "mock") {
        results.push(
          await api.post<MarketDataTestResult>(
            "/settings/test-market-data",
            { market_data: toPayload(values, "futures") },
            { signal: AbortSignal.timeout(35_000), silent: true },
          ),
        );
      }
      if (!results.length) {
        return {
          ok: true,
          provider: "mock",
          realtime: false,
          message: "模拟行情已启用，无需连接外部源站。",
        } satisfies MarketDataTestResult;
      }
      return results[results.length - 1];
    },
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
      if (values.stock_provider !== "mock" || values.futures_provider !== "mock") {
        setSaveStage("testing");
        await test.mutateAsync(values);
      }
      setSaveStage("saving");
      return api.put<SettingsData>(
        "/settings",
        { market_data: toPayload(values) },
        { signal: AbortSignal.timeout(20_000), silent: true },
      );
    },
    onMutate: () => {
      setTestResult(null);
      setTestError(null);
    },
    onSuccess: (next) => {
      setTestedAt(new Date().toLocaleString("zh-CN", { hour12: false }));
      setTestError(null);
      form.setFieldsValue({
        ifind_password: "",
        tushare_token: "",
        rqdata_password: "",
        tqsdk_auth_password: "",
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
              ? `股票 ${selectedStock?.label ?? stockProvider} · 期货 ${selectedFutures?.label ?? futuresProvider}`
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
          <strong>股票与期货可选用不同行情源</strong>
          <p>
            天勤 TqSdk 仅用于期货实时行情；股票请继续使用 AKShare / iFinD /
            通达信等。免费源适合研究和看盘。
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
        <Form.Item name="stock_provider" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="futures_provider" hidden>
          <Input />
        </Form.Item>

        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <ProviderGrid
            title="股票行情源"
            providers={stockProviders}
            activeId={stockProvider}
            onSelect={(id) => {
              form.setFieldValue("stock_provider", id);
              form.setFieldValue("provider", id);
            }}
          />
          <ProviderGrid
            title="期货行情源"
            providers={futuresProviders}
            activeId={futuresProvider}
            onSelect={(id) => form.setFieldValue("futures_provider", id)}
          />
        </Space>

        {!componentReady ? (
          <Alert
            type="warning"
            showIcon
            title="本地组件尚未安装"
            description="配置入口已经开放；安装对应官方 Python 组件或客户端后即可测试并启用。"
            style={{ marginTop: 14, marginBottom: 14 }}
          />
        ) : null}

        <div className="market-provider-config" style={{ marginTop: 14 }}>
          <Row gutter={12}>
            {needsIfind ? (
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

            {needsTdx ? (
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

            {needsTushare ? (
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

            {needsRqdata ? (
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

            {needsTqsdk ? (
              <>
                <Col span={12}>
                  <Form.Item
                    name="tqsdk_auth_user"
                    label="快期账号"
                    extra="仅用于期货行情；不要求期货资金账户。"
                    rules={[{ required: true, message: "请填写快期账号" }]}
                  >
                    <Input prefix={<UserOutlined />} autoComplete="username" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="tqsdk_auth_password"
                    label="快期密码"
                    rules={[
                      {
                        validator: validatePassword(
                          data?.market_data?.tqsdk_credentials_configured,
                          " 快期密码",
                        ),
                      },
                    ]}
                  >
                    <Input.Password
                      prefix={<KeyOutlined />}
                      placeholder={
                        data?.market_data?.tqsdk_credentials_configured
                          ? "••••••••  已安全保存"
                          : "请输入快期密码"
                      }
                      autoComplete="new-password"
                    />
                  </Form.Item>
                </Col>
              </>
            ) : null}

            {needsAkshare ? (
              <Col span={24}>
                <Alert
                  type="success"
                  showIcon
                  title="AKShare：免账号、免密钥"
                  description="数据来自公开财经网站，源站限流或结构调整时可能短暂不可用。"
                  style={{ marginBottom: 12 }}
                />
              </Col>
            ) : null}

            {needsWind ? (
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

            {needsAkshare ? (
              <Col span={8}>
                <Form.Item
                  name="akshare_poll_seconds"
                  label="AKShare 刷新周期"
                  extra="建议不少于 10 秒。"
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
          description="赢顺属于交易客户端；在没有厂商或期货公司授权行情接口的情况下，本系统不采用抓包、注入或网页爬取方式接入。"
          style={{ marginBottom: 14, marginTop: 14 }}
        />

        {test.isPending || saveStage === "testing" ? (
          <Alert
            type="info"
            showIcon
            title="正在验证行情源"
            description="股票与期货源会分别读取单个样本行情。"
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
            title="行情源验证未通过"
            description={`${testError}${testedAt ? `；最近测试 ${testedAt}` : ""}`}
            style={{ marginBottom: 14 }}
          />
        ) : testResult?.ok ? (
          <Alert
            type="success"
            showIcon
            title={configured ? "验证通过并已启用" : "连接测试通过"}
            description={testDescription || "行情源连接正常。"}
            style={{ marginBottom: 14 }}
          />
        ) : configured ? (
          <Alert
            type="success"
            showIcon
            title="当前行情配置已启用"
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
              ? "正在验证行情"
              : saveStage === "saving"
                ? "正在启用，订阅后台恢复"
                : stockProvider === "mock" && futuresProvider === "mock"
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
