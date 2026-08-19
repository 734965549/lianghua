"""Broker 错误类型（doc/ctp-futures-integration.md §15）。

扩展自 sdk.base.AdapterError 以便上层现有 try/except 路径兼容；
新增 BrokerSubmitOutcomeUnknown 表达“发送结果未知”，禁止上层盲目重试。
"""

from __future__ import annotations

from app.schemas.error_codes import ErrorCode
from app.sdk.base import AdapterError


class BrokerConfigurationError(AdapterError):
    def __init__(self, msg: str = "Broker 配置错误", **kw):
        super().__init__(ErrorCode.SYS_INVALID_CONFIG, msg, **kw)


class BrokerAuthenticationError(AdapterError):
    def __init__(self, msg: str = "Broker 认证失败", **kw):
        super().__init__(ErrorCode.SDK_AUTH_FAILED, msg, **kw)


class BrokerLoginError(AdapterError):
    def __init__(self, msg: str = "Broker 登录失败", **kw):
        super().__init__(ErrorCode.SDK_AUTH_FAILED, msg, **kw)


class BrokerSettlementRequired(AdapterError):
    def __init__(self, msg: str = "结算单未确认", **kw):
        super().__init__(ErrorCode.SYS_INVALID_CONFIG, msg, **kw)


class BrokerNotReady(AdapterError):
    def __init__(self, msg: str = "Broker 未就绪，禁止报单", **kw):
        super().__init__(ErrorCode.SDK_DISCONNECTED, msg, retryable=True, **kw)


class BrokerQueryRateLimited(AdapterError):
    def __init__(self, msg: str = "查询频率超限", **kw):
        super().__init__(ErrorCode.SDK_TIMEOUT, msg, retryable=True, **kw)


class BrokerRequestTimeout(AdapterError):
    def __init__(self, msg: str = "Broker 请求超时", **kw):
        super().__init__(ErrorCode.SDK_TIMEOUT, msg, retryable=True, **kw)


class BrokerSubmitRejected(AdapterError):
    def __init__(self, msg: str = "Broker 拒绝报单", **kw):
        super().__init__(ErrorCode.SDK_ORDER_REJECTED, msg, **kw)


class BrokerSubmitOutcomeUnknown(AdapterError):
    """报单发送结果未知（请求超时/断线瞬间）：禁止自动重试，走对账（§10.4）。"""

    def __init__(self, msg: str = "报单结果未知，需查询对账", **kw):
        super().__init__(ErrorCode.ORDER_STATUS_UNKNOWN, msg, retryable=False, **kw)


class BrokerCancelRejected(AdapterError):
    def __init__(self, msg: str = "Broker 拒绝撤单", **kw):
        super().__init__(ErrorCode.SDK_CANCEL_REJECTED, msg, **kw)


class BrokerReconciliationError(AdapterError):
    def __init__(self, msg: str = "Broker 对账不一致", **kw):
        super().__init__(ErrorCode.SYS_INTERNAL_ERROR, msg, **kw)


class BrokerNativeRuntimeError(AdapterError):
    def __init__(self, msg: str = "Broker 原生运行错误", **kw):
        super().__init__(ErrorCode.SYS_INTERNAL_ERROR, msg, **kw)
