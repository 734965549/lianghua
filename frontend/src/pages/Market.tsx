import { useState } from "react";
import { Card, Col, Row, Select, Space, Typography } from "antd";
import QuoteTable from "../components/QuoteTable";
import KlineChart from "../components/KlineChart";
import type { QuoteSnapshot } from "../api/types";

export default function Market() {
  const [selected, setSelected] = useState<QuoteSnapshot | null>(null);
  const [interval, setInterval] = useState("1m");

  const market = selected?.market ?? "stock";
  const symbol = selected?.symbol ?? "600000.SH";

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        行情看板
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        Mock SDK 实时推送；超过 10 秒无更新的标的行将标黄并提示停更。
      </Typography.Paragraph>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card title="订阅列表" size="small">
            <QuoteTable
              selected={selected}
              onSelect={(q) => setSelected(q)}
            />
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card
            size="small"
            title={
              <Space>
                <span>
                  K 线 · {symbol} ({market})
                </span>
                <Select
                  size="small"
                  value={interval}
                  style={{ width: 90 }}
                  onChange={setInterval}
                  options={[
                    { value: "1m", label: "1 分钟" },
                    { value: "5m", label: "5 分钟" },
                    { value: "1d", label: "日线" },
                  ]}
                />
              </Space>
            }
          >
            <KlineChart market={market} symbol={symbol} interval={interval} />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
