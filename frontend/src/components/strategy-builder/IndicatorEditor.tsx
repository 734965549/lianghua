import { Button, Input, InputNumber, Select, Table } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { StrategyDefinition } from "../../api/strategies";
import IndicatorPreviewChart from "./IndicatorPreviewChart";

type CatalogItem = {
  type: string;
  name: string;
  sources: string[];
  outputs?: string[];
  requires_period?: boolean;
  params?: Array<{ name: string; type: string; default?: unknown }>;
};

type Props = {
  definition: StrategyDefinition;
  catalog?: CatalogItem[];
  onChange: (definition: StrategyDefinition) => void;
};

const FALLBACK_CATALOG: CatalogItem[] = [
  { type: "sma", name: "SMA", sources: ["close"], outputs: ["value"], requires_period: true },
  { type: "ema", name: "EMA", sources: ["close"], outputs: ["value"], requires_period: true },
  { type: "rsi", name: "RSI", sources: ["close"], outputs: ["value"], requires_period: true },
  { type: "macd", name: "MACD", sources: ["close"], outputs: ["value", "signal", "histogram"], requires_period: false },
  { type: "bollinger", name: "布林带", sources: ["close"], outputs: ["value", "upper", "lower"], requires_period: true },
  { type: "atr", name: "ATR", sources: ["close"], outputs: ["value"], requires_period: true },
  { type: "roc", name: "ROC", sources: ["close"], outputs: ["value"], requires_period: true },
  { type: "volume_sma", name: "成交量均线", sources: ["volume"], outputs: ["value"], requires_period: true },
  { type: "kdj", name: "KDJ", sources: ["close"], outputs: ["k", "d", "j"], requires_period: true },
];

export default function IndicatorEditor({ definition, catalog, onChange }: Props) {
  const items = catalog ?? FALLBACK_CATALOG;
  const indicators = definition.indicators ?? [];

  const updateIndicators = (next: Array<Record<string, unknown>>) => {
    onChange({ ...definition, indicators: next });
  };

  const metaFor = (type: string) => items.find((c) => c.type === type);

  const addIndicator = () => {
    const id = `ind_${indicators.length + 1}`;
    updateIndicators([...indicators, { id, type: "sma", source: "close", period: 20 }]);
  };

  const updateOne = (idx: number, patch: Record<string, unknown>) => {
    const next = indicators.map((item, i) => (i === idx ? { ...item, ...patch } : item));
    updateIndicators(next);
  };

  const removeOne = (idx: number) => {
    updateIndicators(indicators.filter((_, i) => i !== idx));
  };

  return (
    <div>
      <Table
        size="small"
        pagination={false}
        rowKey={(_, idx) => String(idx)}
        dataSource={indicators}
        scroll={{ x: 720 }}
        columns={[
          {
            title: "别名 ID",
            dataIndex: "id",
            width: 100,
            render: (v, _, idx) => (
              <Input
                size="small"
                value={v as string}
                onChange={(e) => updateOne(idx, { id: e.target.value })}
              />
            ),
          },
          {
            title: "类型",
            dataIndex: "type",
            width: 110,
            render: (v, _, idx) => {
              return (
                <Select
                  size="small"
                  style={{ width: 100 }}
                  value={v as string}
                  onChange={(val) => {
                    const m = metaFor(val);
                    const patch: Record<string, unknown> = { type: val };
                    if (m?.requires_period === false) {
                      patch.period = undefined;
                      if (val === "macd") {
                        patch.params = { fast: 12, slow: 26, signal: 9 };
                      }
                    } else {
                      patch.period = 20;
                      patch.params = val === "bollinger" ? { std_dev: "2" } : undefined;
                    }
                    if (m?.sources?.length === 1) {
                      patch.source = m.sources[0];
                    }
                    updateOne(idx, patch);
                  }}
                  options={items.map((c) => ({ value: c.type, label: c.name ?? c.type }))}
                />
              );
            },
          },
          {
            title: "数据源",
            dataIndex: "source",
            width: 90,
            render: (v, row, idx) => {
              const meta = metaFor(row.type as string);
              const sources = meta?.sources ?? ["close"];
              return (
                <Select
                  size="small"
                  style={{ width: 80 }}
                  value={(v as string) ?? sources[0]}
                  onChange={(val) => updateOne(idx, { source: val })}
                  options={sources.map((f) => ({ value: f, label: f }))}
                />
              );
            },
          },
          {
            title: "周期",
            dataIndex: "period",
            width: 80,
            render: (v, row, idx) => {
              const meta = metaFor(row.type as string);
              if (meta?.requires_period === false) return "-";
              return (
                <InputNumber
                  size="small"
                  min={1}
                  max={500}
                  value={typeof v === "number" ? v : undefined}
                  onChange={(val) => updateOne(idx, { period: val ?? 20 })}
                />
              );
            },
          },
          {
            title: "附加参数",
            dataIndex: "params",
            render: (v, row, idx) => {
              const type = row.type as string;
              const params = (v as Record<string, unknown>) ?? {};
              if (type === "macd") {
                return (
                  <div style={{ display: "flex", gap: 4 }}>
                    <InputNumber size="small" placeholder="fast" value={Number(params.fast ?? 12)}
                      onChange={(n) => updateOne(idx, { params: { ...params, fast: n ?? 12 } })} />
                    <InputNumber size="small" placeholder="slow" value={Number(params.slow ?? 26)}
                      onChange={(n) => updateOne(idx, { params: { ...params, slow: n ?? 26 } })} />
                    <InputNumber size="small" placeholder="sig" value={Number(params.signal ?? 9)}
                      onChange={(n) => updateOne(idx, { params: { ...params, signal: n ?? 9 } })} />
                  </div>
                );
              }
              if (type === "bollinger") {
                return (
                  <InputNumber
                    size="small"
                    min={0.1}
                    max={5}
                    step={0.1}
                    value={Number(params.std_dev ?? 2)}
                    onChange={(n) => updateOne(idx, { params: { std_dev: String(n ?? 2) } })}
                  />
                );
              }
              return "-";
            },
          },
          {
            title: "预览",
            width: 160,
            render: (_, row) => {
              const type = row.type as string;
              const period =
                typeof row.period === "number"
                  ? row.period
                  : typeof row.period === "object" && row.period !== null
                    ? Number((row.period as { default?: number }).default ?? 20)
                    : 20;
              return (
                <IndicatorPreviewChart
                  type={type}
                  period={period}
                  params={(row.params as Record<string, unknown>) ?? {}}
                />
              );
            },
          },
          {
            title: "操作",
            width: 60,
            render: (_, __, idx) => (
              <Button size="small" danger type="link" onClick={() => removeOne(idx)}>
                删除
              </Button>
            ),
          },
        ]}
      />
      <Button type="dashed" icon={<PlusOutlined />} onClick={addIndicator} style={{ marginTop: 8 }}>
        添加指标
      </Button>
    </div>
  );
}
