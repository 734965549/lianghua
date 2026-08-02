import { Card, Skeleton, Table, Tag } from "antd";
import {
  ApiOutlined,
  DatabaseOutlined,
  FundOutlined,
  RadarChartOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SwapOutlined,
  WalletOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { useDashboard, useHealth } from "../api/hooks";
import EmergencyStopButton from "../components/EmergencyStopButton";
import MetricCard from "../components/MetricCard";
import PageHeader from "../components/PageHeader";
import EnumLabel from "../components/EnumLabel";
import { SYSTEM_STATUS_LABEL } from "../utils/status";

function money(value: string | number | null | undefined) {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount)
    ? amount.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "-";
}

function panelTitle(title: string, hint: string) {
  return (
    <div className="panel-title">
      <div className="panel-title__copy">
        <i />
        <strong>{title}</strong>
      </div>
      <small>{hint}</small>
    </div>
  );
}

export default function Dashboard() {
  const health = useHealth();
  const dash = useDashboard();

  const h = health.data;
  const d = dash.data;
  const statusConfirming = dash.isLoading || health.isLoading || !d || !h;

  if (statusConfirming) {
    return (
      <div className="dashboard-page" aria-busy="true">
        <PageHeader
          eyebrow="OPERATIONS / COMMAND CENTER"
          title="交易驾驶舱"
          description="正在核对资金、连接、策略与风险状态；确认完成前不展示可交易结论。"
          meta={<span className="status-chip status-chip--warning">状态确认中</span>}
          actions={<EmergencyStopButton />}
        />
        <Card>
          <Skeleton active title={{ width: "32%" }} paragraph={{ rows: 8 }} />
        </Card>
      </div>
    );
  }

  const dailyPnl = Number(d?.daily_pnl ?? 0);
  const breaker = Boolean(d?.breaker_active);
  const services = [
    { label: "API 服务", value: h?.api ?? "unknown", ok: h?.api === "ok" },
    { label: "PostgreSQL", value: h?.database ?? "unknown", ok: h?.database === "connected" },
    { label: "股票通道", value: h?.stock_sdk ?? "unknown", ok: h?.stock_sdk === "connected" },
    { label: "期货通道", value: h?.futures_sdk ?? "unknown", ok: h?.futures_sdk === "connected" },
  ];
  const insights = [
    breaker
      ? {
          title: "保护性熔断已生效",
          detail: "新委托已被阻断，需在风险指挥台确认行情与通道后人工恢复。",
          tone: "red",
        }
      : {
          title: "交易保护链路正常",
          detail: "风控前置、审计记录与订单状态机均处于工作状态。",
          tone: "green",
        },
    (d?.running_strategies ?? 0) > 0
      ? {
          title: `${d?.running_strategies ?? 0} 个策略正在运行`,
          detail: "策略信号会经过相同的风险检查和执行链路。",
          tone: "green",
        }
      : {
          title: "当前没有运行中策略",
          detail: "可前往策略脉冲检查参数或启动已验证策略。",
          tone: "amber",
        },
    (d?.risk_reject_count ?? 0) > 0
      ? {
          title: `今日已拦截 ${d?.risk_reject_count ?? 0} 次风险请求`,
          detail: "建议查看风险检查链路，确认拒绝是否符合预期。",
          tone: "red",
        }
      : {
          title: "今日暂无风控拒绝",
          detail: "当前风险阈值没有拦截新的交易请求。",
          tone: "green",
        },
  ];

  return (
    <div className="dashboard-page">
      <PageHeader
        eyebrow="OPERATIONS / COMMAND CENTER"
        title="交易驾驶舱"
        description="把资金、连接、策略和风险合并为一个可执行视图；异常优先呈现，交易动作始终受风控约束。"
        meta={
          <span className={`status-chip status-chip--${breaker ? "danger" : "success"}`}>
            {SYSTEM_STATUS_LABEL[d?.system_status ?? ""] ?? d?.system_status ?? "加载中"}
          </span>
        }
        actions={<EmergencyStopButton />}
      />

      <section className="dashboard-hero">
        <div className="dashboard-hero__pnl">
          <span className="dashboard-hero__label">TODAY P&L / 当日盈亏</span>
          <strong className={`dashboard-hero__value ${dailyPnl < 0 ? "is-negative" : ""}`}>
            {dailyPnl > 0 ? "+" : ""}
            {money(dailyPnl)}
          </strong>
          <div className="dashboard-hero__sub">
            <span>总持仓<strong>{money(d?.position_value)}</strong></span>
            <span>可用资金<strong>{money(d?.available_cash)}</strong></span>
          </div>
        </div>

        <div className="dashboard-hero__matrix">
          {services.map((service) => (
            <div className="health-line" key={service.label}>
              <div className="health-line__label">
                <span>{service.label}</span>
                <span>{service.ok ? "ONLINE" : "CHECK"}</span>
              </div>
              <div className="health-line__track">
                <div
                  className={`health-line__fill ${service.ok ? "" : "health-line__fill--danger"}`}
                  style={{ width: service.ok ? "100%" : "36%" }}
                />
              </div>
              <div className="health-line__value">
                <span>{service.value}</span>
                <span>{service.ok ? "100%" : "DEGRADED"}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="dashboard-hero__risk">
          <div className={`risk-orbit ${breaker ? "risk-orbit--danger" : ""}`}>
            <strong>{breaker ? "LOCK" : "SAFE"}</strong>
          </div>
          <div className="risk-caption">
            <strong>Lianghua 风险态势</strong>
            <small>{breaker ? "保护状态 · 禁止新委托" : "风险边界内 · 可执行"}</small>
          </div>
        </div>
      </section>

      <section className="dashboard-metrics">
        <MetricCard
          title="当日成交"
          value={d?.daily_trade_count ?? 0}
          hint="订单状态机已确认成交"
          icon={<SwapOutlined />}
          status="default"
        />
        <MetricCard
          title="运行策略"
          value={d?.running_strategies ?? 0}
          hint="实时策略执行实例"
          icon={<RobotOutlined />}
          status={(d?.running_strategies ?? 0) > 0 ? "success" : "warning"}
        />
        <MetricCard
          title="风控拒绝"
          value={d?.risk_reject_count ?? 0}
          hint="今日被规则拦截的请求"
          icon={<SafetyCertificateOutlined />}
          status={(d?.risk_reject_count ?? 0) > 0 ? "warning" : "success"}
        />
        <MetricCard
          title="系统版本"
          value={h?.version ? `v${h.version}` : "-"}
          hint="本地工作站运行版本"
          icon={<ApiOutlined />}
          status={h?.api === "ok" ? "success" : "error"}
        />
      </section>

      <section className="dashboard-lower">
        <Card
          size="small"
          title={panelTitle("实时事件流", "SYSTEM EVENTS / LATEST")}
          extra={<DatabaseOutlined className="muted" />}
        >
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            loading={dash.isLoading}
            dataSource={d?.latest_alerts ?? []}
            columns={[
              {
                title: "时间",
                dataIndex: "event_time",
                width: 150,
                render: (value: string) => (
                  <span className="numeric muted">{dayjs(value).format("MM-DD HH:mm:ss")}</span>
                ),
              },
              {
                title: "级别",
                dataIndex: "severity",
                width: 76,
                render: (value: string) => (
                  <Tag color={value === "error" ? "error" : value === "warning" ? "warning" : "blue"}>
                    <EnumLabel value={value} kind="severity" />
                  </Tag>
                ),
              },
              { title: "模块", dataIndex: "module", width: 110 },
              { title: "事件消息", dataIndex: "message" },
            ]}
          />
        </Card>

        <Card
          size="small"
          title={panelTitle("智能运行提示", "LIANGHUA SIGNALS")}
          extra={<RadarChartOutlined className="muted" />}
        >
          <div className="insight-stack">
            {insights.map((item, index) => (
              <div className="insight-item" key={item.title}>
                <span className="insight-item__index">{String(index + 1).padStart(2, "0")}</span>
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.detail}</small>
                </span>
                <i className={`insight-item__tone insight-item__tone--${item.tone}`} />
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
            <MetricCard title="资金可用" value={money(d?.available_cash)} icon={<WalletOutlined />} />
            <MetricCard title="持仓规模" value={money(d?.position_value)} icon={<FundOutlined />} />
          </div>
        </Card>
      </section>
    </div>
  );
}
