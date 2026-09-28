"""FastAPI application assembly."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    routes_analyze,
    routes_conversations,
    routes_health,
    routes_history,
)
from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.db.session import init_db
from app.schemas import ErrorDetail, ErrorResponse

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.debug)
    init_db()

    if settings.demo_mode:
        logger.warning(
            "演示模式：未配置 LLM_API_KEY，将使用内置 Mock 返回示例数据。"
            "如需真实识别，请在 backend/.env 中填入 Key。"
        )
    else:
        logger.info(
            "识别服务已就绪：provider=%s model=%s",
            settings.resolved_provider,
            settings.llm_model,
        )
    logger.info("图片处理全程在内存中完成，不写入磁盘。")

    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="上传一张食物照片，返回结构化的营养识别结果。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Error handling: every failure leaves the API in the shape of ErrorResponse,
# never a bare stack trace.
# --------------------------------------------------------------------------


def _error_response(
    request: Request, status: int, code: str, message: str, hint: str | None
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            hint=hint,
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    # Expected failures are warnings, not crashes — no traceback needed.
    logger.warning("[%s] %s", exc.code, exc.message)
    return _error_response(request, exc.status, exc.code, exc.message, exc.hint)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("请求参数校验失败: %s", exc.errors())
    return _error_response(
        request,
        422,
        "validation_error",
        "请求参数不正确，请检查后重试。",
        "如果是从本应用页面操作，请刷新页面后重试。",
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return _error_response(request, 404, "not_found", "接口不存在。", "请检查访问地址。")
    return _error_response(request, exc.status_code, "http_error", str(exc.detail), None)


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理的异常")
    return _error_response(
        request,
        500,
        "internal_error",
        "服务出现意外错误，请稍后重试。",
        "如果反复出现，请把这次操作和页面上的请求编号反馈给我们。",
    )


app.include_router(routes_health.router, prefix=settings.api_prefix)
app.include_router(routes_analyze.router, prefix=settings.api_prefix)
app.include_router(routes_history.router, prefix=settings.api_prefix)
app.include_router(routes_conversations.router, prefix=settings.api_prefix)
