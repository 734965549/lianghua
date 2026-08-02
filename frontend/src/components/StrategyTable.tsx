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
  kind?: "builtin" | "rule";
  status?: "draft" | "published" | "archived";
  current_version?: number | null;
  editable?: boolean;
  validation_errors?: string[];
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
  onEdit?: (row: StrategyRow) => void;
  onClone?: (row: StrategyRow) => void;
  onArchive?: (row: StrategyRow) => void;
};

export default function StrategyTable({
  dataSource,
  loading,
  pendingByStrategy,
  onOpenParams,
  onStart,
  onRestart,
  onStop,
  onEdit,
  onClone,
  onArchive,
}: Props) {
  return (
    <Table
      rowKey="strategy_id"
      size="small"
      loading={loading}
      dataSource={dataSource}
      pagination={false}
      columns={[
        { title: "ID", dataIndex: "strategy_id", width: 140 },
        { title: "名称", dataIndex: "name", width: 140 },
        {
          title: "类型",
          width: 100,
          render: (_, row) => (
            <Tag color={row.kind === "rule" ? "blue" : "default"}>
              {row.kind === "rule" ? "我的策略" : "内置"}
            </Tag>
          ),
        },
        {
          title: "版本",
          width: 70,
          render: (_, row) =>
            row.current_version ? `v${row.current_version}` : row.status === "draft" ? "草稿" : "-",
        },
        { title: "说明", dataIndex: "description", ellipsis: true },
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
          width: 380,
          render: (_, row) => {
            const pending = pendingByStrategy?.get(row.strategy_id);
            const canRun = row.kind !== "rule" || (row.status === "published" && row.current_version);
            return (
              <Space wrap>
                {row.editable !== false && row.kind === "rule" ? (
                  <Button size="small" onClick={() => onEdit?.(row)}>
                    编辑
                  </Button>
                ) : null}
                <Button size="small" onClick={() => onClone?.(row)}>
                  克隆
                </Button>
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
                  <Button
                    size="small"
                    type="primary"
                    disabled={!canRun}
                    onClick={() => onStart?.(row)}
                  >
                    启动
                  </Button>
                )}
                {row.kind === "rule" && row.status !== "archived" ? (
                  <Button size="small" danger type="link" onClick={() => onArchive?.(row)}>
                    归档
                  </Button>
                ) : null}
              </Space>
            );
          },
        },
      ]}
    />
  );
}
