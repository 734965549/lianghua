import { Button, Radio, Space } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import ConditionEditor, { type Condition } from "./ConditionEditor";

export type RuleGroup = {
  all?: Array<Condition | RuleGroup>;
  any?: Array<Condition | RuleGroup>;
};

type Props = {
  value: RuleGroup;
  indicatorIds: string[];
  formulaIds?: string[];
  indicatorOutputs?: Record<string, string[]>;
  operators?: Array<{ operator: string; label: string }>;
  onChange: (group: RuleGroup) => void;
};

function isCondition(item: Condition | RuleGroup): item is Condition {
  return "operator" in item;
}

export default function RuleGroupEditor({
  value,
  indicatorIds,
  formulaIds = [],
  indicatorOutputs,
  operators,
  onChange,
}: Props) {
  const mode = value.all ? "all" : "any";
  const items = value.all ?? value.any ?? [];

  const setMode = (nextMode: "all" | "any") => {
    onChange({ [nextMode]: items.length ? items : [] });
  };

  const updateItems = (next: Array<Condition | RuleGroup>) => {
    onChange({ [mode]: next });
  };

  const addCondition = () => {
    const cond: Condition = {
      operator: "cross_above",
      left: { indicator: indicatorIds[0] },
      right: { indicator: indicatorIds[1] ?? indicatorIds[0] },
    };
    updateItems([...items, cond]);
  };

  return (
    <div>
      <Radio.Group
        size="small"
        value={mode}
        onChange={(e) => setMode(e.target.value)}
        style={{ marginBottom: 8 }}
      >
        <Radio.Button value="all">全部满足</Radio.Button>
        <Radio.Button value="any">任一满足</Radio.Button>
      </Radio.Group>
      <Space direction="vertical" style={{ width: "100%" }}>
        {items.map((item, idx) =>
          isCondition(item) ? (
            <div key={idx} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <ConditionEditor
                value={item}
                indicatorIds={indicatorIds}
                formulaIds={formulaIds}
                indicatorOutputs={indicatorOutputs}
                operators={operators}
                onChange={(cond) => {
                  const next = [...items];
                  next[idx] = cond;
                  updateItems(next);
                }}
              />
              <Button
                size="small"
                danger
                type="link"
                onClick={() => updateItems(items.filter((_, i) => i !== idx))}
              >
                删除
              </Button>
            </div>
          ) : null,
        )}
      </Space>
      <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={addCondition} style={{ marginTop: 8 }}>
        添加条件
      </Button>
    </div>
  );
}
