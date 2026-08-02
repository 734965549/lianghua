import { Form, Input, InputNumber, Radio } from "antd";
import type { StrategyDefinition } from "../../api/strategies";

type Props = {
  definition: StrategyDefinition;
  onChange: (definition: StrategyDefinition) => void;
};

export default function SymbolsStep({ definition, onChange }: Props) {
  const symbols = definition.symbols ?? { mode: "runtime", list: [], max_concurrent: 5 };
  const list = (symbols.list as string[]) ?? [];

  const updateSymbols = (patch: Record<string, unknown>) => {
    onChange({ ...definition, symbols: { ...symbols, ...patch } });
  };

  return (
    <div className="research-form-grid">
      <Form.Item label="标的模式" className="span-2">
        <Radio.Group
          value={symbols.mode ?? "runtime"}
          onChange={(e) => updateSymbols({ mode: e.target.value })}
        >
          <Radio.Button value="runtime">回测/启动时指定</Radio.Button>
          <Radio.Button value="fixed">固定标的列表</Radio.Button>
        </Radio.Group>
      </Form.Item>
      {symbols.mode === "fixed" && (
        <Form.Item label="固定标的" className="span-2" extra="逗号分隔，最多 20 个">
          <Input
            value={list.join(", ")}
            placeholder="600000.SH, 600519.SH"
            onChange={(e) =>
              updateSymbols({
                list: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
        </Form.Item>
      )}
      <Form.Item label="最大并发持仓" extra="同时持有标的数上限">
        <InputNumber
          min={1}
          max={10}
          value={Number(symbols.max_concurrent ?? 5)}
          onChange={(v) => updateSymbols({ max_concurrent: v ?? 5 })}
        />
      </Form.Item>
    </div>
  );
}
