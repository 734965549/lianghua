import { Table, Tag } from "antd";
import type { AuditLog } from "../api/types";

type Props = {
  dataSource: AuditLog[];
  loading?: boolean;
  total?: number;
  pageSize?: number;
};

export default function AuditLogTable({
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
        { title: "模块", dataIndex: "module", width: 100 },
        { title: "操作", dataIndex: "action", width: 140 },
        {
          title: "结果",
          dataIndex: "result",
          width: 100,
          render: (v: string) => (
            <Tag color={v === "success" ? "green" : v === "rejected" ? "orange" : "red"}>
              {v}
            </Tag>
          ),
        },
        { title: "对象", dataIndex: "object_type", width: 120 },
        { title: "原因", dataIndex: "reason" },
        { title: "链路ID", dataIndex: "correlation_id", width: 160 },
      ]}
    />
  );
}
