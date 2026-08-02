import { InputNumber, Select } from "antd";

export type Operand = {
  indicator?: string;
  output?: string;
  field?: string;
  constant?: string | number;
  parameter?: string;
  formula?: string;
};

type Props = {
  value: Operand;
  indicatorIds: string[];
  formulaIds?: string[];
  indicatorOutputs?: Record<string, string[]>;
  onChange: (operand: Operand) => void;
};

export default function OperandEditor({
  value,
  indicatorIds,
  formulaIds = [],
  indicatorOutputs,
  onChange,
}: Props) {
  const kind = value.formula
    ? "formula"
    : value.indicator
      ? "indicator"
      : value.field
        ? "field"
        : value.parameter
          ? "parameter"
          : "constant";

  const outputsFor = (id: string) => indicatorOutputs?.[id] ?? ["value"];

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <Select
        size="small"
        style={{ width: 100 }}
        value={kind}
        onChange={(k) => {
          if (k === "formula") onChange({ formula: formulaIds[0] ?? "" });
          else if (k === "indicator") onChange({ indicator: indicatorIds[0] ?? "", output: "value" });
          else if (k === "field") onChange({ field: "close" });
          else if (k === "parameter") onChange({ parameter: "" });
          else onChange({ constant: "0" });
        }}
        options={[
          { value: "indicator", label: "指标" },
          { value: "formula", label: "公式", disabled: formulaIds.length === 0 },
          { value: "field", label: "价格字段" },
          { value: "constant", label: "常量" },
          { value: "parameter", label: "参数" },
        ]}
      />
      {kind === "formula" && (
        <Select
          size="small"
          style={{ width: 120 }}
          value={value.formula}
          onChange={(v) => onChange({ formula: v })}
          options={formulaIds.map((id) => ({ value: id, label: id }))}
        />
      )}
      {kind === "indicator" && (
        <>
          <Select
            size="small"
            style={{ width: 120 }}
            value={value.indicator}
            onChange={(v) =>
              onChange({ indicator: v, output: outputsFor(v)[0] ?? "value" })
            }
            options={indicatorIds.map((id) => ({ value: id, label: id }))}
          />
          <Select
            size="small"
            style={{ width: 90 }}
            value={value.output ?? "value"}
            onChange={(v) => onChange({ ...value, output: v })}
            options={outputsFor(value.indicator ?? "").map((o) => ({ value: o, label: o }))}
          />
        </>
      )}
      {kind === "field" && (
        <Select
          size="small"
          style={{ width: 100 }}
          value={value.field ?? "close"}
          onChange={(v) => onChange({ field: v })}
          options={["open", "high", "low", "close", "volume"].map((f) => ({ value: f, label: f }))}
        />
      )}
      {kind === "constant" && (
        <InputNumber
          size="small"
          value={Number(value.constant ?? 0)}
          onChange={(v) => onChange({ constant: String(v ?? 0) })}
        />
      )}
      {kind === "parameter" && (
        <Select
          size="small"
          style={{ width: 100 }}
          value={value.parameter}
          onChange={(v) => onChange({ parameter: v })}
          options={["fast", "slow", "quantity"].map((p) => ({ value: p, label: p }))}
          allowClear
        />
      )}
    </div>
  );
}
