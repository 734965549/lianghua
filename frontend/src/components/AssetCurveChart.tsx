import { useMemo } from "react";
import { Empty, Spin } from "antd";
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { api } from "../api/client";

type AssetRow = {
  id: string;
  total_asset: string;
  available_cash: string;
  market_value: string;
  pnl: string;
  snapshot_time: string;
};

export default function AssetCurveChart() {
  const { data, isLoading } = useQuery({
    queryKey: ["assets-curve"],
    queryFn: () => api.get<{ items: AssetRow[] }>("/assets"),
    refetchInterval: 15000,
  });

  const option = useMemo(() => {
    const items = [...(data?.items ?? [])].reverse();
    return {
      tooltip: { trigger: "axis" },
      legend: { data: ["总资产", "可用资金", "市值"] },
      grid: { left: 50, right: 20, top: 40, bottom: 30 },
      xAxis: {
        type: "category",
        data: items.map((i) => dayjs(i.snapshot_time).format("HH:mm:ss")),
      },
      yAxis: { type: "value", scale: true },
      series: [
        { name: "总资产", type: "line", data: items.map((i) => Number(i.total_asset)) },
        { name: "可用资金", type: "line", data: items.map((i) => Number(i.available_cash)) },
        { name: "市值", type: "line", data: items.map((i) => Number(i.market_value)) },
      ],
    };
  }, [data]);

  if (isLoading) return <Spin />;
  if (!data?.items?.length) return <Empty description="暂无资金快照" />;
  return <ReactECharts option={option} style={{ height: 320 }} />;
}
