import ReactECharts from "echarts-for-react";
import { buildIndicatorPreview, latestPreviewValue } from "../../utils/indicatorPreview";

type Props = {
  type: string;
  period?: number;
  params?: Record<string, unknown>;
  height?: number;
};

export default function IndicatorPreviewChart({ type, period, params, height = 72 }: Props) {
  const series = buildIndicatorPreview(type, { period, params });
  if (series.lines.length === 0) return null;

  const option = {
    animation: false,
    grid: { left: 4, right: 4, top: 4, bottom: 4 },
    xAxis: { type: "category", show: false, data: series.times },
    yAxis: { type: "value", show: false, scale: true },
    series: series.lines.map((line) => ({
      name: line.name,
      type: "line",
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 1.5, color: line.color },
      data: line.data,
    })),
    tooltip: { trigger: "axis", confine: true },
  };

  return (
    <div className="indicator-preview">
      <div className="indicator-preview__label">{latestPreviewValue(series)}</div>
      <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "svg" }} />
    </div>
  );
}
