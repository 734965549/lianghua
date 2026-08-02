import { InputNumber, Select } from "antd";
import OperandEditor, { type Operand } from "./OperandEditor";

export type Condition = {
  operator: string;
  left?: Operand;
  right?: Operand;
  operand?: Operand;
  target?: Operand;
  low?: Operand;
  high?: Operand;
  bars?: number;
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
  { operator: "between", label: "介于" },
  { operator: "rising", label: "上升" },
  { operator: "falling", label: "下降" },
  { operator: "percent_change_gte", label: "涨幅≥%" },
  { operator: "percent_change_lte", label: "跌幅≥%" },
  { operator: "has_position", label: "有持仓" },
  { operator: "no_position", label: "无持仓" },
  { operator: "bar_since_gte", label: "距上次信号≥N根" },
];

const UNARY_OPS = new Set(["rising", "falling", "has_position", "no_position"]);
const TERNARY_OPS = new Set(["between"]);
const CHANGE_OPS = new Set(["percent_change_gte", "percent_change_lte"]);
const STATE_BAR_OPS = new Set(["bar_since_gte"]);

export default function ConditionEditor({
  value,
  indicatorIds,
  formulaIds = [],
  indicatorOutputs,
  operators,
  onChange,
}: Props) {
  const ops = operators ?? DEFAULT_OPS;
  const op = value.operator;

  return (
    <div style={{ display: "grid", gap: 8, padding: 8, background: "var(--bg-2)", borderRadius: 6 }}>
      <Select
        size="small"
        style={{ width: 160 }}
        value={op}
        onChange={(nextOp) => onChange({ operator: nextOp })}
        options={ops.map((o) => ({ value: o.operator, label: o.label }))}
      />

      {UNARY_OPS.has(op) && op !== "has_position" && op !== "no_position" && (
        <OperandEditor
          value={value.operand ?? value.left ?? {}}
          indicatorIds={indicatorIds}
          formulaIds={formulaIds}
          indicatorOutputs={indicatorOutputs}
          onChange={(operand) => onChange({ ...value, operand, left: operand })}
        />
      )}

      {CHANGE_OPS.has(op) && (
        <>
          <OperandEditor
            value={value.operand ?? value.left ?? {}}
            indicatorIds={indicatorIds}
            formulaIds={formulaIds}
            indicatorOutputs={indicatorOutputs}
            onChange={(operand) => onChange({ ...value, operand, left: operand })}
          />
          <OperandEditor
            value={value.right ?? { constant: "5" }}
            indicatorIds={indicatorIds}
            formulaIds={formulaIds}
            indicatorOutputs={indicatorOutputs}
            onChange={(right) => onChange({ ...value, right })}
          />
        </>
      )}

      {STATE_BAR_OPS.has(op) && (
        <InputNumber
          size="small"
          min={0}
          max={500}
          placeholder="K线根数"
          value={value.bars}
          onChange={(v) => onChange({ ...value, bars: v ?? 0 })}
        />
      )}

      {TERNARY_OPS.has(op) && (
        <>
          <OperandEditor
            value={value.target ?? value.left ?? {}}
            indicatorIds={indicatorIds}
            formulaIds={formulaIds}
            indicatorOutputs={indicatorOutputs}
            onChange={(target) => onChange({ ...value, target, left: target })}
          />
          <OperandEditor
            value={value.low ?? { constant: "0" }}
            indicatorIds={indicatorIds}
            formulaIds={formulaIds}
            indicatorOutputs={indicatorOutputs}
            onChange={(low) => onChange({ ...value, low })}
          />
          <OperandEditor
            value={value.high ?? { constant: "100" }}
            indicatorIds={indicatorIds}
            formulaIds={formulaIds}
            indicatorOutputs={indicatorOutputs}
            onChange={(high) => onChange({ ...value, high })}
          />
        </>
      )}

      {!UNARY_OPS.has(op) && !TERNARY_OPS.has(op) && !CHANGE_OPS.has(op) && !STATE_BAR_OPS.has(op) && (
        <>
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
        </>
      )}
    </div>
  );
}
