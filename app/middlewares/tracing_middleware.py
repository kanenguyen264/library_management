import time
import uuid
import json
import traceback
from typing import Callable, Dict, Optional, List, Any, Union, Set, Tuple
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from app.core.config import get_settings
from app.logging.setup import get_logger
from app.monitoring.tracing.tracer import tracer, SpanKind, TracingMiddleware
from app.core.db import Base
from app.logs_manager.services import create_performance_log
from app.logs_manager.schemas.performance_log import PerformanceLogCreate

settings = get_settings()
logger = get_logger(__name__)

# Re-export TracingMiddleware
TracingMiddleware = TracingMiddleware


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """
    Middleware để trace các HTTP requests.
    Khác với TracingMiddleware ở chỗ cung cấp thêm chi tiết và metrics.
    """

    def __init__(
        self,
        app,
        excluded_paths: Optional[List[str]] = None,
        trace_request_headers: bool = True,
        trace_response_headers: bool = True,
        trace_query_params: bool = True,
        trace_request_body: bool = False,
        trace_response_body: bool = False,
        trace_errors: bool = True,
        slow_threshold_ms: int = 500,
    ):
        """
        Khởi tạo middleware.

        Args:
            app: ASGI app
            excluded_paths: Danh sách đường dẫn loại trừ
            trace_request_headers: Trace request headers
            trace_response_headers: Trace response headers
            trace_query_params: Trace query params
            trace_request_body: Trace request body
            trace_response_body: Trace response body
            trace_errors: Trace errors
            slow_threshold_ms: Ngưỡng thời gian để coi là request chậm (ms)
        """
        super().__init__(app)

        self.excluded_paths = excluded_paths or ["/metrics", "/health", "/static"]
        self.trace_request_headers = trace_request_headers
        self.trace_response_headers = trace_response_headers
        self.trace_query_params = trace_query_params
        self.trace_request_body = trace_request_body
        self.trace_response_body = trace_response_body
        self.trace_errors = trace_errors
        self.slow_threshold_ms = slow_threshold_ms

        logger.info(
            f"Khởi tạo RequestTracingMiddleware với excluded_paths={len(self.excluded_paths)}, "
            f"trace_request_headers={trace_request_headers}, trace_response_headers={trace_response_headers}"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Xử lý request và trace.

        Args:
            request: Request object
            call_next: Hàm xử lý tiếp theo

        Returns:
            Response
        """
        # Kiểm tra exclude
        path = request.url.path
        if any(path.startswith(excluded_path) for excluded_path in self.excluded_paths):
            # Loại trừ, không trace
            return await call_next(request)

        # Trích xuất thông tin request
        method = request.method
        route = path
        client_ip = self._get_client_ip(request)

        # Tạo span attributes
        attributes = {
            "http.method": method,
            "http.url": str(request.url),
            "http.route": route,
            "http.client_ip": client_ip,
            "http.host": request.headers.get("host", ""),
            "http.scheme": request.url.scheme,
            "http.user_agent": request.headers.get("user-agent", ""),
        }

        # Thêm query params
        if self.trace_query_params and request.query_params:
            for key, value in request.query_params.items():
                attributes[f"http.query.{key}"] = value

        # Thêm request headers
        if self.trace_request_headers:
            for key, value in request.headers.items():
                # Bỏ qua một số headers nhạy cảm
                if key.lower() not in ["authorization", "cookie", "x-api-key"]:
                    attributes[f"http.request.header.{key}"] = value

        # Tạo span
        with tracer.create_span(
            name=f"HTTP {method} {route}", kind=SpanKind.SERVER, attributes=attributes
        ) as span:
            # Thời gian bắt đầu
            start_time = time.time()

            # Thêm request body nếu cần
            if self.trace_request_body:
                try:
                    body = await request.body()
                    request.scope["_body"] = body  # Lưu lại để đọc lại sau

                    # Limit kích thước body
                    if len(body) <= 1024:  # Giới hạn 1KB
                        span.set_attribute(
                            "http.request.body", body.decode("utf-8", errors="replace")
                        )
                except Exception as e:
                    logger.error(f"Lỗi khi đọc request body: {str(e)}")

            try:
                # Gọi handler tiếp theo
                response = await call_next(request)

                # Thời gian kết thúc
                duration = time.time() - start_time
                duration_ms = duration * 1000

                # Thêm thông tin response
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.duration", duration)

                # Ghi performance log nếu duration vượt ngưỡng
                if duration_ms > self.slow_threshold_ms:  # 500ms threshold
                    try:
                        # Extract user ID or admin ID if available
                        user_id = getattr(request.state, "user_id", None)
                        admin_id = getattr(request.state, "admin_id", None)

                        # Use the performance log service
                        for db in Base():
                            await create_performance_log(
                                db,
                                PerformanceLogCreate(
                                    component="api",
                                    operation="request",
                                    duration_ms=duration_ms,
                                    endpoint=path,
                                    user_id=user_id,
                                    admin_id=admin_id,
                                    details={
                                        "method": method,
                                        "status_code": response.status_code,
                                        "client_ip": client_ip,
                                        "user_agent": request.headers.get(
                                            "user-agent", ""
                                        ),
                                        "query_params": dict(request.query_params),
                                    },
                                ),
                            )
                            break
                    except Exception as e:
                        logger.warning(f"Không thể ghi performance log: {str(e)}")
                        logger.warning(traceback.format_exc())

                # Thêm response headers
                if self.trace_response_headers:
                    for key, value in response.headers.items():
                        # Bỏ qua một số headers nhạy cảm
                        if key.lower() not in ["set-cookie"]:
                            span.set_attribute(f"http.response.header.{key}", value)

                # Đọc response body nếu cần
                if self.trace_response_body:
                    try:
                        response_body = b""
                        async for chunk in response.body_iterator:
                            response_body += chunk

                        # Limit kích thước body
                        if len(response_body) <= 1024:  # Giới hạn 1KB
                            span.set_attribute(
                                "http.response.body",
                                response_body.decode("utf-8", errors="replace"),
                            )

                        # Tái tạo response
                        response = Response(
                            content=response_body,
                            status_code=response.status_code,
                            headers=dict(response.headers),
                            media_type=response.media_type,
                        )
                    except Exception as e:
                        logger.error(f"Lỗi khi đọc response body: {str(e)}")

                # Thiết lập trạng thái span
                if 200 <= response.status_code < 400:
                    span.set_status("OK")
                else:
                    span.set_status(
                        "ERROR", f"HTTP status code: {response.status_code}"
                    )

                return response

            except Exception as e:
                # Trace error
                if self.trace_errors:
                    # Duration
                    duration = time.time() - start_time
                    span.set_attribute("http.duration", duration)

                    # Error details
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)

                    # Stacktrace
                    tb = traceback.format_exc()
                    if tb:
                        span.add_event("exception", {"stacktrace": tb})

                    span.set_status("ERROR", str(e))

                # Re-raise exception
                raise

    def _get_client_ip(self, request: Request) -> str:
        """
        Lấy IP của client.

        Args:
            request: Request object

        Returns:
            IP address
        """
        # Lấy từ X-Forwarded-For header
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Lấy IP đầu tiên
            return forwarded_for.split(",")[0].strip()

        # Lấy từ client.host
        client_host = request.client.host if request.client else None

        return client_host or "unknown"
