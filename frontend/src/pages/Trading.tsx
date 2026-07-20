import { useState } from "react";
import { Alert, Card, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import OrderTable from "../components/OrderTable";
import TradeTable from "../components/TradeTable";
import RiskCheckDrawer, { type RiskCheckItem } from "../components/RiskCheckDrawer";
import { api } from "../api/client";
import type { Paged } from "../api/types";

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
      }>("/risk/status"),
    refetchInterval: 5000,
  });

  const openRisk = (clientOrderId: string) => {
    const hit =
      checks.data?.items.find((c) => (c as RiskCheckItem & { client_order_id?: string }).client_order_id === clientOrderId) ||
      null;
    // 若无 client_order_id 关联，取最近一条 rejected 供查看；详情仍可从接口补
    setCheck(hit);
    setOpen(true);
    if (!hit) {
      void api
        .get<Paged<RiskCheckItem>>(`/risk/checks?page=1&page_size=20`)
        .then((res) => {
          setCheck(res.items[0] ?? null);
        })
        .catch(() => undefined);
    }
  };

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        自动交易
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        策略信号经风控通过后自动下单；支持 WebSocket 增量刷新与撤单。
      </Typography.Paragraph>

      {(riskStatus.data?.unknown_order_count ?? 0) > 0 ? (
        <Alert
          type="error"
          showIcon
          banner
          style={{ marginBottom: 16 }}
          message={`存在 ${riskStatus.data?.unknown_order_count} 笔未知状态订单，需人工检查后再恢复交易`}
        />
      ) : null}

      {riskStatus.data?.breaker_active ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message={`系统已${riskStatus.data.system_status === "emergency_stopped" ? "紧急停止" : "熔断"}，禁止新委托`}
          description={riskStatus.data.breaker_reason}
        />
      ) : null}

      <Card title="委托" size="small" style={{ marginBottom: 16 }}>
        <OrderTable onOpenRisk={openRisk} />
      </Card>
      <Card title="成交" size="small">
        <TradeTable />
      </Card>

      <RiskCheckDrawer open={open} onClose={() => setOpen(false)} check={check} />
    </div>
  );
}
