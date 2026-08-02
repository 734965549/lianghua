import { useMemo } from "react";
import { Empty, Spin } from "antd";
import ReactECharts from "echarts-for-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatTime } from "../utils/format";

type AssetRow = {
  id: string;
  account_id: string;
  total_asset: string;
  available_cash: string;
  market_value: string;
  pnl: string;
  snapshot_time: string;
};

type CurvePoint = {
  snapshotTime: string;
  totalAsset: number;
  availableCash: number;
  marketValue: number;
};

function aggregateAccounts(rows: AssetRow[]): CurvePoint[] {
  const buckets = new Map<string, Map<string, AssetRow>>();
  for (const row of [...rows].reverse()) {
    const snapshotTime = new Date(row.snapshot_time).toISOString().slice(0, 19);
    const accounts = buckets.get(snapshotTime) ?? new Map<string, AssetRow>();
    accounts.set(row.account_id, row);
    buckets.set(snapshotTime, accounts);
  }

  return [...buckets.entries()].map(([snapshotTime, accounts]) => {
    const items = [...accounts.values()];
    return {
      snapshotTime: `${snapshotTime}Z`,
      totalAsset: items.reduce((sum, item) => sum + Number(item.total_asset), 0),
      availableCash: items.reduce((sum, item) => sum + Number(item.available_cash), 0),
      marketValue: items.reduce((sum, item) => sum + Number(item.market_value), 0),
    };
  });
}

export default function AssetCurveChart() {
  const { data, isLoading } = useQuery({
    queryKey: ["assets-curve"],
    queryFn: () => api.get<{ items: AssetRow[] }>("/assets?limit=400"),
    refetchInterval: 15000,
  });

  const option = useMemo(() => {
    const items = aggregateAccounts(data?.items ?? []);
    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: { color: "#8291a3" },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#111923",
        borderColor: "#2c3c4d",
        textStyle: { color: "#e7edf5" },
      },
      legend: {
        data: ["总资产", "可用资金", "市值"],
        textStyle: { color: "#8291a3", fontSize: 10 },
      },
      grid: { left: 50, right: 20, top: 40, bottom: 30 },
      xAxis: {
        type: "category",
        data: items.map((i) => formatTime(i.snapshotTime, "HH:mm:ss")),
        axisLine: { lineStyle: { color: "#334356" } },
        axisLabel: { color: "#667587", fontSize: 9 },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: "#667587", fontSize: 9 },
        splitLine: { lineStyle: { color: "#1d2937" } },
      },
      series: [
        {
          name: "总资产",
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { color: "#ff4d57", width: 2 },
          data: items.map((i) => i.totalAsset),
        },
        {
          name: "可用资金",
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { color: "#37b7ff", width: 1.5 },
          data: items.map((i) => i.availableCash),
        },
        {
          name: "市值",
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { color: "#ffb547", width: 1.5 },
          data: items.map((i) => i.marketValue),
        },
      ],
    };
  }, [data]);

  if (isLoading) return <Spin />;
  if (!data?.items?.length) return <Empty description="暂无资金快照" />;
  return <ReactECharts option={option} style={{ height: 320 }} />;
}
