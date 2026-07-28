import { Table, Tag } from "antd";
import type { SystemEvent } from "../api/types";

type Props = {
  dataSource: SystemEvent[];
  loading?: boolean;
  total?: number;
  pageSize?: number;
};

export default function SystemEventTable({
  dataSource,
  loading,
  total,
  pageSize = 50,
}: Props) {
  return (
    <Table
      rowKey="id"
      size="small"
      loading={loading}
      dataSource={dataSource}
      pagination={{ total, pageSize }}
      columns={[
        { title: "时间", dataIndex: "event_time", width: 180 },
        {
          title: "级别",
          dataIndex: "severity",
          width: 100,
          render: (v: string) => (
            <Tag
              color={
                v === "critical" || v === "error"
                  ? "red"
                  : v === "warning"
                    ? "orange"
                    : "blue"
              }
            >
              {v}
            </Tag>
          ),
        },
        { title: "模块", dataIndex: "module", width: 100 },
        { title: "事件码", dataIndex: "event_code", width: 160 },
        { title: "消息", dataIndex: "message" },
      ]}
    />
  );
}
