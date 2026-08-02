import { useMemo } from "react";
import { Alert, Button, Form, Input, Table, Tag } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { StrategyDefinition } from "../../api/strategies";
import {
  buildSamplePreviewContext,
  evaluateFormulas,
} from "../../utils/formulaEvaluator";

type FormulaItem = { id: string; expression: string };

type Props = {
  definition: StrategyDefinition;
  indicatorIds: string[];
  indicatorOutputs?: Record<string, string[]>;
  helpText?: string;
  onChange: (definition: StrategyDefinition) => void;
};

function formatPreviewValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (!Number.isFinite(value)) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(4);
}

export default function FormulaEditor({
  definition,
  indicatorIds,
  indicatorOutputs = {},
  helpText,
  onChange,
}: Props) {
  const formulas = (definition.formulas ?? []) as FormulaItem[];

  const preview = useMemo(() => {
    const ctx = buildSamplePreviewContext(
      indicatorIds,
      indicatorOutputs,
      definition.parameters ?? {},
    );
    return evaluateFormulas(formulas, ctx);
  }, [formulas, indicatorIds, indicatorOutputs, definition.parameters]);

  const updateFormulas = (next: FormulaItem[]) => {
    onChange({ ...definition, formulas: next });
  };

  const addFormula = () => {
    const id = `f${formulas.length + 1}`;
    const expr =
      indicatorIds.length >= 2
        ? `@${indicatorIds[0]} - @${indicatorIds[1]}`
        : "@fast_ma - @slow_ma";
    updateFormulas([...formulas, { id, expression: expr }]);
  };

  return (
    <div>
      {helpText && (
        <p style={{ color: "var(--text-3)", fontSize: 12, marginBottom: 8 }}>{helpText}</p>
      )}
      <Table
        size="small"
        pagination={false}
        rowKey="id"
        dataSource={formulas}
        columns={[
          {
            title: "公式 ID",
            dataIndex: "id",
            width: 120,
            render: (v, _, idx) => (
              <Input
                size="small"
                value={v}
                onChange={(e) => {
                  const next = formulas.map((f, i) =>
                    i === idx ? { ...f, id: e.target.value } : f,
                  );
                  updateFormulas(next);
                }}
              />
            ),
          },
          {
            title: "表达式",
            dataIndex: "expression",
            render: (v, _, idx) => (
              <Input
                size="small"
                value={v}
                placeholder="@fast_ma - @slow_ma"
                onChange={(e) => {
                  const next = formulas.map((f, i) =>
                    i === idx ? { ...f, expression: e.target.value } : f,
                  );
                  updateFormulas(next);
                }}
              />
            ),
          },
          {
            title: "示例预览",
            width: 120,
            render: (_, row) => {
              const val = preview.values[row.id];
              const invalid = preview.error && row.expression.trim();
              return (
                <Tag color={invalid ? "error" : val !== null && val !== undefined ? "blue" : "default"}>
                  {invalid ? "语法错误" : formatPreviewValue(val)}
                </Tag>
              );
            },
          },
          {
            title: "操作",
            width: 60,
            render: (_, __, idx) => (
              <Button
                size="small"
                danger
                type="link"
                onClick={() => updateFormulas(formulas.filter((_, i) => i !== idx))}
              >
                删除
              </Button>
            ),
          },
        ]}
      />
      {preview.error && formulas.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 8 }}
          message="公式预览"
          description={preview.error}
        />
      )}
      <Form.Item style={{ marginTop: 8, marginBottom: 0 }}>
        <Button type="dashed" icon={<PlusOutlined />} onClick={addFormula}>
          添加公式
        </Button>
      </Form.Item>
      <p style={{ color: "var(--text-3)", fontSize: 11, marginTop: 8 }}>
        引用: @指标[.输出] · $close · #参数 · &amp;其他公式 · 运算符 + - * / ( ) ·
        预览基于示例指标值实时计算
      </p>
    </div>
  );
}
