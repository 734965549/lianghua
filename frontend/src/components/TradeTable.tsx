import { Table } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../api/client";
import type { Paged } from "../api/types";
import { ws } from "../api/ws";

export type TradeRow = {
  id: string;
  sdk_trade_id: string;
  client_order_id: string;
  symbol: string;
  market: string;
  side: string;
  price: string;
  quantity: string;
  fee: string;
  trade_time: string;
};

export default function TradeTable() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["trades"],
    queryFn: () => api.get<Paged<TradeRow>>("/trades?page=1&page_size=50"),
    refetchInterval: 8000,
  });

  useEffect(() => {
    const off = ws.on("trade.update", () => {
      qc.invalidateQueries({ queryKey: ["trades"] });
      qc.invalidateQueries({ queryKey: ["orders"] });
    });
    return off;
  }, [qc]);

  return (
    <Table
      rowKey="id"
      size="small"
      loading={isLoading}
      dataSource={data?.items ?? []}
      pagination={{ total: data?.total, pageSize: 50 }}
      columns={[
        { title: "成交编号", dataIndex: "sdk_trade_id", width: 180 },
        { title: "委托号", dataIndex: "client_order_id", width: 180 },
        { title: "标的", dataIndex: "symbol", width: 110 },
        { title: "方向", dataIndex: "side", width: 70 },
        { title: "价格", dataIndex: "price", width: 90 },
        { title: "数量", dataIndex: "quantity", width: 80 },
        { title: "费用", dataIndex: "fee", width: 80 },
        { title: "时间", dataIndex: "trade_time", width: 180 },
      ]}
    />
  );
}
