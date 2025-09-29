from fastapi import APIRouter, FastAPI, Request, Response, Depends
from starlette.middleware.cors import CORSMiddleware
import time
from typing import List, Dict, Any, Callable

from app.core.config import get_settings
from app.core.exceptions import NotFoundException, ServerException
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_duration
from app.middlewares.rate_limit_middleware import RateLimitMiddleware
from app.middlewares.auth_middleware import AuthMiddleware
from app.middlewares.logging_middleware import LoggingMiddleware
from app.middlewares.cache_middleware import CacheMiddleware
from app.middlewares.security_middleware import SecurityMiddleware
from app.security.waf.middleware import WAFMiddleware
from app.middlewares.cors_middleware import CORSHeadersMiddleware
from app.monitoring.tracing.tracer import TracingMiddleware
from app.monitoring.apm.apm_agent import APMAgent
from app.performance.caching_strategies.layered_cache import LayeredCache
from app.cache.keys import create_api_response_key

# Import các router
from app.user_site.api.v1 import (
    users,
    auth,
    books,
    chapters,
    categories,
    authors,
    tags,
    bookmarks,
    bookshelves,
    book_lists,
    book_series,
    reading_sessions,
    reading_goals,
    annotations,
    reviews,
    quotes,
    search,
    recommendations,
    badges,
    social_profiles,
    following,
    notifications,
    preferences,
    subscriptions,
    discussions,
)

settings = get_settings()
logger = get_logger("api_router")
api_router = APIRouter(prefix=settings.API_PREFIX)
apm_agent = APMAgent()


# Đăng ký tất cả các router
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(books.router, prefix="/books", tags=["Books"])
api_router.include_router(chapters.router, prefix="/chapters", tags=["Chapters"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
api_router.include_router(authors.router, prefix="/authors", tags=["Authors"])
api_router.include_router(tags.router, prefix="/tags", tags=["Tags"])
api_router.include_router(bookmarks.router, prefix="/bookmarks", tags=["Bookmarks"])
api_router.include_router(
    bookshelves.router, prefix="/bookshelves", tags=["Bookshelves"]
)
api_router.include_router(book_lists.router, prefix="/book-lists", tags=["Book Lists"])
api_router.include_router(
    book_series.router, prefix="/book-series", tags=["Book Series"]
)
api_router.include_router(
    reading_sessions.router, prefix="/reading-sessions", tags=["Reading Sessions"]
)
api_router.include_router(
    reading_goals.router, prefix="/reading-goals", tags=["Reading Goals"]
)
api_router.include_router(
    annotations.router, prefix="/annotations", tags=["Annotations"]
)
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
api_router.include_router(quotes.router, prefix="/quotes", tags=["Quotes"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(
    recommendations.router, prefix="/recommendations", tags=["Recommendations"]
)
api_router.include_router(badges.router, prefix="/badges", tags=["Badges"])
api_router.include_router(
    social_profiles.router, prefix="/social-profiles", tags=["Social Profiles"]
)
api_router.include_router(following.router, prefix="/following", tags=["Following"])
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["Notifications"]
)
api_router.include_router(
    preferences.router, prefix="/preferences", tags=["Preferences"]
)
api_router.include_router(
    subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"]
)
api_router.include_router(
    discussions.router, prefix="/discussions", tags=["Discussions"]
)


def setup_routers(app: FastAPI):
    """
    Thiết lập tất cả các router và middleware cho ứng dụng.
    """
    # Thêm router vào app
    app.include_router(api_router)

    # Middleware để đo lường thời gian xử lý request
    @app.middleware("http")
    async def add_metrics_middleware(request: Request, call_next):
        """
        Middleware đo lường thời gian xử lý request và ghi nhận metrics.
        """
        # Bắt đầu transaction APM
        with apm_agent.start_transaction(
            f"{request.method} {request.url.path}", "api_request"
        ):
            # Ghi nhận thời gian bắt đầu
            start_time = time.time()

            # Thêm correlation ID để theo dõi request
            correlation_id = (
                request.headers.get("X-Correlation-ID") or f"req-{time.time()}"
            )
            request.state.correlation_id = correlation_id

            try:
                # Gọi next middleware hoặc endpoint
                response = await call_next(request)

                # Tính thời gian xử lý
                process_time = time.time() - start_time
                response.headers["X-Process-Time"] = str(process_time)
                response.headers["X-Correlation-ID"] = correlation_id

                # Ghi nhận metrics
                endpoint = request.url.path
                status_code = response.status_code
                track_request_duration(endpoint, process_time)

                # Ghi log nếu request quá chậm
                if process_time > 1.0:  # Ngưỡng 1 giây
                    logger.warning(
                        f"Request chậm: {request.method} {endpoint} - {process_time:.4f}s",
                        extra={
                            "method": request.method,
                            "endpoint": endpoint,
                            "status_code": status_code,
                            "duration": process_time,
                            "correlation_id": correlation_id,
                        },
                    )

                return response
            except Exception as e:
                # Ghi nhận exception trong APM
                apm_agent.capture_exception()

                # Tính thời gian xử lý
                process_time = time.time() - start_time

                # Ghi log lỗi
                logger.error(
                    f"Lỗi xử lý request: {request.method} {request.url.path} - {str(e)}",
                    extra={
                        "method": request.method,
                        "endpoint": request.url.path,
                        "error": str(e),
                        "duration": process_time,
                        "correlation_id": correlation_id,
                    },
                    exc_info=True,
                )

                # Re-raise exception để được xử lý bởi exception handler
                raise

    # Thêm các middleware (thứ tự từ ngoài vào trong)
    # 1. Security Middleware (đầu tiên để đảm bảo bảo mật sớm nhất)
    app.add_middleware(
        SecurityMiddleware,
        hsts_max_age=31536000,  # 1 năm
        hsts_include_subdomains=True,
        xss_protection=True,
    )

    # 2. WAF Middleware (Web Application Firewall)
    app.add_middleware(WAFMiddleware)

    # 3. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # 4. Rate Limiting Middleware
    app.add_middleware(
        RateLimitMiddleware,
        limit_by_ip=True,
        limit_by_path=True,
        default_limit=settings.RATE_LIMIT_REQUESTS,
        default_window=settings.RATE_LIMIT_DURATION,
        exclude_paths=["/docs", "/redoc", "/openapi.json", "/health"],
    )

    # 5. Logging Middleware
    app.add_middleware(
        LoggingMiddleware,
        log_headers=True,
        log_body=settings.LOG_REQUEST_BODY,
        log_responses=settings.LOG_RESPONSE_BODY,
        log_errors_only=False,
    )

    # 6. Auth Middleware (nếu sử dụng custom auth middleware thay vì Depends)
    app.add_middleware(
        AuthMiddleware,
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        public_paths=[
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/verify-email",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/reset-password",
            "/api/v1/auth/refresh-token",
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        ],
    )

    # 7. Cache Middleware
    app.add_middleware(
        CacheMiddleware,
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
        redis_password=settings.REDIS_PASSWORD,
        default_ttl=300,  # 5 phút
        cache_by_auth=True,
        cache_by_query_params=True,
        exclude_paths=["/api/v1/auth", "/health", "/docs", "/redoc", "/openapi.json"],
    )

    # 8. Tracing Middleware (nếu sử dụng distributed tracing)
    if settings.TRACING_ENABLED:
        app.add_middleware(
            TracingMiddleware, exclude_paths=["/health", "/metrics", "/favicon.ico"]
        )

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check():
        """
        Kiểm tra trạng thái hoạt động của API.
        Trả về 200 OK nếu API đang hoạt động bình thường.
        """
        return {
            "status": "ok",
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
            "timestamp": time.time(),
        }

    # Thêm các exception handler
    @app.exception_handler(NotFoundException)
    async def not_found_exception_handler(request: Request, exc: NotFoundException):
        """
        Exception handler cho Not Found (404).
        """
        return Response(
            status_code=404,
            content=f'{{"detail": "{exc.detail}", "code": "{exc.code}"}}',
            media_type="application/json",
        )

    @app.exception_handler(ServerException)
    async def server_exception_handler(request: Request, exc: ServerException):
        """
        Exception handler cho Internal Server Error (500).
        """
        logger.error(
            f"Server Exception: {exc.detail}",
            extra={"path": request.url.path, "method": request.method},
        )
        return Response(
            status_code=500,
            content=f'{{"detail": "{exc.detail}", "code": "{exc.code}"}}',
            media_type="application/json",
        )

    return app
