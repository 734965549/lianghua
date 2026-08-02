"""专业行情数据适配层。

支持 Tushare Pro、RQData、Wind 等主流数据源的统一抽象与按需切换。
"""

from app.sdk.market_data.backed_adapter import MarketDataBackedAdapter
from app.sdk.market_data.base import MarketDataAdapter
from app.sdk.market_data.factory import get_market_data_adapter, list_supported_providers

__all__ = [
    "MarketDataAdapter",
    "MarketDataBackedAdapter",
    "get_market_data_adapter",
    "list_supported_providers",
]
