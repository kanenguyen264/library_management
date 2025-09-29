import json
import traceback
import logging
from typing import Dict, Any, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    Xử lý HTTP exceptions và trả về response chuẩn.
    """
    error_detail = {"detail": str(exc.detail)}
    if hasattr(exc, "code"):
        error_detail["code"] = exc.code

    # Log lỗi với thông tin chi tiết
    log_data = {
        "path": request.url.path,
        "method": request.method,
        "error": error_detail,
    }

    # Thêm thông tin yêu cầu nếu đang ở môi trường dev
    if settings.DEBUG or settings.APP_ENV.lower() != "production":
        log_data["request_headers"] = dict(request.headers)
        log_data["query_params"] = dict(request.query_params)
        # Không cố gắng đọc body, có thể gây lỗi

    logger.warning(
        f"HTTP {exc.status_code} Error: {json.dumps(error_detail)}", extra=log_data
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_detail,
        headers=exc.headers or {},
    )


async def http_422_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Xử lý lỗi validation với chi tiết về các trường bị lỗi.
    """
    errors = []
    for error in exc.errors():
        error_detail = {
            "field": (
                ".".join([str(loc) for loc in error["loc"]]) if "loc" in error else None
            ),
            "message": error["msg"],
            "type": error["type"],
        }
        errors.append(error_detail)

    content = {"detail": "Validation error", "errors": errors}

    # Log chi tiết lỗi validation
    log_data = {
        "path": request.url.path,
        "method": request.method,
        "validation_errors": errors,
    }

    # Thêm chi tiết yêu cầu trong môi trường dev
    if settings.DEBUG or settings.APP_ENV.lower() != "production":
        log_data["request_headers"] = dict(request.headers)
        log_data["query_params"] = dict(request.query_params)
        # Không cố gắng đọc body, có thể gây lỗi

    logger.warning(f"Validation Error: {json.dumps(content)}", extra=log_data)

    return JSONResponse(
        status_code=422,
        content=content,
    )


async def server_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Xử lý lỗi server 500 với thông tin chi tiết trong môi trường dev.
    """
    error_id = id(exc)
    error_type = type(exc).__name__

    content = {
        "detail": "Internal server error",
        "code": "server_error",
        "error_id": str(error_id),
    }

    # Chuẩn bị dữ liệu log
    log_data = {
        "path": request.url.path,
        "method": request.method,
        "error_id": error_id,
        "error_type": error_type,
        "error_message": str(exc),
    }

    # Trong môi trường dev, thêm traceback và thông tin request
    if settings.DEBUG or settings.APP_ENV.lower() != "production":
        # Thêm traceback vào response
        tb = traceback.format_exc()
        content["error_type"] = error_type
        content["error_message"] = str(exc)
        content["traceback"] = tb.split("\n")

        # Thêm chi tiết request vào log
        log_data["traceback"] = tb
        log_data["request_headers"] = dict(request.headers)
        log_data["query_params"] = dict(request.query_params)
        # Không cố gắng đọc body, có thể gây lỗi

    # Log lỗi chi tiết
    logger.exception(f"Server Error ({error_type}): {str(exc)}", extra=log_data)

    return JSONResponse(
        status_code=500,
        content=content,
    )


async def api_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """
    Xử lý lỗi ValueError thường gặp trong xử lý API.
    """
    content = {"detail": str(exc), "code": "value_error"}

    # Chuẩn bị dữ liệu log
    log_data = {
        "path": request.url.path,
        "method": request.method,
        "error_message": str(exc),
    }

    # Trong môi trường dev, thêm chi tiết
    if settings.DEBUG or settings.APP_ENV.lower() != "production":
        tb = traceback.format_exc()
        content["traceback"] = tb.split("\n")
        log_data["traceback"] = tb
        log_data["request_headers"] = dict(request.headers)
        log_data["query_params"] = dict(request.query_params)

    logger.error(f"API Value Error: {str(exc)}", extra=log_data)

    return JSONResponse(
        status_code=400,
        content=content,
    )
