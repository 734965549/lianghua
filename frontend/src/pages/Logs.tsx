import { useState } from "react";
import { DatePicker, Input, Select, Space, Tabs, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import type { Dayjs } from "dayjs";
import { api } from "../api/client";
import type { AuditLog, Paged, SystemEvent } from "../api/types";
import AuditLogTable from "../components/AuditLogTable";
import SystemEventTable from "../components/SystemEventTable";

const moduleOptions = [
  "system",
  "market",
  "market_data",
  "data_quality",
  "risk",
  "strategy",
  "order",
  "trade",
  "settings",
  "scheduler",
].map((value) => ({ value, label: value }));

export default function Logs() {
  const [auditQuery, setAuditQuery] = useState("");
  const [auditResult, setAuditResult] = useState<string>();
  const [auditModule, setAuditModule] = useState<string>();
  const [auditRange, setAuditRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [eventQuery, setEventQuery] = useState("");
  const [eventSeverity, setEventSeverity] = useState<string>();
  const [eventModule, setEventModule] = useState<string>();
  const [eventRange, setEventRange] = useState<[Dayjs, Dayjs] | null>(null);
  const audit = useQuery({
    queryKey: ["audit", auditQuery, auditResult, auditModule, auditRange?.[0]?.valueOf(), auditRange?.[1]?.valueOf()],
    queryFn: () => {
      const qs = new URLSearchParams({ page: "1", page_size: "50" });
      if (auditQuery) qs.set("query", auditQuery);
      if (auditResult) qs.set("result", auditResult);
      if (auditModule) qs.set("module", auditModule);
      if (auditRange?.[0]) qs.set("start", auditRange[0].startOf("day").toISOString());
      if (auditRange?.[1]) qs.set("end", auditRange[1].endOf("day").toISOString());
      return api.get<Paged<AuditLog>>(`/logs/audit?${qs.toString()}`);
    },
  });
  const events = useQuery({
    queryKey: ["system-events", eventQuery, eventSeverity, eventModule, eventRange?.[0]?.valueOf(), eventRange?.[1]?.valueOf()],
    queryFn: () => {
      const qs = new URLSearchParams({ page: "1", page_size: "50" });
      if (eventQuery) qs.set("query", eventQuery);
      if (eventSeverity) qs.set("severity", eventSeverity);
      if (eventModule) qs.set("module", eventModule);
      if (eventRange?.[0]) qs.set("start", eventRange[0].startOf("day").toISOString());
      if (eventRange?.[1]) qs.set("end", eventRange[1].endOf("day").toISOString());
      return api.get<Paged<SystemEvent>>(`/logs/system-events?${qs.toString()}`);
    },
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
              <>
                <Space wrap style={{ marginBottom: 12 }}>
                  <Input.Search
                    aria-label="搜索审计日志"
                    allowClear
                    placeholder="搜索操作、对象、原因或链路 ID"
                    style={{ width: 320 }}
                    onSearch={setAuditQuery}
                  />
                  <Select
                    aria-label="筛选审计结果"
                    allowClear
                    placeholder="结果"
                    style={{ width: 130 }}
                    value={auditResult}
                    onChange={setAuditResult}
                    options={[
                      { value: "success", label: "成功" },
                      { value: "rejected", label: "已拒绝" },
                      { value: "failed", label: "失败" },
                    ]}
                  />
                  <Select
                    aria-label="筛选审计模块"
                    allowClear
                    showSearch
                    placeholder="模块"
                    style={{ width: 150 }}
                    value={auditModule}
                    onChange={setAuditModule}
                    options={moduleOptions}
                  />
                  <DatePicker.RangePicker
                    aria-label="筛选审计日期"
                    value={auditRange}
                    onChange={(value) => setAuditRange(value as [Dayjs, Dayjs] | null)}
                  />
                </Space>
                <AuditLogTable
                  dataSource={audit.data?.items ?? []}
                  loading={audit.isLoading}
                  total={audit.data?.total}
                  pageSize={50}
                />
              </>
            ),
          },
          {
            key: "events",
            label: "系统事件",
            children: (
              <>
                <Space wrap style={{ marginBottom: 12 }}>
                  <Input.Search
                    aria-label="搜索系统事件"
                    allowClear
                    placeholder="搜索事件码、模块或消息"
                    style={{ width: 320 }}
                    onSearch={setEventQuery}
                  />
                  <Select
                    aria-label="筛选事件级别"
                    allowClear
                    placeholder="级别"
                    style={{ width: 130 }}
                    value={eventSeverity}
                    onChange={setEventSeverity}
                    options={[
                      { value: "info", label: "信息" },
                      { value: "warning", label: "警告" },
                      { value: "error", label: "错误" },
                      { value: "critical", label: "严重" },
                    ]}
                  />
                  <Select
                    aria-label="筛选事件模块"
                    allowClear
                    showSearch
                    placeholder="模块"
                    style={{ width: 150 }}
                    value={eventModule}
                    onChange={setEventModule}
                    options={moduleOptions}
                  />
                  <DatePicker.RangePicker
                    aria-label="筛选事件日期"
                    value={eventRange}
                    onChange={(value) => setEventRange(value as [Dayjs, Dayjs] | null)}
                  />
                </Space>
                <SystemEventTable
                  dataSource={events.data?.items ?? []}
                  loading={events.isLoading}
                  total={events.data?.total}
                  pageSize={50}
                />
              </>
            ),
          },
        ]}
      />
    </div>
  );
}
