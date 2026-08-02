import { useState } from "react";
import { Card, Tabs } from "antd";
import { SafetyCertificateOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import EmergencyStopButton from "../components/EmergencyStopButton";
import ManualOrderForm from "../components/ManualOrderForm";
import OrderTable from "../components/OrderTable";
import PageHeader from "../components/PageHeader";
import TradeTable from "../components/TradeTable";
import RiskCheckDrawer, { type RiskCheckItem } from "../components/RiskCheckDrawer";
import { api } from "../api/client";
import type { Paged } from "../api/types";

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

export default function Trading() {
  const [open, setOpen] = useState(false);
  const [check, setCheck] = useState<RiskCheckItem | null>(null);

  const checks = useQuery({
    queryKey: ["risk-checks-all"],
    queryFn: () => api.get<Paged<RiskCheckItem>>("/risk/checks?page=1&page_size=100"),
  });

  const riskStatus = useQuery({
    queryKey: ["risk-status"],
    queryFn: () =>
      api.get<{
        breaker_active: boolean;
        unknown_order_count: number;
        system_status: string;
        breaker_reason?: string;
        daily_loss?: string;
        daily_trade_count?: number;
        consecutive_order_fail?: number;
      }>("/risk/status"),
    refetchInterval: 5000,
  });

  const openRisk = (clientOrderId: string) => {
    const hit =
      checks.data?.items.find(
        (item) =>
          (item as RiskCheckItem & { client_order_id?: string }).client_order_id === clientOrderId,
      ) ?? null;
    setCheck(hit);
    setOpen(true);
    if (!hit) {
      void api
        .get<Paged<RiskCheckItem>>("/risk/checks?page=1&page_size=20")
        .then((response) => setCheck(response.items[0] ?? null))
        .catch(() => undefined);
    }
  };

  const status = riskStatus.data;
  const blocked = Boolean(status?.breaker_active);
  const unknownOrders = status?.unknown_order_count ?? 0;

  return (
    <div>
      <PageHeader
        eyebrow="EXECUTION / ORDER DESK"
        title="交易工作台"
        description="手工交易与策略订单共享同一套风险前置、订单状态机和审计链路；右侧交易票据固定在操作视线内。"
        meta={
          <span className={`status-chip status-chip--${blocked ? "danger" : "success"}`}>
            {blocked ? "交易保护中" : "允许委托"}
          </span>
        }
        actions={<EmergencyStopButton />}
      />

      <section className="trading-workspace">
        <div className="trading-main">
          <div className={`risk-ribbon ${blocked ? "risk-ribbon--danger" : ""}`}>
            <div className="risk-ribbon__primary">
              <strong>
                <SafetyCertificateOutlined />{" "}
                {blocked ? "Lianghua 风险闸门已关闭" : "Lianghua 风险闸门正常"}
              </strong>
              <small>
                {blocked
                  ? status?.breaker_reason || "所有新委托已被保护性拦截"
                  : "白名单、仓位、亏损、频率、行情与重复信号规则在线"}
              </small>
            </div>
            <div className="risk-ribbon__stat">
              <span>未知订单</span>
              <strong className={unknownOrders > 0 ? "market-up" : ""}>{unknownOrders}</strong>
            </div>
            <div className="risk-ribbon__stat">
              <span>今日交易</span>
              <strong>{status?.daily_trade_count ?? 0}</strong>
            </div>
            <div className="risk-ribbon__stat">
              <span>连续失败</span>
              <strong>{status?.consecutive_order_fail ?? 0}</strong>
            </div>
          </div>

          <Card
            size="small"
            className="trading-ledger"
            title={panelTitle("执行台账", "ORDERS / TRADES")}
            extra={<ThunderboltOutlined className="muted" />}
          >
            <Tabs
              defaultActiveKey="orders"
              items={[
                {
                  key: "orders",
                  label: "活动委托",
                  children: <OrderTable scope="active" onOpenRisk={openRisk} />,
                },
                {
                  key: "attention-orders",
                  label: "待处理委托",
                  children: <OrderTable scope="attention" onOpenRisk={openRisk} />,
                },
                {
                  key: "trades",
                  label: "成交回报",
                  children: <TradeTable />,
                },
              ]}
            />
          </Card>
        </div>

        <aside className="order-dock">
          {blocked ? (
            <div className="order-dock__warning">
              <strong>交易票据已锁定</strong>
              <br />
              {status?.breaker_reason || "请在风险指挥台完成检查并人工恢复。"}
            </div>
          ) : null}
          <Card
            size="small"
            title={panelTitle("人工交易票据", "MANUAL ORDER")}
            extra={<span className="status-chip status-chip--warning">SIM</span>}
          >
            <ManualOrderForm variant="ticket" disabled={blocked} />
          </Card>
          <Card size="small" title={panelTitle("执行保护链", "PRE-TRADE CHECKS")}>
            <div className="insight-stack">
              {[
                ["01", "标的准入", "白名单 / 黑名单"],
                ["02", "资金与仓位", "单笔 / 单标的 / 总仓位"],
                ["03", "行情质量", "时效 / 断线 / 数据质量"],
                ["04", "执行控制", "频率 / 重复信号 / 失败次数"],
              ].map(([index, title, detail]) => (
                <div className="insight-item" key={index}>
                  <span className="insight-item__index">{index}</span>
                  <span>
                    <strong>{title}</strong>
                    <small>{detail}</small>
                  </span>
                  <i className="insight-item__tone insight-item__tone--green" />
                </div>
              ))}
            </div>
          </Card>
        </aside>
      </section>

      <RiskCheckDrawer open={open} onClose={() => setOpen(false)} check={check} />
    </div>
  );
}
