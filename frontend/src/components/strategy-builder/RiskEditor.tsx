import { Form, InputNumber } from "antd";
import type { StrategyDefinition } from "../../api/strategies";

type Props = {
  definition: StrategyDefinition;
  onChange: (definition: StrategyDefinition) => void;
};

export default function RiskEditor({ definition, onChange }: Props) {
  const risk = definition.risk ?? {};

  const update = (patch: Record<string, unknown>) => {
    onChange({ ...definition, risk: { ...risk, ...patch } });
  };

  return (
    <div className="research-form-grid">
      <Form.Item label="止损 (%)">
        <InputNumber
          min={0}
          max={100}
          value={Number(risk.stop_loss_pct ?? 5)}
          onChange={(v) => update({ stop_loss_pct: String(v ?? 5) })}
        />
      </Form.Item>
      <Form.Item label="止盈 (%)">
        <InputNumber
          min={0}
          max={100}
          value={Number(risk.take_profit_pct ?? 10)}
          onChange={(v) => update({ take_profit_pct: String(v ?? 10) })}
        />
      </Form.Item>
      <Form.Item label="最大仓位 (%)">
        <InputNumber
          min={0}
          max={100}
          value={Number(risk.max_position_pct ?? 30)}
          onChange={(v) => update({ max_position_pct: String(v ?? 30) })}
        />
      </Form.Item>
    </div>
  );
}
