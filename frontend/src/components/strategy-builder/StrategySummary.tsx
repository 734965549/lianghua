import { Alert, Descriptions } from "antd";
import type { StrategyDefinition } from "../../api/strategies";

type Props = {
  name: string;
  definition: StrategyDefinition;
  validationErrors: string[];
};

function summarizeRule(rule: Record<string, unknown> | undefined): string {
  if (!rule) return "未设置";
  const items = (rule.all ?? rule.any ?? []) as Array<Record<string, unknown>>;
  const mode = rule.all ? "全部" : "任一";
  if (!items.length) return "未设置";
  const labels = items.map((c) => {
    const op = c.operator as string;
    const left = (c.left as { indicator?: string })?.indicator ?? "?";
    const right = (c.right as { indicator?: string })?.indicator ?? "?";
    if (op === "cross_above") return `${left} 上穿 ${right}`;
    if (op === "cross_below") return `${left} 下穿 ${right}`;
    return `${left} ${op} ${right}`;
  });
  return `${mode}满足：${labels.join("；")}`;
}

export default function StrategySummary({ name, definition, validationErrors }: Props) {
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {validationErrors.length > 0 && (
        <Alert type="error" message="校验未通过" description={validationErrors.join("；")} showIcon />
      )}
      <Descriptions size="small" bordered column={1}>
        <Descriptions.Item label="策略名称">{name || "未命名"}</Descriptions.Item>
        <Descriptions.Item label="市场">{definition.market}</Descriptions.Item>
        <Descriptions.Item label="周期">{definition.interval}</Descriptions.Item>
        <Descriptions.Item label="标的">
          {definition.symbols?.mode === "fixed"
            ? (definition.symbols.list ?? []).join("、") || "未设置"
            : `运行时指定（最多 ${definition.symbols?.max_concurrent ?? 5} 个并发持仓）`}
        </Descriptions.Item>
        <Descriptions.Item label="公式因子">
          {(definition.formulas ?? []).map((f) => `${f.id}=${f.expression}`).join("；") || "无"}
        </Descriptions.Item>
        <Descriptions.Item label="指标">
          {(definition.indicators ?? []).map((i) => `${i.id}(${i.type})`).join("、") || "无"}
        </Descriptions.Item>
        <Descriptions.Item label="卖出规则">{summarizeRule(definition.exit_rule)}</Descriptions.Item>
        <Descriptions.Item label="数量">
          {(definition.execution?.quantity_pct as { constant?: string })?.constant
            ? `账户 ${(definition.execution?.quantity_pct as { constant?: string }).constant}%`
            : String((definition.execution?.quantity as { constant?: string })?.constant ?? "100")}
        </Descriptions.Item>
        <Descriptions.Item label="止损/止盈">
          {`${definition.risk?.stop_loss_pct ?? "-"}% / ${definition.risk?.take_profit_pct ?? "-"}%`}
        </Descriptions.Item>
      </Descriptions>
    </div>
  );
}
