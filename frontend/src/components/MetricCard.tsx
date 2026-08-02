import type { ReactNode } from "react";
import { Card, Statistic } from "antd";

type Props = {
  title: string;
  value: string | number;
  status?: "default" | "success" | "warning" | "error";
  hint?: string;
  icon?: ReactNode;
  prefix?: string;
  loading?: boolean;
};

export default function MetricCard({
  title,
  value,
  status = "default",
  hint,
  icon,
  prefix,
  loading = false,
}: Props) {
  const color =
    status === "success"
      ? "#18c78c"
      : status === "error"
        ? "#ff4d57"
        : status === "warning"
          ? "#ffb547"
          : "#e7edf5";

  return (
    <Card size="small" loading={loading} className={`metric-card metric-card--${status}`}>
      <div className="metric-card__topline">
        <span>{title}</span>
        {icon ? <span className="metric-card__icon">{icon}</span> : null}
      </div>
      <Statistic
        value={value}
        prefix={prefix}
        styles={{ content: { color } }}
      />
      {hint ? <div className="metric-card__hint">{hint}</div> : null}
    </Card>
  );
}
