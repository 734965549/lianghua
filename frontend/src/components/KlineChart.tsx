import { useEffect, useMemo } from "react";
import { Alert, Empty, Space, Spin, Tag, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { KlineBar, QuoteSnapshot } from "../api/types";
import { formatTime } from "../utils/format";

type Props = {
  market: string;
  symbol: string;
  interval?: string;
  quote?: QuoteSnapshot;
  onIntegrityChange?: (integrity: KlineIntegrity) => void;
};

export type KlineIntegrity = {
  trusted: boolean;
  source: string;
  simulated: boolean;
  marketDate: string;
  lastBarTime: string;
  reason: string;
};

export default function KlineChart({
  market,
  symbol,
  interval = "1m",
  quote,
  onIntegrityChange,
}: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["klines", market, symbol, interval],
    queryFn: () =>
      api.get<KlineBar[]>(
        `/klines?market=${market}&symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=120`,
        { silent: true },
      ),
    enabled: Boolean(market && symbol),
    refetchInterval: 30000,
  });

  const integrity = useMemo<KlineIntegrity>(() => {
    const bars = data ?? [];
    const latest = bars.at(-1);
    const sources = [...new Set(bars.map((bar) => bar.source || "unknown"))];
    const source = sources.length === 1 ? sources[0] : "mixed";
    const quoteSource = quote?.source || "unknown";
    const sourceMatches =
      source !== "unknown" &&
      source !== "mixed" &&
      quoteSource !== "unknown" &&
      source === quoteSource;
    const quotePrice = Number(quote?.last_price);
    const closePrice = Number(latest?.close);
    const priceDeviation =
      quotePrice > 0 && closePrice > 0
        ? Math.abs(closePrice - quotePrice) / quotePrice
        : Number.POSITIVE_INFINITY;
    const priceMatches = priceDeviation <= 0.05;
    const qualityPassed = bars.every((bar) => bar.quality_status !== "quarantined");
    const trusted = Boolean(latest) && sourceMatches && priceMatches && qualityPassed;
    const reason = !latest
      ? "暂无 K 线，快捷下单已锁定"
      : !sourceMatches
        ? `行情来源 ${quoteSource} 与 K 线来源 ${source} 不一致`
        : !priceMatches
          ? `最新 K 线与现价偏差 ${(priceDeviation * 100).toFixed(2)}%，超过 5% 安全阈值`
          : !qualityPassed
            ? "K 线包含隔离记录"
            : "行情卡与 K 线来源、价格校验通过";
    return {
      trusted,
      source,
      simulated: bars.some((bar) => Boolean(bar.simulated)),
      marketDate: latest?.market_date || "-",
      lastBarTime: latest?.bar_time || "",
      reason,
    };
  }, [data, quote?.last_price, quote?.source]);

  useEffect(() => {
    onIntegrityChange?.(integrity);
  }, [integrity, onIntegrityChange]);

  const option = useMemo(() => {
    const bars = data ?? [];
    const categories = bars.map((b) =>
      formatTime(b.bar_time, interval === "1d" ? "MM-DD" : "HH:mm"),
    );
    const values = bars.map((b) => [
      Number(b.open),
      Number(b.close),
      Number(b.low),
      Number(b.high),
    ]);
    const volumes = bars.map((b) => Number(b.volume));

    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: { color: "#8291a3" },
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "cross",
          lineStyle: { color: "#53657a" },
          crossStyle: { color: "#53657a" },
        },
        backgroundColor: "#111923",
        borderColor: "#2c3c4d",
        textStyle: { color: "#e7edf5", fontSize: 10 },
      },
      grid: [
        { left: 54, right: 18, top: 22, height: "61%" },
        { left: 54, right: 18, top: "75%", height: "15%" },
      ],
      xAxis: [
        {
          type: "category",
          data: categories,
          boundaryGap: true,
          axisLine: { onZero: false, lineStyle: { color: "#334356" } },
          axisTick: { show: false },
          axisLabel: { color: "#667587", fontSize: 9 },
        },
        {
          type: "category",
          gridIndex: 1,
          data: categories,
          axisLabel: { show: false },
          axisLine: { lineStyle: { color: "#334356" } },
          axisTick: { show: false },
        },
      ],
      yAxis: [
        {
          scale: true,
          axisLabel: { color: "#667587", fontSize: 9 },
          splitLine: { lineStyle: { color: "#1d2937" } },
          splitArea: { show: false },
        },
        {
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: { color: "#667587", fontSize: 9 },
          splitLine: { lineStyle: { color: "#1d2937" } },
        },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1] },
        {
          type: "slider",
          xAxisIndex: [0, 1],
          height: 12,
          bottom: 2,
          borderColor: "#263342",
          backgroundColor: "#0c121a",
          fillerColor: "rgba(55,183,255,.12)",
          handleStyle: { color: "#37b7ff" },
          textStyle: { color: "#667587", fontSize: 8 },
        },
      ],
      series: [
        {
          name: "K线",
          type: "candlestick",
          data: values,
          itemStyle: {
            color: "#ff4d57",
            color0: "#18c78c",
            borderColor: "#ff6c75",
            borderColor0: "#32d9a0",
          },
        },
        {
          name: "成交量",
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          itemStyle: { color: "rgba(55,183,255,.48)" },
        },
      ],
    };
  }, [data, interval]);

  if (!symbol) return <Empty description="请选择标的" />;
  if (isLoading) return <Spin />;
  if (!data?.length) return <Empty description="暂无 K 线数据" />;

  return (
    <div>
      <Alert
        type={integrity.trusted ? "info" : "error"}
        showIcon
        title={integrity.reason}
        description={
          <Space wrap size={[6, 4]}>
            <Tag>来源 {integrity.source}</Tag>
            <Tag>交易日 {integrity.marketDate}</Tag>
            <Tag>
              最后 Bar {integrity.lastBarTime ? formatTime(integrity.lastBarTime, "MM-DD HH:mm:ss") : "-"}
            </Tag>
            <Tag color={integrity.simulated ? "gold" : "green"}>
              {integrity.simulated ? "模拟数据" : "非模拟"}
            </Tag>
            {!integrity.trusted ? (
              <Typography.Text type="danger">快捷下单已锁定</Typography.Text>
            ) : null}
          </Space>
        }
        style={{ marginBottom: 8 }}
      />
      <ReactECharts option={option} style={{ height: 360 }} />
    </div>
  );
}
