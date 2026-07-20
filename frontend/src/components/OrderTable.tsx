import { Button, Input, Modal, Select, Space, Table, Tag, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Paged } from "../api/types";
import { ws } from "../api/ws";
import { ORDER_STATUS_LABEL, orderStatusColor } from "../utils/orderStatus";

export type OrderRow = {
  client_order_id: string;
  sdk_order_id?: string | null;
  symbol: string;
  market: string;
  side: string;
  action: string;
  status: string;
  price: string;
  quantity: string;
  filled_quantity: string;
  strategy_id?: string | null;
  created_at: string;
  fail_reason?: string;
};

type Props = {
  onOpenRisk?: (clientOrderId: string) => void;
};

export default function OrderTable({ onOpenRisk }: Props) {
  const qc = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<OrderRow | null>(null);
  const [resolvedStatus, setResolvedStatus] = useState("cancelled");
  const [confirmReason, setConfirmReason] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["orders"],
    queryFn: () => api.get<Paged<OrderRow>>("/orders?page=1&page_size=50"),
    refetchInterval: 8000,
  });

  useEffect(() => {
    const off = ws.on("order.update", () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
    });
    return off;
  }, [qc]);

  const cancel = useMutation({
    mutationFn: (id: string) =>
      api.post(`/orders/${encodeURIComponent(id)}/cancel`, { reason: "用户手动撤单" }),
    onSuccess: () => {
      message.success("撤单请求已提交");
      qc.invalidateQueries({ queryKey: ["orders"] });
    },
  });

  const confirmUnknown = useMutation({
    mutationFn: (payload: { id: string; resolved_status: string; reason: string }) =>
      api.post(`/orders/${encodeURIComponent(payload.id)}/confirm-unknown`, {
        confirm: true,
        resolved_status: payload.resolved_status,
        reason: payload.reason,
      }),
    onSuccess: () => {
      message.success("未知订单已确认处理");
      setConfirmOpen(false);
      setConfirmTarget(null);
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["risk-status"] });
    },
  });

  const cancellable = new Set(["submitting", "submitted", "partially_filled"]);

  const openConfirmUnknown = (row: OrderRow) => {
    setConfirmTarget(row);
    setResolvedStatus("cancelled");
    setConfirmReason("");
    setConfirmOpen(true);
  };

  return (
    <>
    <Table
      rowKey="client_order_id"
      size="small"
      loading={isLoading}
      dataSource={data?.items ?? []}
      pagination={{ total: data?.total, pageSize: 50 }}
      columns={[
        { title: "委托号", dataIndex: "client_order_id", width: 180 },
        { title: "标的", dataIndex: "symbol", width: 110 },
        { title: "方向", dataIndex: "side", width: 70 },
        {
          title: "状态",
          dataIndex: "status",
          width: 110,
          render: (s: string) => (
            <Tag color={orderStatusColor(s)}>
              {ORDER_STATUS_LABEL[s] ?? s}
              {s === "unknown" ? "（需人工）" : ""}
            </Tag>
          ),
        },
        { title: "价格", dataIndex: "price", width: 90 },
        { title: "数量", dataIndex: "quantity", width: 80 },
        { title: "成交", dataIndex: "filled_quantity", width: 80 },
        { title: "策略", dataIndex: "strategy_id", width: 100 },
        { title: "时间", dataIndex: "created_at", width: 170 },
        {
          title: "操作",
          width: 220,
          render: (_, row) => (
            <Space>
              {row.status === "unknown" && (
                <Button size="small" type="primary" danger onClick={() => openConfirmUnknown(row)}>
                  确认处理
                </Button>
              )}
              {cancellable.has(row.status) && (
                <Button
                  size="small"
                  danger
                  onClick={() =>
                    Modal.confirm({
                      title: "确认撤单？",
                      content: "将撤销该笔未成交委托。",
                      onOk: () => cancel.mutateAsync(row.client_order_id),
                    })
                  }
                >
                  撤单
                </Button>
              )}
              {onOpenRisk && (
                <Button size="small" type="link" onClick={() => onOpenRisk(row.client_order_id)}>
                  风控
                </Button>
              )}
            </Space>
          ),
        },
      ]}
    />
    <Modal
      title="确认 unknown 订单"
      open={confirmOpen}
      onCancel={() => setConfirmOpen(false)}
      confirmLoading={confirmUnknown.isPending}
      onOk={() => {
        if (!confirmTarget) return;
        confirmUnknown.mutate({
          id: confirmTarget.client_order_id,
          resolved_status: resolvedStatus,
          reason: confirmReason || "人工确认 SDK 状态",
        });
      }}
    >
      <p>
        委托号：<strong>{confirmTarget?.client_order_id}</strong>
      </p>
      <p style={{ marginBottom: 8 }}>请先在券商/同花顺客户端核对实际状态，再选择最终状态：</p>
      <Select
        style={{ width: "100%", marginBottom: 12 }}
        value={resolvedStatus}
        onChange={setResolvedStatus}
        options={[
          { value: "cancelled", label: "已撤销（cancelled）" },
          { value: "filled", label: "已成交（filled）" },
          { value: "failed", label: "失败（failed）" },
        ]}
      />
      <Input.TextArea
        rows={2}
        placeholder="确认说明（可选）"
        value={confirmReason}
        onChange={(e) => setConfirmReason(e.target.value)}
      />
    </Modal>
    </>
  );
}
