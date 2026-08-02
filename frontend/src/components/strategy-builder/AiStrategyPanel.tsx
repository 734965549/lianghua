/**
 * AI 自然语言策略生成面板。
 * 调用 POST /api/ai/strategies/generate，将结果填入 StrategyBuilder 表单。
 * 见 doc/strategy-builder-design.md
 */
import { useState } from "react";
import { RobotOutlined } from "@ant-design/icons";
import { Alert, Button, Input, Modal, Select, Space, Typography, message } from "antd";
import { useMutation } from "@tanstack/react-query";
import { generateStrategyFromPrompt, type StrategyDefinition } from "../../api/strategies";
import { getApiErrorMessage } from "../../api/client";

type Props = {
  onGenerated: (result: {
    name: string;
    description: string;
    definition: StrategyDefinition;
  }) => void;
};

export default function AiStrategyPanel({ onGenerated }: Props) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [market, setMarket] = useState<string | undefined>(undefined);
  const [interval, setInterval] = useState<string | undefined>(undefined);

  const generate = useMutation({
    mutationFn: () =>
      generateStrategyFromPrompt({
        prompt: prompt.trim(),
        market,
        interval,
      }),
    onSuccess: (data) => {
      onGenerated({
        name: data.name,
        description: data.description,
        definition: data.definition,
      });
      if (data.validation.valid) {
        message.success("AI 已生成策略定义，请检查后保存");
      } else {
        message.warning(`AI 已生成策略，但有 ${data.validation.errors.length} 个校验问题待修正`);
      }
      setOpen(false);
    },
    onError: (err) => {
      message.error(getApiErrorMessage(err, "AI 策略生成失败"));
    },
  });

  return (
    <>
      <Alert
        type="info"
        showIcon
        icon={<RobotOutlined />}
        message="用自然语言描述策略，AI 帮你写好规则定义"
        description="例如：「日线双均线，5日上穿20日买入，下穿卖出，每次100股，止损5%止盈10%」"
        action={
          <Button type="primary" size="small" onClick={() => setOpen(true)}>
            AI 生成策略
          </Button>
        }
        style={{ marginBottom: 16 }}
      />

      <Modal
        title="AI 生成策略"
        open={open}
        onCancel={() => setOpen(false)}
        width={640}
        footer={[
          <Button key="cancel" onClick={() => setOpen(false)}>
            取消
          </Button>,
          <Button
            key="generate"
            type="primary"
            loading={generate.isPending}
            disabled={!prompt.trim()}
            onClick={() => generate.mutate()}
          >
            生成
          </Button>,
        ]}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Typography.Text type="secondary">描述你想要的交易策略</Typography.Text>
            <Input.TextArea
              rows={5}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="例如：15分钟线 RSI 低于 30 买入，高于 70 卖出，用账户 20% 资金，最多同时持 3 只"
              maxLength={4000}
              showCount
              style={{ marginTop: 8 }}
            />
          </div>
          <Space wrap>
            <Select
              allowClear
              placeholder="市场（可选）"
              style={{ width: 140 }}
              value={market}
              onChange={setMarket}
              options={[
                { value: "stock", label: "股票" },
                { value: "futures", label: "期货" },
              ]}
            />
            <Select
              allowClear
              placeholder="周期（可选）"
              style={{ width: 140 }}
              value={interval}
              onChange={setInterval}
              options={[
                { value: "1m", label: "1 分钟" },
                { value: "5m", label: "5 分钟" },
                { value: "15m", label: "15 分钟" },
                { value: "1h", label: "1 小时" },
                { value: "1d", label: "日线" },
              ]}
            />
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            生成后可在各步骤中继续微调。未配置 AI 时请到系统设置填写 Provider 和 API Key。
          </Typography.Text>
        </Space>
      </Modal>
    </>
  );
}
