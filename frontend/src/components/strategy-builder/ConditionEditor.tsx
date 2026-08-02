import { Select } from "antd";
import OperandEditor, { type Operand } from "./OperandEditor";

export type Condition = {
  operator: string;
  left?: Operand;
  right?: Operand;
};

type Props = {
  value: Condition;
  indicatorIds: string[];
  formulaIds?: string[];
  indicatorOutputs?: Record<string, string[]>;
  operators?: Array<{ operator: string; label: string }>;
  onChange: (condition: Condition) => void;
};

const DEFAULT_OPS = [
  { operator: "cross_above", label: "上穿" },
  { operator: "cross_below", label: "下穿" },
  { operator: "gt", label: "大于" },
  { operator: "lt", label: "小于" },
  { operator: "gte", label: "大于等于" },
  { operator: "lte", label: "小于等于" },
];

export default function ConditionEditor({
  value,
  indicatorIds,
  formulaIds = [],
  indicatorOutputs,
  operators,
  onChange,
}: Props) {
  const ops = operators ?? DEFAULT_OPS;

  return (
    <div style={{ display: "grid", gap: 8, padding: 8, background: "var(--bg-2)", borderRadius: 6 }}>
      <Select
        size="small"
        style={{ width: 140 }}
        value={value.operator}
        onChange={(op) => onChange({ ...value, operator: op })}
        options={ops.map((o) => ({ value: o.operator, label: o.label }))}
      />
      <OperandEditor
        value={value.left ?? {}}
        indicatorIds={indicatorIds}
        formulaIds={formulaIds}
        indicatorOutputs={indicatorOutputs}
        onChange={(left) => onChange({ ...value, left })}
      />
      <OperandEditor
        value={value.right ?? {}}
        indicatorIds={indicatorIds}
        formulaIds={formulaIds}
        indicatorOutputs={indicatorOutputs}
        onChange={(right) => onChange({ ...value, right })}
      />
    </div>
  );
}
