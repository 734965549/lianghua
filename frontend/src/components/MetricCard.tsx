import { Card, Statistic } from "antd";

type Props = {
  title: string;
  value: string | number;
  status?: "default" | "success" | "warning" | "error";
};

export default function MetricCard({ title, value, status = "default" }: Props) {
  const color =
    status === "success"
      ? "#3f8600"
      : status === "error"
        ? "#cf1322"
        : status === "warning"
          ? "#d48806"
          : undefined;

  return (
    <Card size="small">
      <Statistic title={title} value={value} valueStyle={color ? { color } : undefined} />
    </Card>
  );
}
