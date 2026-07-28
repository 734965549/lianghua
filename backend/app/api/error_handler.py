from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.response import BizError, fail
from app.schemas.error_codes import ErrorCode


def _cid(request: Request) -> str:
    return getattr(request.state, "correlation_id", "")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError):
        return JSONResponse(
            status_code=exc.status,
            content=fail(
                exc.code,
                exc.message,
                retryable=exc.retryable,
                debug=exc.debug,
                correlation_id=_cid(request),
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=fail(
                ErrorCode.SYS_VALIDATION_ERROR,
                "请求参数校验失败",
                debug=str(exc.errors()),
                correlation_id=_cid(request),
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = ErrorCode.SYS_NOT_FOUND if exc.status_code == 404 else ErrorCode.SYS_HTTP_ERROR
        detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(code, detail, correlation_id=_cid(request)).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=fail(
                ErrorCode.SYS_INTERNAL_ERROR,
                "服务器内部错误",
                debug=str(exc),
                correlation_id=_cid(request),
            ).model_dump(),
        )
