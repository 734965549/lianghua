import { Drawer, Descriptions, Tag } from "antd";

export type RiskCheckItem = {
  check_id: string;
  signal_id?: string | null;
  result: string;
  rule_code: string;
  reason: string;
  checked_at: string;
  snapshot?: Record<string, unknown>;
};

type Props = {
  open: boolean;
  onClose: () => void;
  check: RiskCheckItem | null;
};

export default function RiskCheckDrawer({ open, onClose, check }: Props) {
  return (
    <Drawer title="风控检查详情" open={open} onClose={onClose} width={480}>
      {check && (
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="结果">
            <Tag color={check.result === "passed" ? "green" : "red"}>{check.result}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="规则码">{check.rule_code || "-"}</Descriptions.Item>
          <Descriptions.Item label="原因">{check.reason || "-"}</Descriptions.Item>
          <Descriptions.Item label="信号 ID">{check.signal_id || "-"}</Descriptions.Item>
          <Descriptions.Item label="时间">{check.checked_at}</Descriptions.Item>
          <Descriptions.Item label="快照">
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12 }}>
              {JSON.stringify(check.snapshot ?? {}, null, 2)}
            </pre>
          </Descriptions.Item>
        </Descriptions>
      )}
    </Drawer>
  );
}
