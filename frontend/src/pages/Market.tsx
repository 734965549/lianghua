import { useState } from "react";
import { Card, Col, Row, Select, Space, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import QuoteTable from "../components/QuoteTable";
import KlineChart from "../components/KlineChart";
import { api } from "../api/client";
import type { QuoteSnapshot } from "../api/types";

type WatchlistItem = { symbol: string; market: string; enabled: boolean };

export default function Market() {
  const [selected, setSelected] = useState<QuoteSnapshot | null>(null);
  const [interval, setInterval] = useState("1m");

  const { data: watchlist } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist"),
  });

  const watchlistSymbols = (watchlist ?? [])
    .filter((w) => w.enabled)
    .map((w) => ({ market: w.market, symbol: w.symbol }));

  const market = selected?.market ?? watchlistSymbols[0]?.market ?? "stock";
  const symbol = selected?.symbol ?? watchlistSymbols[0]?.symbol ?? "600000.SH";

  return (
    <div>
      <Typography.Title level={3} style={{ marginTop: 0 }}>
        行情看板
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        展示股票池中所有标的的实时行情；超过 10 秒无更新将标黄提示停更。
      </Typography.Paragraph>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card title="股票池行情" size="small">
            <QuoteTable
              watchlist={watchlistSymbols}
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
