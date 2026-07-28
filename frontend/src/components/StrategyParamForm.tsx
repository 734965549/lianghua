import { Button, Form, Input, InputNumber, Switch, type FormInstance } from "antd";
import { useEffect } from "react";

type JsonSchemaProperty = {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  items?: { type?: string };
  minimum?: number;
  maximum?: number;
};

type JsonSchema = {
  type?: string;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
};

type Props = {
  schema?: Record<string, unknown> | null;
  form?: FormInstance;
  initialValues?: Record<string, unknown>;
  onFinish: (values: Record<string, unknown>) => void;
  loading?: boolean;
  submitText?: string;
};

function propType(prop: JsonSchemaProperty): string {
  const t = prop.type;
  if (Array.isArray(t)) return t.find((x) => x !== "null") ?? "string";
  return t ?? "string";
}

function schemaToFormValues(
  schema: JsonSchema | undefined,
  parameters: Record<string, unknown>
): Record<string, unknown> {
  const props = schema?.properties;
  if (!props || Object.keys(props).length === 0) {
    return {
      symbols: Array.isArray(parameters.symbols)
        ? (parameters.symbols as string[]).join(",")
        : String(parameters.symbols ?? "600000.SH"),
      fast: Number(parameters.fast ?? 5),
      slow: Number(parameters.slow ?? 20),
      interval: String(parameters.interval ?? "1m"),
      quantity: Number(parameters.quantity ?? 100),
    };
  }
  const values: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(props)) {
    const raw = parameters[key] ?? prop.default;
    const t = propType(prop);
    if (t === "array") {
      values[key] = Array.isArray(raw) ? (raw as unknown[]).map(String).join(",") : String(raw ?? "");
    } else if (t === "boolean") {
      values[key] = Boolean(raw);
    } else if (t === "integer" || t === "number") {
      values[key] = raw === undefined || raw === null || raw === "" ? undefined : Number(raw);
    } else {
      values[key] = raw === undefined || raw === null ? "" : String(raw);
    }
  }
  return values;
}

/** 按 schema 将表单值组装为 parameters；无 properties 时回退固定字段逻辑 */
export function buildParametersFromForm(
  schema: Record<string, unknown> | null | undefined,
  values: Record<string, unknown>
): Record<string, unknown> {
  const props = (schema as JsonSchema | undefined)?.properties;
  if (props && Object.keys(props).length > 0) {
    const parameters: Record<string, unknown> = {};
    for (const [key, prop] of Object.entries(props)) {
      const t = propType(prop);
      const v = values[key];
      if (t === "array") {
        parameters[key] = String(v ?? "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
      } else if (t === "boolean") {
        parameters[key] = Boolean(v);
      } else if (t === "integer") {
        parameters[key] = v === undefined || v === null || v === "" ? undefined : Number(v);
      } else if (t === "number") {
        parameters[key] = v === undefined || v === null || v === "" ? undefined : Number(v);
      } else {
        parameters[key] = v;
      }
    }
    return parameters;
  }
  return {
    symbols: String(values.symbols || "600000.SH")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    fast: values.fast,
    slow: values.slow,
    interval: values.interval || "1m",
    quantity: String(values.quantity ?? "100"),
  };
}

export function getInitialFormValues(
  schema: Record<string, unknown> | null | undefined,
  parameters: Record<string, unknown>
): Record<string, unknown> {
  return schemaToFormValues(schema as JsonSchema | undefined, parameters);
}

function renderControl(prop: JsonSchemaProperty) {
  const t = propType(prop);
  if (t === "integer" || t === "number") {
    return <InputNumber style={{ width: "100%" }} min={prop.minimum} max={prop.maximum} />;
  }
  if (t === "boolean") {
    return <Switch />;
  }
  if (t === "array") {
    return <Input placeholder="多个值用逗号分隔" />;
  }
  return <Input />;
}

export default function StrategyParamForm({
  schema,
  form: externalForm,
  initialValues,
  onFinish,
  loading,
  submitText = "保存参数",
}: Props) {
  const [internalForm] = Form.useForm();
  const form = externalForm ?? internalForm;
  const jsonSchema = schema as JsonSchema | undefined;
  const properties = jsonSchema?.properties;
  const required = new Set(jsonSchema?.required ?? []);
  const hasSchema = !!properties && Object.keys(properties).length > 0;

  useEffect(() => {
    if (initialValues) {
      form.setFieldsValue(initialValues);
    }
  }, [form, initialValues]);

  return (
    <Form form={form} layout="vertical" onFinish={onFinish}>
      {hasSchema
        ? Object.entries(properties).map(([key, prop]) => {
            const t = propType(prop);
            const label = prop.title ?? key;
            return (
              <Form.Item
                key={key}
                name={key}
                label={t === "array" ? `${label}（逗号分隔）` : label}
                extra={prop.description}
                valuePropName={t === "boolean" ? "checked" : "value"}
                rules={required.has(key) ? [{ required: true, message: `请填写${label}` }] : undefined}
              >
                {renderControl(prop)}
              </Form.Item>
            );
          })
        : (
          <>
            <Form.Item name="symbols" label="标的（逗号分隔）" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="fast" label="快线" rules={[{ required: true }]}>
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name="slow" label="慢线" rules={[{ required: true }]}>
              <InputNumber min={2} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name="interval" label="周期">
              <Input placeholder="1m / 5m" />
            </Form.Item>
            <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
          </>
        )}
      <Button type="primary" htmlType="submit" loading={loading} block>
        {submitText}
      </Button>
    </Form>
  );
}
