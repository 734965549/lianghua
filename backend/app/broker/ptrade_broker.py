"""PTrade（恒生）真实交易 Broker 适配器。

PTrade 与 QMT 类似，均基于 xtquant SDK，但连接路径与账号体系不同。
本适配器继承 QMTBroker 的核心逻辑，仅调整默认配置字段与错误文案。
"""

from app.broker.qmt_broker import QMTBroker


class PTradeBroker(QMTBroker):
    """PTrade Broker 适配器。"""

    name = "ptrade"

    def __init__(self, config: dict | None = None):
        # 将 ptrade_* 配置映射为 qmt_* 配置，复用父类逻辑
        merged = dict(config or {})
        for src, dst in {
            "ptrade_client_key": "qmt_client_key",
            "ptrade_account_id": "qmt_account_id",
            "ptrade_path": "qmt_path",
            "ptrade_rpc_url": "qmt_rpc_url",
            "ptrade_poll_seconds": "qmt_poll_seconds",
        }.items():
            if src in merged and dst not in merged:
                merged[dst] = merged[src]
        super().__init__(merged)
        self.name = "ptrade"
