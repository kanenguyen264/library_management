import time
import hashlib
from typing import Dict, List, Optional, Tuple, Any, Union, Callable
import redis.asyncio as redis
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from app.core.config import get_settings
from app.security.ddos.protection import DDoSProtection
from app.logging.setup import get_logger
from app.cache.manager import cache_manager

settings = get_settings()
logger = get_logger(__name__)


class AdvancedRateLimiter(BaseHTTPMiddleware):
    """
    Middleware cho rate limiting nâng cao với nhiều tính năng:
    - Nhiều limit khác nhau cho từng API route
    - Hỗ trợ user token và IP
    - Giảm rate limit dần dần khi lạm dụng
    - Burst handling và token buckets
    - Ghi log đầy đủ và thông báo
    """

    def __init__(
        self,
        app: FastAPI,
        redis_client: redis.Redis = None,
        redis_host: str = settings.REDIS_HOST,
        redis_port: int = settings.REDIS_PORT,
        redis_password: str = settings.REDIS_PASSWORD,
        redis_db: int = settings.REDIS_DB,
        default_rate_limit: int = settings.RATE_LIMIT_PER_MINUTE,
        admin_rate_limit: int = settings.RATE_LIMIT_ADMIN_PER_MINUTE,
        ddos_protection: Optional[DDoSProtection] = None,
        enable_token_bucket: bool = True,
        burst_multiplier: float = 2.0,
        per_route_limits: Dict[str, int] = None,
        whitelist_paths: List[str] = None,
    ):
        """
        Initialize AdvancedRateLimiter.

        Args:
            app: FastAPI application
            redis_client: Redis client (optional)
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password
            redis_db: Redis database
            default_rate_limit: Default rate limit per minute
            admin_rate_limit: Rate limit for admin routes
            ddos_protection: DDoS protection instance (optional)
            enable_token_bucket: Whether to use token bucket algorithm
            burst_multiplier: Multiplier for burst capacity
            per_route_limits: Dict mapping route prefixes to rate limits
            whitelist_paths: List of paths to exclude from rate limiting
        """
        super().__init__(app)
        self.redis_client = redis_client

        if not self.redis_client:
            self.redis_client = redis.from_url(
                f"redis://{':' + redis_password + '@' if redis_password else ''}{redis_host}:{redis_port}/{redis_db}"
            )

        self.default_rate_limit = default_rate_limit
        self.admin_rate_limit = admin_rate_limit
        self.enable_token_bucket = enable_token_bucket
        self.burst_multiplier = burst_multiplier
        self.per_route_limits = per_route_limits or {}
        self.whitelist_paths = whitelist_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/favicon.ico",
        ]

        # DDoS protection
        self.ddos_protection = ddos_protection
        if not self.ddos_protection:
            self.ddos_protection = DDoSProtection(redis_client=self.redis_client)

        # Key prefix
        self.key_prefix = "ratelimit:"

    def get_client_identifier(self, request: Request) -> str:
        """
        Lấy định danh của client dựa vào IP và User-Agent.

        Args:
            request: FastAPI request

        Returns:
            Client identifier hash
        """
        # Lấy IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host or "127.0.0.1"

        # Lấy User-Agent
        user_agent = request.headers.get("User-Agent", "")

        # Lấy token từ Authorization header nếu có
        auth_header = request.headers.get("Authorization", "")
        token_part = auth_header.split(" ")[-1] if auth_header else ""

        # Tạo định danh kết hợp
        if token_part and len(token_part) > 10:
            # Ưu tiên dùng token nếu có
            identifier = f"token:{token_part}"
        else:
            # Fallback về IP + User-Agent hash
            raw_id = f"{ip}:{user_agent}"
            identifier = f"ip:{hashlib.md5(raw_id.encode()).hexdigest()}"

        return identifier

    def get_rate_limit_for_path(self, path: str) -> int:
        """
        Lấy rate limit phù hợp cho path.

        Args:
            path: API path

        Returns:
            Rate limit per minute
        """
        # Admin routes
        if "/admin/" in path:
            return self.admin_rate_limit

        # Check specific route limits
        for prefix, limit in self.per_route_limits.items():
            if path.startswith(prefix):
                return limit

        # Default limit
        return self.default_rate_limit

    async def is_path_whitelisted(self, path: str) -> bool:
        """
        Kiểm tra xem path có trong whitelist không.

        Args:
            path: API path

        Returns:
            True if whitelisted
        """
        return any(path.startswith(wpath) for wpath in self.whitelist_paths)

    async def token_bucket_check(
        self, key: str, rate_limit: int, now: float
    ) -> Tuple[bool, int, int]:
        """
        Thực hiện kiểm tra theo thuật toán token bucket.

        Args:
            key: Redis key
            rate_limit: Rate limit per minute
            now: Current timestamp

        Returns:
            Tuple (allowed, tokens_left, reset_seconds)
        """
        # Chuyển đổi rate từ req/min sang tokens/sec
        rate_per_sec = rate_limit / 60.0

        # Max tokens = burst capacity
        max_tokens = rate_limit * self.burst_multiplier / 60.0

        # Get current bucket info
        bucket_key = f"{key}:bucket"
        bucket_info = await self.redis_client.hgetall(bucket_key)

        if not bucket_info:
            # Initialize new bucket with max tokens
            tokens = max_tokens
            last_update = now
        else:
            # Load existing bucket
            tokens = float(bucket_info.get(b"tokens", max_tokens))
            last_update = float(bucket_info.get(b"last_update", now))

        # Calculate tokens to add based on time passed
        time_passed = now - last_update
        new_tokens = min(max_tokens, tokens + time_passed * rate_per_sec)

        # Check if request can be processed
        if new_tokens >= 1.0:
            # Consume a token
            new_tokens -= 1.0
            allowed = True
        else:
            allowed = False

        # Calculate time until reset
        if not allowed:
            reset_seconds = int((1.0 - new_tokens) / rate_per_sec)
        else:
            reset_seconds = 0

        # Update bucket
        await self.redis_client.hmset(
            bucket_key, {"tokens": str(new_tokens), "last_update": str(now)}
        )

        # Set expiration
        await self.redis_client.expire(bucket_key, 3600)  # 1 hour

        return allowed, int(new_tokens), reset_seconds

    async def simple_rate_check(
        self, key: str, rate_limit: int, window: int
    ) -> Tuple[bool, int, int]:
        """
        Thực hiện kiểm tra đếm đơn giản.

        Args:
            key: Redis key
            rate_limit: Rate limit per minute
            window: Current time window

        Returns:
            Tuple (allowed, requests_left, reset_seconds)
        """
        # Tạo key với window hiện tại
        window_key = f"{key}:{window}"

        # Increment counter
        count = await self.redis_client.incr(window_key)

        # Set expiration if new key
        if count == 1:
            await self.redis_client.expire(window_key, 60)

        # Check if allowed
        allowed = count <= rate_limit

        # Calculate reset time
        reset_seconds = 60 - (int(time.time()) % 60)

        return allowed, max(0, rate_limit - count), reset_seconds

    async def dispatch(self, request: Request, call_next):
        # Bypass cho môi trường dev nếu cần
        if settings.APP_ENV == "development" and not settings.DEBUG:
            return await call_next(request)

        # Get path và kiểm tra whitelist
        path = request.url.path
        if await self.is_path_whitelisted(path):
            return await call_next(request)

        # Get client identifier
        client_id = self.get_client_identifier(request)

        # Get IP address
        forwarded = request.headers.get("X-Forwarded-For")
        ip = forwarded.split(",")[0].strip() if forwarded else request.client.host

        # Check DDoS protection first
        if await self.ddos_protection.is_rate_limited(ip):
            # Log bị block
            logger.warning(
                f"DDoS protection blocked request from {ip}",
                extra={
                    "ip": ip,
                    "path": path,
                    "method": request.method,
                    "user_agent": request.headers.get("User-Agent"),
                },
            )

            return JSONResponse(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests. Your IP has been temporarily blocked."
                },
            )

        # Lấy rate limit cho path
        rate_limit = self.get_rate_limit_for_path(path)

        # Tạo key cho rate limiting
        rate_key = f"{self.key_prefix}{client_id}:{path.split('/')[1]}"

        # Kiểm tra rate limit
        if self.enable_token_bucket:
            now = time.time()
            allowed, remaining, reset = await self.token_bucket_check(
                rate_key, rate_limit, now
            )
        else:
            window = int(time.time() / 60)  # 1 phút window
            allowed, remaining, reset = await self.simple_rate_check(
                rate_key, rate_limit, window
            )

        # Nếu không được phép, trả về lỗi
        if not allowed:
            # Record suspicious nếu client liên tục bị rate limit
            await self.ddos_protection.record_suspicious_activity(ip)

            # Log thông tin
            logger.warning(
                f"Rate limit exceeded for {client_id}",
                extra={
                    "ip": ip,
                    "path": path,
                    "method": request.method,
                    "rate_limit": rate_limit,
                },
            )

            return JSONResponse(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Please try again later.",
                    "reset_in_seconds": reset,
                },
            )

        # Proceed with request
        response = await call_next(request)

        # Add rate limiting headers
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)

        return response


def rate_limit(
    limit: int = None,
    per_minute: bool = True,
    period: int = None,
    key_func: Callable = None,
    error_message: str = "Rate limit exceeded. Please try again later.",
):
    """
    Decorator để rate limit các API endpoints cụ thể.

    Args:
        limit: Số lượng request tối đa trong một phút hoặc một giờ.
        per_minute: True nếu limit là per minute, False nếu limit là per hour.
        period: Thời gian (giây) cho rate limit, sẽ ghi đè per_minute nếu được cung cấp.
        key_func: Hàm tùy chỉnh để tạo cache key từ request.
        error_message: Thông báo lỗi khi vượt quá limit.

    Returns:
        Decorator function
    """
    import functools
    from fastapi import Request, HTTPException, status
    import time
    import hashlib
    from app.core.config import get_settings
    from app.cache.manager import cache_manager

    settings = get_settings()

    # Default limits
    if limit is None:
        limit = (
            settings.RATE_LIMIT_PER_MINUTE
            if per_minute
            else settings.RATE_LIMIT_PER_HOUR
        )

    # Xác định ttl dựa trên period hoặc per_minute
    if period is not None:
        ttl = period
        window_divider = period  # Chia thời gian thành các cửa sổ dựa trên period
    else:
        if per_minute:
            ttl = 60  # 1 phút
            window_divider = 60
        else:
            ttl = 3600  # 1 giờ
            window_divider = 3600

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Tìm request object
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if request is None:
                # Không có request, bỏ qua rate limiting
                return await func(*args, **kwargs)

            # Tạo key
            if key_func:
                rate_key = key_func(request)
            else:
                # Lấy IP
                forwarded = request.headers.get("X-Forwarded-For")
                if forwarded:
                    ip = forwarded.split(",")[0].strip()
                else:
                    ip = request.client.host or "127.0.0.1"

                # Lấy User-Agent
                user_agent = request.headers.get("User-Agent", "")

                # Tạo định danh kết hợp
                auth_header = request.headers.get("Authorization", "")
                token_part = auth_header.split(" ")[-1] if auth_header else ""

                if token_part and len(token_part) > 10:
                    # Ưu tiên dùng token nếu có
                    identifier = f"token:{token_part}"
                else:
                    # Fallback về IP + User-Agent hash
                    raw_id = f"{ip}:{user_agent}"
                    identifier = f"ip:{hashlib.md5(raw_id.encode()).hexdigest()}"

                endpoint = request.url.path
                rate_key = f"ratelimit:{identifier}:{endpoint}"

            # Lấy window hiện tại
            window = int(time.time() / window_divider)
            window_key = f"{rate_key}:{window}"

            # Lấy và tăng counter
            count_value = await cache_manager.get(window_key) or 0
            if count_value >= limit:
                # Đã vượt quá limit
                remaining = 0
                reset_after = ttl - int(time.time()) % ttl

                # Set headers
                headers = {
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_after),
                    "Retry-After": str(reset_after),
                }

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=error_message,
                    headers=headers,
                )

            # Tăng counter
            new_count = count_value + 1
            await cache_manager.set(window_key, new_count, ttl=ttl)

            # Gọi hàm gốc
            return await func(*args, **kwargs)

        return wrapper

    return decorator
