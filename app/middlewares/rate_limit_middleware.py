from typing import Dict, List, Any, Optional, Union, Set, Tuple, Callable
import time
import logging
import hashlib
import asyncio
from datetime import datetime, timedelta

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from fastapi import HTTPException

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.security.ddos import get_ddos_protection, AdvancedRateLimiter

settings = get_settings()
logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware giới hạn tốc độ request.
    """

    def __init__(
        self,
        app,
        rate_limiter: Optional[AdvancedRateLimiter] = None,
        ddos_protection: Optional[object] = None,
        limit_by_ip: bool = True,
        limit_by_user: bool = True,
        limit_by_path: bool = True,
        default_limit: int = 100,  # requests per minute
        default_window: int = 60,  # seconds
        exclude_paths: Optional[List[str]] = None,
        exclude_ips: Optional[List[str]] = None,
    ):
        """
        Khởi tạo middleware.

        Args:
            app: ASGI app
            rate_limiter: Rate limiter object
            ddos_protection: DDoS protection object
            limit_by_ip: Giới hạn theo IP
            limit_by_user: Giới hạn theo user_id
            limit_by_path: Giới hạn theo path
            default_limit: Giới hạn mặc định
            default_window: Cửa sổ thời gian mặc định (giây)
            exclude_paths: Đường dẫn loại trừ
            exclude_ips: IP loại trừ
        """
        super().__init__(app)

        # Rate limiter - sử dụng singleton từ module security nếu không được cung cấp
        self.rate_limiter = rate_limiter
        if not self.rate_limiter:
            # Lấy hoặc tạo AdvancedRateLimiter
            try:
                from app.security.ddos.rate_limiter import AdvancedRateLimiter

                self.rate_limiter = AdvancedRateLimiter(
                    app=app,
                    default_rate_limit=default_limit,
                    ddos_protection=ddos_protection or get_ddos_protection(),
                )
            except ImportError:
                from app.security.ddos.rate_limiter import RateLimiter

                self.rate_limiter = RateLimiter()
                logger.warning(
                    "Sử dụng RateLimiter cơ bản vì không thể import AdvancedRateLimiter"
                )

        # DDoS protection
        self.ddos_protection = ddos_protection or get_ddos_protection()

        # Cấu hình
        self.limit_by_ip = limit_by_ip
        self.limit_by_user = limit_by_user
        self.limit_by_path = limit_by_path
        self.default_limit = default_limit
        self.default_window = default_window
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/metrics",
            "/health",
            "/static",
        ]
        self.exclude_ips = exclude_ips or ["127.0.0.1", "::1"]

        logger.info(
            f"Khởi tạo RateLimitMiddleware với default_limit={default_limit}/{default_window}s, "
            f"limit_by_ip={limit_by_ip}, limit_by_user={limit_by_user}, limit_by_path={limit_by_path}"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Xử lý request và kiểm tra giới hạn tốc độ.

        Args:
            request: Request object
            call_next: Hàm xử lý tiếp theo

        Returns:
            Response
        """
        # Kiểm tra exclude
        path = request.url.path
        client_ip = self._get_client_ip(request)

        if (
            any(path.startswith(exclude_path) for exclude_path in self.exclude_paths)
            or client_ip in self.exclude_ips
        ):
            # Loại trừ, không kiểm tra
            return await call_next(request)

        # Kiểm tra DDoS protection trước
        if await self.ddos_protection.is_rate_limited(client_ip):
            logger.warning(
                f"DDoS protection blocked request from {client_ip} on {path}"
            )

            return JSONResponse(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded by DDoS protection. Your IP has been temporarily blocked.",
                },
            )

        # Tạo key cho rate limiting
        rate_limit_key = self._create_rate_limit_key(request, client_ip)

        # Determine rate limit based on path and user type
        rate_limit = self.default_limit

        # Adjust limit for admin paths
        if any(path.startswith("/api/v1/admin/") for path in [path]):
            # Admin paths have higher limit
            rate_limit = getattr(
                settings, "RATE_LIMIT_ADMIN_PER_MINUTE", self.default_limit * 2
            )

        # Adjust limit for auth paths
        elif any(path.startswith("/api/v1/auth/") for path in [path]):
            # Auth paths have lower limit to prevent brute force
            rate_limit = getattr(
                settings, "RATE_LIMIT_AUTH_PER_MINUTE", self.default_limit // 2
            )

        # Use advanced rate limiter if it's an AdvancedRateLimiter
        if isinstance(self.rate_limiter, AdvancedRateLimiter):
            # Advanced rate limiter provides more features
            allowed, tokens_left, reset_seconds = (
                await self.rate_limiter.token_bucket_check(
                    key=rate_limit_key, rate_limit=rate_limit, now=time.time()
                )
            )

            remaining = tokens_left
            retry_after = reset_seconds
            current_count = rate_limit - tokens_left
        else:
            # Kiểm tra giới hạn với simple rate check
            result = await self.rate_limiter.simple_rate_check(
                key=rate_limit_key, limit=rate_limit, window=self.default_window
            )

            allowed = result.allowed
            remaining = max(0, result.limit - result.current_count)
            retry_after = result.retry_after
            current_count = result.current_count

        if not allowed:
            # Vượt quá giới hạn, ghi nhận hoạt động đáng ngờ
            await self.ddos_protection.record_suspicious_activity(client_ip)

            # Log warning
            logger.warning(
                f"Rate limit exceeded for {client_ip} on {path}: "
                f"{current_count}/{rate_limit} requests"
            )

            # Tạo response
            response = JSONResponse(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Quá nhiều yêu cầu. Vui lòng thử lại sau.",
                    "retry_after": retry_after,
                },
            )

            # Thêm headers
            response.headers["Retry-After"] = str(retry_after)
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(time.time() + retry_after))

            return response

        # Trong giới hạn, tiếp tục xử lý
        response = await call_next(request)

        # Thêm headers
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(
            int(time.time() + self.default_window)
        )

        return response

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

    def _create_rate_limit_key(self, request: Request, client_ip: str) -> str:
        """
        Tạo key cho rate limiting.

        Args:
            request: Request object
            client_ip: IP của client

        Returns:
            Rate limit key
        """
        # Các thành phần của key
        key_parts = []

        # Thêm IP
        if self.limit_by_ip:
            key_parts.append(f"ip:{client_ip}")

        # Thêm user_id
        if (
            self.limit_by_user
            and hasattr(request.state, "user")
            and isinstance(request.state.user, dict)
        ):
            user_id = request.state.user.get("sub")
            if user_id:
                key_parts.append(f"user:{user_id}")

        # Thêm path
        if self.limit_by_path:
            path = request.url.path
            key_parts.append(f"path:{path}")

        # Tạo key
        if key_parts:
            return ":".join(key_parts)
        else:
            # Fallback đến IP
            return f"ip:{client_ip}"
