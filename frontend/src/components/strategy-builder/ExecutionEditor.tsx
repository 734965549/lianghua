import { Form, InputNumber, Radio } from "antd";
import type { StrategyDefinition } from "../../api/strategies";

type Props = {
  definition: StrategyDefinition;
  onChange: (definition: StrategyDefinition) => void;
};

export default function ExecutionEditor({ definition, onChange }: Props) {
  const execution = definition.execution ?? {};
  const mode = execution.quantity_pct ? "pct" : "fixed";

  const update = (patch: Record<string, unknown>) => {
    onChange({ ...definition, execution: { ...execution, ...patch } });
  };

  const setMode = (next: "fixed" | "pct") => {
    if (next === "fixed") {
      onChange({
        ...definition,
        execution: {
          cooldown_bars: execution.cooldown_bars ?? 1,
          quantity: execution.quantity ?? { constant: "100" },
        },
      });
    } else {
      onChange({
        ...definition,
        execution: {
          cooldown_bars: execution.cooldown_bars ?? 1,
          quantity_pct: execution.quantity_pct ?? { constant: "30" },
        },
      });
    }
  };

  return (
    <div className="research-form-grid">
      <Form.Item label="仓位模式" className="span-2">
        <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
          <Radio.Button value="fixed">固定数量</Radio.Button>
          <Radio.Button value="pct">账户百分比</Radio.Button>
        </Radio.Group>
      </Form.Item>
      {mode === "fixed" ? (
        <Form.Item label="买入数量（股）">
          <InputNumber
            min={1}
            value={Number((execution.quantity as { constant?: string })?.constant ?? 100)}
            onChange={(v) => update({ quantity: { constant: String(v ?? 100) } })}
          />
        </Form.Item>
      ) : (
        <Form.Item label="买入仓位（%）" extra="受最大仓位限制约束">
          <InputNumber
            min={1}
            max={100}
            value={Number((execution.quantity_pct as { constant?: string })?.constant ?? 30)}
            onChange={(v) => update({ quantity_pct: { constant: String(v ?? 30) } })}
          />
        </Form.Item>
      )}
      <Form.Item label="信号冷却（Bar 数）">
        <InputNumber
          min={0}
          max={100}
          value={Number(execution.cooldown_bars ?? 1)}
          onChange={(v) => update({ cooldown_bars: v ?? 1 })}
        />
      </Form.Item>
    </div>
  );
}
