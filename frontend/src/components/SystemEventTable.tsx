import { Table, Tag } from "antd";
import type { SystemEvent } from "../api/types";
import { formatTime } from "../utils/format";

const EVENT_LABELS: Record<string, string> = {
  STARTUP_RECOVERY: "启动恢复",
  SYSTEM_STATUS_CHANGED: "系统状态已变更",
  CIRCUIT_BREAKER: "熔断保护",
  KLINE_QUALITY_ISSUE: "K 线质量异常",
  KLINE_QUALITY_OK: "K 线质量检查通过",
  KLINE_QUARANTINED: "K 线已隔离",
  QUOTE_QUARANTINED: "行情已隔离",
  quote_stale: "行情长时间未更新",
  CIRCUIT_BREAKER_TRIGGERED: "熔断已触发",
  CIRCUIT_BREAKER_RESUMED: "熔断已解除",
  ORDER_UNKNOWN: "订单状态未知",
};

const SEVERITY_LABELS: Record<string, string> = {
  info: "信息",
  warning: "警告",
  error: "错误",
  critical: "严重",
};

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
        { title: "时间", dataIndex: "event_time", width: 180, render: (v) => formatTime(v, "MM-DD HH:mm:ss") },
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
              {SEVERITY_LABELS[v] ?? v}
            </Tag>
          ),
        },
        { title: "模块", dataIndex: "module", width: 100 },
        {
          title: "事件",
          dataIndex: "event_code",
          width: 190,
          render: (value: string) => EVENT_LABELS[value] ?? value,
        },
        { title: "消息", dataIndex: "message" },
      ]}
    />
  );
}
