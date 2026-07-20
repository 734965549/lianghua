import { Result } from "antd";

export default function Placeholder({ title }: { title: string }) {
  return (
    <Result status="info" title={title} subTitle="该模块将在后续阶段实现，敬请期待。" />
  );
}
