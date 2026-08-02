import { useEffect, useMemo, useState } from "react";
import { Empty, Input, Modal } from "antd";
import {
  AlertOutlined,
  BarChartOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  FundOutlined,
  HistoryOutlined,
  LineChartOutlined,
  RobotOutlined,
  SettingOutlined,
  SwapOutlined,
  UnorderedListOutlined,
  WalletOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

type Props = {
  open: boolean;
  onClose: () => void;
};

const commands = [
  { path: "/dashboard", label: "交易驾驶舱", hint: "总览资金、风险和运行态势", icon: <DashboardOutlined /> },
  { path: "/market", label: "行情工作台", hint: "标的、股票池、K 线与快捷下单", icon: <LineChartOutlined /> },
  { path: "/watchlist", label: "自选与股票池", hint: "管理关注标的和数据任务", icon: <UnorderedListOutlined /> },
  { path: "/data", label: "数据中枢", hint: "数据质量、下载和供应商状态", icon: <DatabaseOutlined /> },
  { path: "/strategies", label: "策略脉冲", hint: "策略状态、参数与信号", icon: <RobotOutlined /> },
  { path: "/backtest", label: "研究实验室", hint: "回测、撮合与绩效分析", icon: <BarChartOutlined /> },
  { path: "/trading", label: "交易工作台", hint: "人工委托、自动交易和成交", icon: <SwapOutlined /> },
  { path: "/positions", label: "账户与持仓", hint: "资金曲线和实时仓位", icon: <WalletOutlined /> },
  { path: "/history", label: "交易档案", hint: "订单链路、成交和导出", icon: <HistoryOutlined /> },
  { path: "/ai-reports", label: "AI 复盘", hint: "交易归因与复盘报告", icon: <FundOutlined /> },
  { path: "/risk-settings", label: "风险指挥台", hint: "风险阈值、熔断与恢复", icon: <AlertOutlined /> },
  { path: "/settings", label: "系统设置", hint: "运行环境与通道配置", icon: <SettingOutlined /> },
  { path: "/logs", label: "审计与日志", hint: "系统事件和审计轨迹", icon: <FileTextOutlined /> },
];

export default function CommandPalette({ open, onClose }: Props) {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return commands;
    return commands.filter(
      (item) =>
        item.label.toLowerCase().includes(keyword) ||
        item.hint.toLowerCase().includes(keyword) ||
        item.path.includes(keyword),
    );
  }, [query]);

  const go = (path: string) => {
    navigate(path);
    onClose();
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      width={620}
      destroyOnHidden
      className="command-palette"
      styles={{ body: { padding: 0 } }}
    >
      <div className="command-palette__search">
        <Input
          autoFocus
          variant="borderless"
          placeholder="搜索页面或功能…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onPressEnter={() => filtered[0] && go(filtered[0].path)}
          suffix={<kbd>ESC</kbd>}
        />
      </div>
      <div className="command-palette__label">快速前往</div>
      <div className="command-palette__results">
        {filtered.length ? (
          filtered.map((item, index) => (
            <button
              type="button"
              className="command-palette__item"
              key={item.path}
              onClick={() => go(item.path)}
            >
              <span className="command-palette__icon">{item.icon}</span>
              <span>
                <strong>{item.label}</strong>
                <small>{item.hint}</small>
              </span>
              <span className="command-palette__index">{String(index + 1).padStart(2, "0")}</span>
            </button>
          ))
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的功能" />
        )}
      </div>
      <div className="command-palette__footer">
        <span>↵ 打开</span>
        <span>Ctrl / ⌘ + K 呼出</span>
      </div>
    </Modal>
  );
}
