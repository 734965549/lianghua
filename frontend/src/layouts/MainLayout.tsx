import { Layout, Menu, Typography } from "antd";
import {
  DashboardOutlined,
  SettingOutlined,
  FileTextOutlined,
  LineChartOutlined,
  RobotOutlined,
  SwapOutlined,
  WalletOutlined,
  HistoryOutlined,
  AlertOutlined,
  DatabaseOutlined,
  FundOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import EmergencyStopButton from "../components/EmergencyStopButton";
import SystemStatusBar from "../components/SystemStatusBar";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "仪表盘" },
  { key: "/market", icon: <LineChartOutlined />, label: "行情看板" },
  { key: "/watchlist", icon: <UnorderedListOutlined />, label: "股票池" },
  { key: "/data", icon: <DatabaseOutlined />, label: "数据管理" },
  { key: "/strategies", icon: <RobotOutlined />, label: "策略监控" },
  { key: "/trading", icon: <SwapOutlined />, label: "自动交易" },
  { key: "/positions", icon: <WalletOutlined />, label: "持仓与账户" },
  { key: "/history", icon: <HistoryOutlined />, label: "历史交易" },
  { key: "/ai-reports", icon: <FundOutlined />, label: "AI 复盘" },
  { key: "/risk-settings", icon: <AlertOutlined />, label: "风控设置" },
  { key: "/settings", icon: <SettingOutlined />, label: "系统设置" },
  { key: "/logs", icon: <FileTextOutlined />, label: "系统日志" },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth={64} theme="dark">
        <div style={{ padding: "16px 12px" }}>
          <Typography.Text style={{ color: "#fff", fontWeight: 600 }}>
            量化交易
          </Typography.Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          <SystemStatusBar />
          <EmergencyStopButton size="small" />
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
