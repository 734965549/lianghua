import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <Result
      status="404"
      title="页面不存在"
      extra={
        <Button type="primary" onClick={() => navigate("/dashboard")}>
          返回仪表盘
        </Button>
      }
    />
  );
}
