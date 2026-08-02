import { Segmented, Space, Table, Typography } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Paged } from "../api/types";
import { ws } from "../api/ws";
import { formatTime } from "../utils/format";
import EnumLabel from "./EnumLabel";

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

type ScopedTrades = Paged<TradeRow> & {
  scope: "today" | "all";
  scope_label: string;
  range_start: string | null;
  range_end: string | null;
  timezone: string;
};

export default function TradeTable() {
  const qc = useQueryClient();
  const [scope, setScope] = useState<"today" | "all">("today");
  const { data, isLoading } = useQuery({
    queryKey: ["trades", scope],
    queryFn: () =>
      api.get<ScopedTrades>(
        `/trades?page=1&page_size=50&scope=${scope}`,
      ),
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
    <>
      <Space
        style={{
          width: "100%",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <Typography.Text type="secondary">
          数据范围：{data?.scope_label ?? (scope === "today" ? "今日成交（上海时区）" : "全部成交")}
        </Typography.Text>
        <Segmented
          size="small"
          value={scope}
          onChange={(value) => setScope(value as "today" | "all")}
          options={[
            { label: "今日", value: "today" },
            { label: "全部", value: "all" },
          ]}
        />
      </Space>
      <Table
      rowKey="id"
      size="small"
      loading={isLoading}
      dataSource={data?.items ?? []}
      locale={{
        emptyText:
          scope === "today"
            ? "今日暂无成交，可切换“全部”查看历史成交"
            : "暂无成交记录",
      }}
      pagination={{ total: data?.total, pageSize: 50 }}
      columns={[
        { title: "成交编号", dataIndex: "sdk_trade_id", width: 180 },
        { title: "委托号", dataIndex: "client_order_id", width: 180 },
        { title: "标的", dataIndex: "symbol", width: 110 },
        {
          title: "方向",
          dataIndex: "side",
          width: 70,
          render: (value: string) => <EnumLabel value={value} kind="side" />,
        },
        { title: "价格", dataIndex: "price", width: 90 },
        { title: "数量", dataIndex: "quantity", width: 80 },
        { title: "费用", dataIndex: "fee", width: 80 },
        {
          title: "时间",
          dataIndex: "trade_time",
          width: 180,
          render: (value: string) => formatTime(value, "MM-DD HH:mm:ss"),
        },
      ]}
      />
    </>
  );
}
