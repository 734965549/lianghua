from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    debug: str | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    correlation_id: str = ""


class PagedData(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


def ok(data: Any = None, correlation_id: str = "") -> dict:
    return ApiResponse(success=True, data=data, error=None, correlation_id=correlation_id).model_dump()


def fail(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    debug: str | None = None,
    correlation_id: str = "",
) -> dict:
    return ApiResponse(
        success=False,
        data=None,
        error=ErrorDetail(code=code, message=message, retryable=retryable, debug=debug),
        correlation_id=correlation_id,
    ).model_dump()


class BizError(Exception):
    """业务异常，由全局异常处理器转成 fail() 响应。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status: int = 400,
        debug: str | None = None,
    ):
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status = status
        self.debug = debug
