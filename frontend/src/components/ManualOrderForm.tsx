import { useEffect } from "react";
import { Button, Form, Input, InputNumber, Select, Space, message } from "antd";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

interface ManualOrderValues {
  symbol: string;
  market: "stock" | "futures";
  side: "buy" | "sell";
  price_type: "market" | "limit";
  quantity: number;
  price?: number | null;
}

interface ManualOrderFormProps {
  symbol?: string;
  market?: "stock" | "futures";
  variant?: "inline" | "ticket";
  disabled?: boolean;
}

function createManualOrder(values: ManualOrderValues) {
  return api.post("/orders", {
    symbol: values.symbol,
    market: values.market,
    side: values.side,
    action: "open",
    price_type: values.price_type,
    quantity: String(values.quantity),
    price: values.price_type === "limit" && values.price != null ? String(values.price) : null,
    reason: "人工下单",
  });
}

export default function ManualOrderForm({
  symbol,
  market,
  variant = "inline",
  disabled = false,
}: ManualOrderFormProps) {
  const [form] = Form.useForm<ManualOrderValues>();
  const priceType = Form.useWatch("price_type", form) ?? "market";
  const side = Form.useWatch("side", form) ?? "buy";
  const queryClient = useQueryClient();

  useEffect(() => {
    if (symbol && market) {
      form.setFieldsValue({ symbol, market });
    }
  }, [symbol, market, form]);

  const mutation = useMutation({
    mutationFn: createManualOrder,
    onSuccess: () => {
      message.success("下单成功");
      form.resetFields();
      // 保留当前选中的标的
      if (symbol && market) {
        form.setFieldsValue({ symbol, market });
      }
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
      void queryClient.invalidateQueries({ queryKey: ["positions"] });
    },
  });

  const fields = (
    <>
      <Form.Item name="symbol" label="标的" rules={[{ required: true }]}>
        <Input style={{ width: 120 }} placeholder="600519.SH" disabled={disabled} />
      </Form.Item>
      <Form.Item name="market" label="市场" rules={[{ required: true }]}>
        <Select
          style={{ width: 100 }}
          disabled={disabled}
          options={[
            { value: "stock", label: "股票" },
            { value: "futures", label: "期货" },
          ]}
        />
      </Form.Item>
      <Form.Item name="side" label="方向" rules={[{ required: true }]}>
        <Select
          style={{ width: 90 }}
          disabled={disabled}
          options={[
            { value: "buy", label: "买入" },
            { value: "sell", label: "卖出" },
          ]}
        />
      </Form.Item>
      <Form.Item name="price_type" label="委托类型" rules={[{ required: true }]}>
        <Select
          style={{ width: 100 }}
          disabled={disabled}
          options={[
            { value: "market", label: "市价" },
            { value: "limit", label: "限价" },
          ]}
        />
      </Form.Item>
      {priceType === "limit" ? (
        <Form.Item name="price" label="委托价格" rules={[{ required: true }]}>
          <InputNumber style={{ width: 120 }} min={0} step={0.01} disabled={disabled} />
        </Form.Item>
      ) : null}
      <Form.Item name="quantity" label="委托数量" rules={[{ required: true }]}>
        <InputNumber style={{ width: 120 }} min={1} disabled={disabled} />
      </Form.Item>
    </>
  );

  if (variant === "ticket") {
    return (
      <Form
        form={form}
        layout="vertical"
        className="manual-order-form manual-order-form--ticket"
        onFinish={(values) => mutation.mutate(values)}
        initialValues={{ market: market ?? "stock", side: "buy", price_type: "market" }}
        disabled={disabled}
      >
        <div className="manual-order-form__grid">{fields}</div>
        <div className="manual-order-presets">
          <span>快捷数量</span>
          <Space.Compact>
            {[100, 500, 1000].map((quantity) => (
              <Button
                key={quantity}
                size="small"
                disabled={disabled}
                onClick={() => form.setFieldValue("quantity", quantity)}
              >
                {quantity}
              </Button>
            ))}
          </Space.Compact>
        </div>
        <Button
          type="primary"
          htmlType="submit"
          loading={mutation.isPending}
          disabled={disabled}
          className={`manual-order-submit manual-order-submit--${side}`}
        >
          {disabled ? "交易保护中" : `确认${side === "buy" ? "买入" : "卖出"}`}
        </Button>
        <div className="manual-order-disclaimer">
          提交后先经过白名单、仓位、亏损、频率和行情时效检查。
        </div>
      </Form>
    );
  }

  return (
    <Form
      form={form}
      layout="inline"
      className="manual-order-form manual-order-form--inline"
      onFinish={(values) => mutation.mutate(values)}
      initialValues={{ market: market ?? "stock", side: "buy", price_type: "market" }}
      disabled={disabled}
    >
      {fields}
      <Form.Item>
        <Button type="primary" htmlType="submit" loading={mutation.isPending} disabled={disabled}>
          {disabled ? "保护中" : "提交委托"}
        </Button>
      </Form.Item>
    </Form>
  );
}
