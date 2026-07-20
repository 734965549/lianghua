import { useMemo } from "react";
import { Empty, Spin } from "antd";
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { api } from "../api/client";
import type { KlineBar } from "../api/types";

type Props = {
  market: string;
  symbol: string;
  interval?: string;
};

export default function KlineChart({ market, symbol, interval = "1m" }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["klines", market, symbol, interval],
    queryFn: () =>
      api.get<KlineBar[]>(
        `/klines?market=${market}&symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=120`
      ),
    enabled: Boolean(market && symbol),
    refetchInterval: 30000,
  });

  const option = useMemo(() => {
    const bars = data ?? [];
    const categories = bars.map((b) => dayjs(b.bar_time).format("HH:mm"));
    const values = bars.map((b) => [
      Number(b.open),
      Number(b.close),
      Number(b.low),
      Number(b.high),
    ]);
    const volumes = bars.map((b) => Number(b.volume));

    return {
      animation: false,
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      grid: [
        { left: 50, right: 20, top: 30, height: "55%" },
        { left: 50, right: 20, top: "72%", height: "16%" },
      ],
      xAxis: [
        { type: "category", data: categories, boundaryGap: true, axisLine: { onZero: false } },
        { type: "category", gridIndex: 1, data: categories, axisLabel: { show: false } },
      ],
      yAxis: [
        { scale: true, splitArea: { show: true } },
        { scale: true, gridIndex: 1, splitNumber: 2 },
      ],
      dataZoom: [{ type: "inside", xAxisIndex: [0, 1] }],
      series: [
        {
          name: "K线",
          type: "candlestick",
          data: values,
          itemStyle: {
            color: "#cf1322",
            color0: "#3f8600",
            borderColor: "#cf1322",
            borderColor0: "#3f8600",
          },
        },
        {
          name: "成交量",
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumes,
          itemStyle: { color: "#91caff" },
        },
      ],
    };
  }, [data]);

  if (!symbol) return <Empty description="请选择标的" />;
  if (isLoading) return <Spin />;
  if (!data?.length) return <Empty description="暂无 K 线数据" />;

  return <ReactECharts option={option} style={{ height: 420 }} />;
}
