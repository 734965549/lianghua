import { Table } from "antd";

export type PositionRow = {
  id: string;
  symbol: string;
  market: string;
  direction: string;
  quantity: string;
  available_quantity: string;
  avg_cost: string;
  market_value: string;
  pnl: string;
  snapshot_time: string;
};

type Props = {
  dataSource: PositionRow[];
  loading?: boolean;
};

export default function PositionTable({ dataSource, loading }: Props) {
  return (
    <Table
      rowKey="id"
      size="small"
      loading={loading}
      dataSource={dataSource}
      pagination={false}
      locale={{ emptyText: "暂无持仓（Mock 默认可为空，资金快照仍会同步）" }}
      columns={[
        { title: "标的", dataIndex: "symbol" },
        { title: "市场", dataIndex: "market", width: 90 },
        { title: "方向", dataIndex: "direction", width: 80 },
        { title: "数量", dataIndex: "quantity", width: 90 },
        { title: "可用", dataIndex: "available_quantity", width: 90 },
        { title: "成本", dataIndex: "avg_cost", width: 100 },
        { title: "市值", dataIndex: "market_value", width: 110 },
        { title: "盈亏", dataIndex: "pnl", width: 100 },
        { title: "快照时间", dataIndex: "snapshot_time", width: 180 },
      ]}
    />
  );
}
