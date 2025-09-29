from typing import Dict, List, Any, Optional, Union, Set, Tuple
import logging

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.middlewares.cors_middleware import (
    create_cors_middleware,
    CORSHeadersMiddleware,
)
from app.middlewares.logging_middleware import LoggingMiddleware
from app.middlewares.auth_middleware import AuthMiddleware
from app.middlewares.rate_limit_middleware import RateLimitMiddleware
from app.middlewares.security_middleware import SecurityMiddleware
from app.middlewares.tracing_middleware import (
    RequestTracingMiddleware,
    TracingMiddleware,
)
from app.middlewares.cache_middleware import CacheMiddleware

# Import từ module security
from app.security import setup_security
from app.security.headers import setup_secure_headers
from app.security.ddos import setup_rate_limiter
from app.security.waf import setup_waf

settings = get_settings()
logger = get_logger(__name__)


def setup_middlewares(app: FastAPI) -> None:
    """
    Thiết lập các middlewares cho ứng dụng.

    Args:
        app: FastAPI app
    """
    # Thứ tự quan trọng: từ ngoài vào trong
    middleware_count = 0

    # Thiết lập các tính năng bảo mật cơ bản
    if settings.ENABLE_SECURITY_FEATURES:
        security_components = setup_security(app)
        logger.info(
            f"Đã thiết lập các tính năng bảo mật: {list(security_components.keys())}"
        )
        middleware_count += len(security_components)
    else:
        # Thiết lập riêng lẻ các tính năng nếu không dùng setup_security

        # 1. WAF - Web Application Firewall
        if settings.ENABLE_WAF:
            setup_waf(app)
            logger.info("Đã thêm WAF (Web Application Firewall)")
            middleware_count += 1

        # 2. Security Headers
        if settings.ENABLE_SECURITY_MIDDLEWARE:
            setup_secure_headers(app)
            logger.info("Đã thêm Secure Headers Middleware")
            middleware_count += 1

        # 3. Rate Limiter
        if settings.ENABLE_RATE_LIMIT_MIDDLEWARE:
            setup_rate_limiter(app)
            logger.info("Đã thêm Rate Limiter Middleware")
            middleware_count += 1

    # 4. GZip compression - nén phản hồi
    if settings.ENABLE_GZIP_MIDDLEWARE:
        app.add_middleware(
            GZipMiddleware,
            minimum_size=settings.GZIP_MINIMUM_SIZE,
            compresslevel=settings.GZIP_COMPRESSION_LEVEL,
        )
        logger.info("Đã thêm GZipMiddleware")
        middleware_count += 1

    # 5. CORS - cho phép cross-origin requests
    if settings.ENABLE_CORS_MIDDLEWARE:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ALLOW_ORIGINS,
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=settings.CORS_ALLOW_METHODS,
            allow_headers=settings.CORS_ALLOW_HEADERS,
            expose_headers=settings.CORS_EXPOSE_HEADERS,
            max_age=settings.CORS_MAX_AGE,
        )
        logger.info("Đã thêm CORSMiddleware")
        middleware_count += 1

    # 6. Request Tracing - theo dõi các requests
    if settings.ENABLE_TRACING_MIDDLEWARE:
        app.add_middleware(RequestTracingMiddleware)
        logger.info("Đã thêm RequestTracingMiddleware")
        middleware_count += 1

    # 7. Auth - xác thực token (chỉ thêm nếu không dùng security.access_control)
    if settings.ENABLE_AUTH_MIDDLEWARE and not settings.ENABLE_SECURITY_FEATURES:
        app.add_middleware(
            AuthMiddleware,
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        logger.info("Đã thêm AuthMiddleware")
        middleware_count += 1

    # 8. Cache - cache responses
    if settings.ENABLE_CACHE_MIDDLEWARE:
        app.add_middleware(
            CacheMiddleware,
            ttl=settings.CACHE_DEFAULT_TTL,
            cache_get_requests=settings.CACHE_GET_REQUESTS,
        )
        logger.info("Đã thêm CacheMiddleware")
        middleware_count += 1

    # 9. Logging - ghi log requests và responses
    if settings.ENABLE_LOGGING_MIDDLEWARE:
        app.add_middleware(
            LoggingMiddleware,
            log_request_body=settings.LOG_REQUEST_BODY,
            log_response_body=settings.LOG_RESPONSE_BODY,
            db_logging=settings.LOG_TO_DATABASE,
        )
        logger.info("Đã thêm LoggingMiddleware")
        middleware_count += 1

    logger.info(f"Đã thiết lập {middleware_count} middlewares")


def get_admin_middlewares():
    """
    Trả về danh sách middlewares cần thiết cho AdminSite.

    Returns:
        Dict middleware settings
    """
    return {
        "rate_limit": {
            "default_limit": settings.RATE_LIMIT_ADMIN_PER_MINUTE,
            "exclude_paths": ["/docs", "/redoc", "/openapi.json", "/health"],
        },
        "security_headers": {"content_security_policy": settings.ADMIN_CSP_POLICY},
        "auth": {
            "admin_paths": ["/api/v1/admin/"],
            "admin_roles": ["admin", "superadmin"],
        },
    }


def get_user_middlewares():
    """
    Trả về danh sách middlewares cần thiết cho UserSite.

    Returns:
        Dict middleware settings
    """
    return {
        "rate_limit": {
            "default_limit": settings.RATE_LIMIT_PER_MINUTE,
            "exclude_paths": [
                "/docs",
                "/redoc",
                "/openapi.json",
                "/health",
                "/api/v1/auth/",
            ],
        },
        "security_headers": {"content_security_policy": settings.USER_CSP_POLICY},
        "auth": {
            "admin_paths": [],
            "public_paths": [
                "/docs",
                "/redoc",
                "/openapi.json",
                "/metrics",
                "/health",
                "/api/v1/auth/login",
                "/api/v1/auth/register",
                "/api/v1/auth/forgot-password",
                "/api/v1/auth/reset-password",
                "/static",
                "/api/v1/books/public",
            ],
        },
    }
