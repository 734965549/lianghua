import { Table, Tag } from "antd";
import type { AuditLog } from "../api/types";
import { formatTime } from "../utils/format";

const ACTION_LABELS: Record<string, string> = {
  order_create: "创建委托",
  order_submit: "提交委托",
  order_cancel: "撤销委托",
  risk_check: "执行风控检查",
  risk_rejected: "风控拒绝",
  ai_report_generate: "生成 AI 复盘",
  data_retention_cleanup: "清理过期数据",
  state_transition: "系统状态切换",
  strategy_signal: "生成策略信号",
  strategy_start: "启动策略",
  test_ai_connection: "测试 AI 连接",
  test_market_data_connection: "测试行情连接",
  trigger_breaker: "触发熔断",
  update_settings: "更新设置",
  settings_update: "更新设置",
  emergency_stop: "紧急停止",
  risk_resume: "恢复交易",
};

const RESULT_LABELS: Record<string, string> = {
  success: "成功",
  rejected: "已拒绝",
  failed: "失败",
};

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
        { title: "时间", dataIndex: "event_time", width: 180, render: (v) => formatTime(v, "MM-DD HH:mm:ss") },
        { title: "模块", dataIndex: "module", width: 100 },
        {
          title: "操作",
          dataIndex: "action",
          width: 160,
          render: (value: string) => ACTION_LABELS[value] ?? value,
        },
        {
          title: "结果",
          dataIndex: "result",
          width: 100,
          render: (v: string) => (
            <Tag color={v === "success" ? "green" : v === "rejected" ? "orange" : "red"}>
              {RESULT_LABELS[v] ?? v}
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
