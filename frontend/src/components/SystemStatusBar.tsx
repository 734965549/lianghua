import { Space, Tag } from "antd";
import { useSystemStatus } from "../hooks/useSystemStatus";
import { connColor, SYSTEM_STATUS_LABEL, systemStatusColor } from "../utils/status";

export default function SystemStatusBar() {
  const { status, dbOk, stockSdk, futuresSdk } = useSystemStatus();

  return (
    <Space wrap>
      <Tag color={systemStatusColor(status)}>
        系统: {SYSTEM_STATUS_LABEL[status] ?? status}
      </Tag>
      <Tag color={connColor(dbOk ? "connected" : "disconnected")}>
        DB: {dbOk ? "已连接" : "断开"}
      </Tag>
      <Tag color={connColor(stockSdk)}>股票SDK: {stockSdk}</Tag>
      <Tag color={connColor(futuresSdk)}>期货SDK: {futuresSdk}</Tag>
    </Space>
  );
}
