import { Form, Select } from "antd";
import type { StrategyDefinition } from "../../api/strategies";

type Props = {
  definition: StrategyDefinition;
  onChange: (definition: StrategyDefinition) => void;
};

export default function BasicInfoStep({ definition, onChange }: Props) {
  const update = (patch: Partial<StrategyDefinition>) => {
    onChange({ ...definition, ...patch });
  };

  return (
    <div className="research-form-grid">
      <Form.Item label="市场" required>
        <Select
          value={definition.market}
          onChange={(v) => update({ market: v })}
          options={[
            { value: "stock", label: "股票" },
            { value: "futures", label: "期货" },
          ]}
        />
      </Form.Item>
      <Form.Item label="K 线周期" required>
        <Select
          value={definition.interval}
          onChange={(v) => update({ interval: v })}
          options={[
            { value: "1d", label: "日线" },
            { value: "1h", label: "小时线" },
            { value: "15m", label: "15 分钟" },
            { value: "1m", label: "1 分钟" },
          ]}
        />
      </Form.Item>
    </div>
  );
}
