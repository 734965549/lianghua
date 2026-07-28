import { Tabs, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AuditLog, Paged, SystemEvent } from "../api/types";
import AuditLogTable from "../components/AuditLogTable";
import SystemEventTable from "../components/SystemEventTable";

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
              <AuditLogTable
                dataSource={audit.data?.items ?? []}
                loading={audit.isLoading}
                total={audit.data?.total}
                pageSize={50}
              />
            ),
          },
          {
            key: "events",
            label: "系统事件",
            children: (
              <SystemEventTable
                dataSource={events.data?.items ?? []}
                loading={events.isLoading}
                total={events.data?.total}
                pageSize={50}
              />
            ),
          },
        ]}
      />
    </div>
  );
}
