import { useEffect, useState } from "react";
import { Button, Layout, Menu, Tooltip, type MenuProps } from "antd";
import {
  AlertOutlined,
  BarChartOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  FundOutlined,
  HistoryOutlined,
  LineChartOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  SwapOutlined,
  UnorderedListOutlined,
  WalletOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import CommandPalette from "../components/CommandPalette";
import EmergencyStopButton from "../components/EmergencyStopButton";
import SystemStatusBar from "../components/SystemStatusBar";

const { Header, Sider, Content } = Layout;

const menuItems: MenuProps["items"] = [
  {
    type: "group",
    label: "总览",
    children: [
      { key: "/dashboard", icon: <DashboardOutlined />, label: "交易驾驶舱" },
      { key: "/market", icon: <LineChartOutlined />, label: "行情工作台" },
      { key: "/watchlist", icon: <UnorderedListOutlined />, label: "自选与股票池" },
    ],
  },
  {
    type: "group",
    label: "研究与交易",
    children: [
      { key: "/data", icon: <DatabaseOutlined />, label: "数据中枢" },
      { key: "/strategies", icon: <RobotOutlined />, label: "策略脉冲" },
      { key: "/backtest", icon: <BarChartOutlined />, label: "研究实验室" },
      { key: "/trading", icon: <SwapOutlined />, label: "交易工作台" },
      { key: "/positions", icon: <WalletOutlined />, label: "账户与持仓" },
      { key: "/history", icon: <HistoryOutlined />, label: "交易档案" },
    ],
  },
  {
    type: "group",
    label: "洞察与控制",
    children: [
      { key: "/ai-reports", icon: <FundOutlined />, label: "AI 复盘" },
      { key: "/risk-settings", icon: <AlertOutlined />, label: "风险指挥台" },
      { key: "/settings", icon: <SettingOutlined />, label: "系统设置" },
      { key: "/logs", icon: <FileTextOutlined />, label: "审计与日志" },
    ],
  },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [clock, setClock] = useState(() => dayjs());

  useEffect(() => {
    const timer = window.setInterval(() => setClock(dayjs()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const openCommand = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
      }
    };
    window.addEventListener("keydown", openCommand);
    return () => window.removeEventListener("keydown", openCommand);
  }, []);

  return (
    <Layout className="terminal-shell">
      <Sider
        width={208}
        collapsedWidth={68}
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        className="terminal-sider"
      >
        <button
          type="button"
          className={`brand-lockup ${collapsed ? "brand-lockup--collapsed" : ""}`}
          onClick={() => navigate("/dashboard")}
          aria-label="返回交易驾驶舱"
        >
          <span className="brand-mark">LQ</span>
          {!collapsed ? (
            <span className="brand-copy">
              <strong>LIANGHUA</strong>
              <small>QUANT WORKSTATION</small>
            </span>
          ) : null}
        </button>

        <div className="sider-session">
          <span className="live-dot" />
          {!collapsed ? (
            <span>
              <strong>SIMULATION</strong>
              <small>本地模拟环境</small>
            </span>
          ) : null}
        </div>

        <Menu
          theme="dark"
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          className="terminal-menu"
        />

        {!collapsed ? (
          <div className="sider-footnote">
            <span>执行模式</span>
            <strong>RISK FIRST</strong>
            <small>每一笔订单先经过风控</small>
          </div>
        ) : null}
      </Sider>

      <Layout className="terminal-main">
        <Header className="terminal-header">
          <div className="terminal-header__left">
            <Button
              type="text"
              className="collapse-trigger"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
              aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
            />
            <div className="session-clock">
              <strong>{clock.format("HH:mm:ss")}</strong>
              <span>{clock.format("YYYY.MM.DD · ddd").toUpperCase()}</span>
            </div>
            <div className="terminal-breadcrumb">
              <span>工作区</span>
              <b>/</b>
              <strong>{location.pathname.replace("/", "") || "dashboard"}</strong>
            </div>
          </div>

          <div className="terminal-header__center">
            <span><i className="pulse-dot pulse-dot--red" /> 风控前置</span>
            <span><i className="pulse-dot pulse-dot--cyan" /> 实时增量</span>
            <span><i className="pulse-dot pulse-dot--green" /> 全链路审计</span>
          </div>

          <div className="terminal-header__right">
            <Tooltip title="全局功能搜索（Ctrl / ⌘ + K）">
              <Button
                className="command-trigger"
                icon={<SearchOutlined />}
                onClick={() => setCommandOpen(true)}
              >
                搜索
                <kbd>⌘K</kbd>
              </Button>
            </Tooltip>
            <SystemStatusBar />
            <EmergencyStopButton size="small" />
          </div>
        </Header>

        <Content className="terminal-content">
          <Outlet />
        </Content>

        <footer className="terminal-footer">
          <span>LIANGHUA QUANT ENGINE · v0.1.0</span>
          <span>行情与交易数据仅用于本地模拟验证</span>
          <span className="terminal-footer__latency"><i /> WORKSTATION ONLINE</span>
        </footer>
      </Layout>

      <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} />
    </Layout>
  );
}
