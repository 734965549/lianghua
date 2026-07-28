# 前端设计

## 技术栈

| 类型 | 选型 |
| --- | --- |
| 框架 | React + TypeScript |
| 构建 | Vite |
| 组件 | Ant Design |
| 图表 | ECharts |
| 数据请求 | TanStack Query 或等价请求缓存方案 |
| 实时数据 | WebSocket |

> **实现说明（2026-07）：** 依赖主版本以 `frontend/package.json` 为准（当前为 React 19 / antd 6 / ECharts 6 / react-router 7 / Vite 8 / TypeScript 6）；下文「包依赖」节与之对齐。路由采用 `React.lazy` 按页懒加载。

## 信息架构

```text
主布局
  仪表盘
  行情看板
  策略监控
  自动交易
  持仓与账户
  历史交易
  AI 分析报告
  风控设置
  系统设置
  系统日志
```

这是交易控制台，不做营销式首页。首屏应直接展示系统状态、风险状态、当日盈亏、持仓、策略和最新告警。

## 页面职责

### 仪表盘

展示：

1. API、数据库、股票 SDK、期货 SDK 状态。
2. 当前交易状态。
3. 当日盈亏、持仓市值、可用资金。
4. 当日交易次数、风控拒绝次数、熔断状态。
5. 运行中策略数量。
6. 最新订单、成交和告警。

关键操作：

1. 一键停止。
2. 恢复交易。
3. 查看系统健康详情。

### 行情看板

展示：

1. 自选股票和期货合约列表。
2. 最新价、涨跌幅、成交量、买卖盘、更新时间。
3. K 线图。
4. 行情断线或停更告警。

### 策略监控

展示：

1. 策略列表和运行状态。
2. 策略参数。
3. 策略启停按钮。
4. 最新信号列表。
5. 策略收益和风险指标。
6. 策略日志。

危险操作：

1. 启动实盘策略必须二次确认。
2. 修改运行中策略参数必须提示生效时机。

### 自动交易

展示：

1. 委托列表。
2. 成交列表。
3. 风控检查结果。
4. 撤单操作。
5. 一键停止入口。

委托状态需要通过实时事件更新。状态未知时使用醒目提示，并引导人工检查。

### 持仓与账户

展示：

1. 账户资金。
2. 持仓列表。
3. 持仓盈亏。
4. 持仓更新时间。
5. 资金曲线。

### 历史交易

功能：

1. 按日期、标的、策略、市场、订单状态筛选。
2. 查看订单、成交和风控详情。
3. 导出 CSV。
4. 查看单笔交易链路：信号 -> 风控 -> 委托 -> 成交 -> 审计。

### AI 分析报告

功能：

1. 选择时间范围、策略、标的和市场。
2. 生成报告。
3. 查看历史报告。
4. 展示收益、回撤、胜率、盈亏比等指标图表。
5. 展示 AI 文本分析。

页面必须明确 AI 报告仅用于复盘参考，不提供直接下单入口。

### 风控设置

功能：

1. 编辑白名单、黑名单。
2. 编辑交易时段。
3. 编辑单笔金额、数量、仓位、亏损和交易次数阈值。
4. 编辑 SDK/行情异常阈值。
5. 查看风控变更审计日志。

保存风控设置必须二次确认。

### 系统设置

功能：

1. 配置股票 SDK 和期货 SDK 路径。
2. 配置 SDK 账号标识和连接参数。
3. 配置数据库连接。
4. 测试 SDK 和数据库连接。
5. 配置日志和备份路径。

敏感字段不回显明文。

### 系统日志

展示：

1. 审计日志。
2. 系统事件。
3. SDK 异常。
4. 策略异常。
5. 风控事件。

## 实时状态处理

前端启动后：

1. 调用 `/api/health` 和 `/api/dashboard` 获取初始快照。
2. 建立 `/api/ws/events` 连接。
3. 收到实时事件后更新查询缓存。
4. WebSocket 断线时显示降级提示，并继续用轮询刷新关键数据。

## 状态颜色建议

| 状态 | 颜色语义 |
| --- | --- |
| 正常、已连接、已成交 | 绿色 |
| 等待、提交中、部分成交 | 蓝色 |
| 暂停、降级、未知 | 黄色 |
| 风控拒绝、失败、熔断、紧急停止 | 红色 |

## 交互规则

1. 一键停止按钮在仪表盘和自动交易页都必须可见。
2. 一键停止、恢复交易、启动实盘策略、保存风控设置必须二次确认。
3. 所有危险操作的确认弹窗必须展示影响范围。
4. 请求失败时展示用户可理解错误信息，并保留详情入口。
5. 前端不得保存交易密码和 Token。
6. 表格默认支持筛选、排序、刷新和详情抽屉。

## 首期组件清单

| 组件 | 用途 |
| --- | --- |
| `SystemStatusBar` | 展示系统、数据库和 SDK 状态 |
| `EmergencyStopButton` | 一键停止 |
| `MetricCard` | 仪表盘指标 |
| `QuoteTable` | 行情列表 |
| `KlineChart` | K 线 |
| `StrategyTable` | 策略列表 |
| `OrderTable` | 委托列表 |
| `TradeTable` | 成交列表 |
| `RiskCheckDrawer` | 风控详情 |
| `AuditLogTable` | 审计日志 |
| `AiReportViewer` | AI 报告展示 |

## 前端验收

1. 无后端真实 SDK 时，Mock 数据能跑完整页面。
2. 系统状态变化能实时反映到仪表盘。
3. 风控拒绝和熔断能在页面醒目展示。
4. 委托和成交状态能实时更新。
5. 所有危险操作都有确认和审计原因输入。

---

## 目录结构

```text
frontend/
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  src/
    main.tsx                 入口
    App.tsx                  路由 + 全局 Provider
    router.tsx               路由配置
    api/
      client.ts              axios/fetch 封装，统一处理响应与错误
      hooks.ts               TanStack Query hooks（useDashboard, useOrders...）
      ws.ts                  WebSocket 客户端
      types.ts               后端响应 TS 类型（与 api-spec.md 对齐）
    layouts/
      MainLayout.tsx         主布局：左侧菜单 + 顶部状态条 + 内容区
    pages/
      Dashboard.tsx          仪表盘
      Market.tsx             行情看板
      Strategies.tsx         策略监控
      Trading.tsx            自动交易
      Positions.tsx          持仓与账户
      History.tsx            历史交易
      AiReports.tsx          AI 分析报告
      RiskSettings.tsx       风控设置
      Settings.tsx           系统设置
      Logs.tsx               系统日志
      NotFound.tsx
    components/
      SystemStatusBar.tsx
      EmergencyStopButton.tsx
      MetricCard.tsx
      QuoteTable.tsx
      KlineChart.tsx
      StrategyTable.tsx
      StrategyParamForm.tsx  根据 parameters_schema 动态渲染
      OrderTable.tsx
      TradeTable.tsx
      PositionTable.tsx
      AssetCurveChart.tsx
      RiskCheckDrawer.tsx
      TradeChainDrawer.tsx   信号->风控->委托->成交->审计 链路
      AuditLogTable.tsx
      SystemEventTable.tsx
      AiReportViewer.tsx
      ConfirmDialog.tsx      危险操作二次确认
    hooks/
      useSystemStatus.ts     订阅 system.status 事件
      useWebSocket.ts
    utils/
      format.ts              decimal 字符串格式化、时间格式化
      status.ts              状态枚举 -> 颜色/文字
```

## 路由清单

> 放 `src/router.tsx`。

```tsx
import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { Spin } from "antd";
import MainLayout from "./layouts/MainLayout";

const Dashboard = lazy(() => import("./pages/Dashboard"));
// ... 其余页面均 React.lazy 动态 import

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div style={{ padding: 48, textAlign: "center" }}><Spin tip="加载中…" /></div>}>
      {children}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <MainLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <LazyPage><Dashboard /></LazyPage> },
      // ... 其余路由同理包裹 LazyPage
      { path: "*", element: <LazyPage><NotFound /></LazyPage> },
    ],
  },
]);
```

## API 客户端骨架

> 放 `src/api/client.ts`。统一处理 `{success, data, error, correlation_id}` 响应。

```ts
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
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  const body: ApiResp<T> = await res.json();
  if (!body.success) {
    message.error(body.error?.message ?? "请求失败");
    throw body.error;
  }
  return body.data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(data ?? {}) }),
  put: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(data ?? {}) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
```

## WebSocket 客户端骨架

> 放 `src/api/ws.ts`。

```ts
type EventTopic = "system.status" | "quote.update" | "strategy.signal" |
                  "order.update" | "trade.update" | "risk.event" | "audit.event";

type Handler = (data: any) => void;

class WsClient {
  private ws: WebSocket | null = null;
  private handlers: Record<EventTopic, Handler[]> = {
    "system.status": [], "quote.update": [], "strategy.signal": [],
    "order.update": [], "trade.update": [], "risk.event": [], "audit.event": [],
  };
  private reconnectTimer: number | null = null;

  connect() {
    this.ws = new WebSocket(`ws://127.0.0.1:8000/api/ws/events`);
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      this.handlers[msg.topic as EventTopic]?.forEach((h) => h(msg.data));
    };
    this.ws.onclose = () => {
      // 断线降级：5 秒后重连，同时通知上层切轮询
      this.reconnectTimer = window.setTimeout(() => this.connect(), 5000);
    };
  }

  on(topic: EventTopic, handler: Handler) {
    this.handlers[topic].push(handler);
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}

export const ws = new WsClient();
```

## 全局 Provider 与启动流程

> 放 `src/App.tsx`。

```tsx
import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, App as AntdApp } from "antd";
import zhCN from "antd/locale/zh_CN";
import { router } from "./router";
import { RouterProvider } from "react-router-dom";
import { ws } from "./api/ws";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

export default function App() {
  useEffect(() => {
    ws.connect();
    return () => ws.disconnect();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: "#1677ff" } }}>
        <AntdApp>
          <RouterProvider router={router} />
        </AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
```

## 关键组件骨架

### SystemStatusBar（顶部状态条）

```tsx
import { Tag, Space } from "antd";
import { useSystemStatus } from "../hooks/useSystemStatus";

export default function SystemStatusBar() {
  const { status, dbOk, stockSdk, futuresSdk } = useSystemStatus();
  const color = (s: string) =>
    s === "ok" || s === "connected" ? "green" :
    s === "disconnected" || s === "not_configured" ? "red" : "orange";
  return (
    <Space>
      <Tag color={status === "trading" ? "green" : status === "circuit_breaker" || status === "emergency_stopped" ? "red" : "orange"}>
        系统: {status}
      </Tag>
      <Tag color={color(dbOk ? "ok" : "disconnected")}>DB</Tag>
      <Tag color={color(stockSdk)}>股票SDK</Tag>
      <Tag color={color(futuresSdk)}>期货SDK</Tag>
    </Space>
  );
}
```

### EmergencyStopButton（一键停止）

```tsx
import { Button, Popconfirm, Input } from "antd";
import { api } from "../api/client";
import { useState } from "react";

export default function EmergencyStopButton() {
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const stop = async () => {
    setLoading(true);
    try {
      await api.post("/risk/emergency-stop", { reason, cancel_open_orders: true });
    } finally { setLoading(false); }
  };
  return (
    <Popconfirm
      title="确认紧急停止？"
      description={<Input.TextArea value={reason} onChange={(e) => setReason(e.target.value)}
                         placeholder="停止原因（必填，写入审计日志）" rows={2} />}
      okText="立即停止" okButtonProps={{ danger: true }} cancelText="取消"
      onConfirm={stop} disabled={!reason.trim()}>
      <Button danger type="primary" loading={loading}>一键停止</Button>
    </Popconfirm>
  );
}
```

### Dashboard 页面骨架

```tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Row, Col, Card } from "antd";
import MetricCard from "../components/MetricCard";
import EmergencyStopButton from "../components/EmergencyStopButton";

export default function Dashboard() {
  const { data } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<any>("/dashboard"),
    refetchInterval: 5000,
  });
  return (
    <div>
      <div style={{ marginBottom: 16 }}><EmergencyStopButton /></div>
      <Row gutter={[16, 16]}>
        <Col span={6}><MetricCard title="当日盈亏" value={data?.daily_pnl} /></Col>
        <Col span={6}><MetricCard title="持仓市值" value={data?.position_value} /></Col>
        <Col span={6}><MetricCard title="可用资金" value={data?.available_cash} /></Col>
        <Col span={6}><MetricCard title="交易次数" value={data?.daily_trade_count} /></Col>
        <Col span={6}><MetricCard title="风控拒绝" value={data?.risk_reject_count} /></Col>
        <Col span={6}><MetricCard title="运行策略" value={data?.running_strategies} /></Col>
      </Row>
      {/* 最近订单、最近告警表格 */}
    </div>
  );
}
```

### OrderTable（含 WebSocket 实时更新）

```tsx
import { Table } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { ws } from "../api/ws";
import { useEffect } from "react";

export default function OrderTable() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["orders"],
    queryFn: () => api.get<any[]>("/orders?page=1&page_size=100"),
  });

  useEffect(() => {
    ws.on("order.update", (evt) => {
      // 收到状态变化，失效缓存触发重查
      qc.invalidateQueries({ queryKey: ["orders"] });
    });
  }, [qc]);

  const columns = [
    { title: "委托ID", dataIndex: "client_order_id" },
    { title: "标的", dataIndex: "symbol" },
    { title: "方向", dataIndex: "side" },
    { title: "状态", dataIndex: "status", render: (s: string) => statusTag(s) },
    { title: "已成交", dataIndex: "filled_quantity" },
    { title: "时间", dataIndex: "created_at" },
  ];
  return <Table rowKey="client_order_id" dataSource={data?.items ?? []} columns={columns} />;
}

function statusTag(s: string) {
  const color = s === "filled" ? "green" : s === "cancelled" || s === "failed" || s === "risk_rejected" ? "red"
    : s === "unknown" ? "orange" : "blue";
  return <Tag color={color}>{s}</Tag>;
}
```

### StrategyParamForm（根据 schema 动态渲染）

```tsx
import { Form, Input, InputNumber, Select } from "antd";

// 简化版：根据后端返回的 parameters_schema（JSON Schema）渲染表单
// 生产建议用 @rjsf/antd
export default function StrategyParamForm({ schema, value, onChange }: {
  schema: any; value: any; onChange: (v: any) => void;
}) {
  return (
    <Form layout="vertical" onValuesChange={(_, all) => onChange(all)}>
      {Object.entries(schema?.properties ?? {}).map(([key, prop]: [string, any]) => (
        <Form.Item key={key} label={prop.title ?? key} name={key}>
          {prop.type === "integer" || prop.type === "number"
            ? <InputNumber />
            : prop.type === "array"
            ? <Select mode="tags" />
            : <Input />}
        </Form.Item>
      ))}
    </Form>
  );
}
```

## 状态颜色与文案工具

> 放 `src/utils/status.ts`。

```ts
export const ORDER_STATUS_META: Record<string, { color: string; text: string }> = {
  pending_risk:     { color: "blue",   text: "等待风控" },
  risk_rejected:    { color: "red",    text: "风控拒绝" },
  submitting:       { color: "blue",   text: "提交中" },
  submitted:        { color: "blue",   text: "已提交" },
  partially_filled: { color: "blue",   text: "部分成交" },
  filled:           { color: "green",  text: "全部成交" },
  cancelled:        { color: "default",text: "已撤单" },
  failed:           { color: "red",    text: "失败" },
  unknown:          { color: "orange", text: "未知（需人工检查）" },
};

export const SYSTEM_STATUS_META: Record<string, { color: string; text: string }> = {
  initializing:      { color: "blue",   text: "初始化" },
  ready:             { color: "green",  text: "就绪" },
  trading:           { color: "green",  text: "交易中" },
  paused:            { color: "orange", text: "暂停" },
  circuit_breaker:   { color: "red",    text: "熔断" },
  emergency_stopped: { color: "red",    text: "紧急停止" },
  degraded:          { color: "orange", text: "降级" },
  offline:           { color: "default",text: "离线" },
};
```

## 危险操作确认清单

所有以下操作必须经过 `ConfirmDialog` 二次确认，并要求输入原因（写入审计日志）：

| 操作 | 接口 | 确认文案要点 |
| --- | --- | --- |
| 一键停止 | `POST /api/risk/emergency-stop` | "将立即禁止所有新委托，可选撤销未成交委托" |
| 恢复交易 | `POST /api/risk/resume` | "将解除熔断/紧急停止，恢复交易前请确认 SDK 与账户正常" |
| 启动实盘策略 | `POST /api/strategies/{id}/start` | "将启动实盘策略，可能产生真实委托" |
| 保存风控设置 | `PUT /api/risk/settings` | "风控参数变更可能影响交易安全" |
| 撤单 | `POST /api/orders/{id}/cancel` | "将撤销该笔未成交委托" |

## 包依赖（package.json 关键项）

> 主版本约定与 `frontend/package.json` 对齐；补丁/次版本以 lockfile 为准。若升级主版本，需同步更新本节与上文「技术栈」实现说明。

```json
{
  "dependencies": {
    "react": "^19", "react-dom": "^19", "react-router-dom": "^7",
    "antd": "^6", "@ant-design/icons": "^6",
    "echarts": "^6", "echarts-for-react": "^3",
    "@tanstack/react-query": "^5",
    "dayjs": "^1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^6", "vite": "^8",
    "typescript": "~6",
    "@types/react": "^19", "@types/react-dom": "^19",
    "@types/node": "^24"
  }
}
```
