import { Table, Tabs, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AuditLog, Paged, SystemEvent } from "../api/types";

export default function Logs() {
  const audit = useQuery({
    queryKey: ["audit"],
    queryFn: () => api.get<Paged<AuditLog>>("/logs/audit?page=1&page_size=50"),
  });
  const events = useQuery({
    queryKey: ["system-events"],
    queryFn: () => api.get<Paged<SystemEvent>>("/logs/system-events?page=1&page_size=50"),
  });

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        系统日志
      </Typography.Title>
      <Tabs
        items={[
          {
            key: "audit",
            label: "审计日志",
            children: (
              <Table
                rowKey="id"
                size="small"
                loading={audit.isLoading}
                dataSource={audit.data?.items ?? []}
                pagination={{ total: audit.data?.total, pageSize: 50 }}
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
            ),
          },
          {
            key: "events",
            label: "系统事件",
            children: (
              <Table
                rowKey="id"
                size="small"
                loading={events.isLoading}
                dataSource={events.data?.items ?? []}
                pagination={{ total: events.data?.total, pageSize: 50 }}
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
            ),
          },
        ]}
      />
    </div>
  );
}
