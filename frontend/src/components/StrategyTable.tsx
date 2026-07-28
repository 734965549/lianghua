import { Button, Space, Table, Tag } from "antd";

export type StrategyRow = {
  strategy_id: string;
  name: string;
  description: string;
  enabled: boolean;
  running: boolean;
  supported_markets: string[];
  parameters: Record<string, unknown>;
  parameters_schema?: Record<string, unknown>;
};

type Props = {
  dataSource: StrategyRow[];
  loading?: boolean;
  /** strategy_id -> 是否有待确认重启的运行实例 */
  pendingByStrategy?: Map<string, unknown>;
  onOpenParams?: (row: StrategyRow) => void;
  onStart?: (row: StrategyRow) => void;
  onRestart?: (row: StrategyRow) => void;
  onStop?: (row: StrategyRow) => void;
};

export default function StrategyTable({
  dataSource,
  loading,
  pendingByStrategy,
  onOpenParams,
  onStart,
  onRestart,
  onStop,
}: Props) {
  return (
    <Table
      rowKey="strategy_id"
      size="small"
      loading={loading}
      dataSource={dataSource}
      pagination={false}
      columns={[
        { title: "ID", dataIndex: "strategy_id", width: 120 },
        { title: "名称", dataIndex: "name", width: 140 },
        { title: "说明", dataIndex: "description" },
        {
          title: "状态",
          width: 140,
          render: (_, row) => {
            const pending = pendingByStrategy?.get(row.strategy_id);
            if (row.running) {
              return <Tag color="green">运行中</Tag>;
            }
            if (pending) {
              return <Tag color="orange">待确认重启</Tag>;
            }
            return <Tag>已停止</Tag>;
          },
        },
        {
          title: "操作",
          width: 300,
          render: (_, row) => {
            const pending = pendingByStrategy?.get(row.strategy_id);
            return (
              <Space>
                <Button size="small" onClick={() => onOpenParams?.(row)}>
                  参数
                </Button>
                {row.running ? (
                  <Button size="small" danger onClick={() => onStop?.(row)}>
                    停止
                  </Button>
                ) : pending ? (
                  <Button size="small" type="primary" onClick={() => onRestart?.(row)}>
                    确认重启
                  </Button>
                ) : (
                  <Button size="small" type="primary" onClick={() => onStart?.(row)}>
                    启动
                  </Button>
                )}
              </Space>
            );
          },
        },
      ]}
    />
  );
}
