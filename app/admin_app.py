import os

# Tắt hoàn toàn DataDog APM và logs - Đặt biến môi trường trước tất cả
os.environ["DD_TRACE_ENABLED"] = "false"
os.environ["DD_TELEMETRY_ENABLED"] = "false"
os.environ["DD_TRACE_DEBUG"] = "false"
os.environ["DD_AGENT_HOST"] = "none"
os.environ["DD_LOGGING_RATE_LIMIT"] = "0"
os.environ["DD_INSTRUMENTATION_TELEMETRY_ENABLED"] = "false"
os.environ["DD_TRACE_STARTUP_LOGS"] = "0"

# Vô hiệu hóa DataDog trong Python, thay thế class gây ra lỗi
try:

    class DummyWriter:
        def __init__(self, *args, **kwargs):
            self.enabled = False

        def start(self, *args, **kwargs):
            pass

        def stop(self, *args, **kwargs):
            pass

        def periodic(self, *args, **kwargs):
            pass

        def write(self, *args, **kwargs):
            pass

        def flush_queue(self, *args, **kwargs):
            pass

    # Thử import và thay thế
    import ddtrace.internal
    import ddtrace.internal.telemetry

    # Thay thế writer gây ra thông báo
    ddtrace.internal.telemetry.telemetry_writer = DummyWriter()
    # Cũng vô hiệu hóa tracer
    ddtrace.tracer.enabled = False
except Exception:
    pass

# Tắt log của DataDog - Đặt mức ERROR cho tất cả module DataDog
import logging

for logger_name in [
    "ddtrace",
    "ddtrace.writer",
    "ddtrace.internal",
    "ddtrace.internal.writer",
    "ddtrace.internal.agent",
    "ddtrace.internal.telemetry",
    "ddtrace.internal.telemetry.writer",
]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)
    # Xóa các handlers hiện có
    for handler in logging.getLogger(logger_name).handlers[:]:
        logging.getLogger(logger_name).removeHandler(handler)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.middlewares import (
    AuthMiddleware,
    RateLimitMiddleware,
    LoggingMiddleware,
    CacheMiddleware,
    SecurityMiddleware,
    TracingMiddleware,
)

# Đặt cấu hình logging cơ bản trước
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("admin")

# Initialize settings
settings = get_settings()

# Sau đó mới import setup_logging
try:
    from app.logging.setup import setup_logging, get_admin_logger

    # Cấu hình logging dựa trên thiết lập nếu có
    setup_logging(None)  # Không sử dụng file cấu hình
    logger = get_admin_logger("app")
except ImportError as e:
    logger.warning(f"Không thể thiết lập logging: {e}")
except Exception as e:
    logger.warning(f"Lỗi khi thiết lập logging: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Setup application on startup
    logger.info("Starting Admin API application...")

    # Cố gắng cấu hình logging nếu chưa làm ở trên
    try:
        if "setup_logging" not in locals():
            from app.logging.setup import setup_logging

            setup_logging(settings.LOGGING_CONFIG_PATH)
    except Exception as e:
        logger.warning(f"Lỗi khi thiết lập logging trong lifespan: {e}")

    # Setup tracing if enabled
    if settings.TRACING_ENABLED:
        try:
            from app.monitoring.tracing import setup_tracing

            setup_tracing(app, "admin_api", settings.APM_PROVIDER)
            logger.info("Tracing initialized")
        except Exception as e:
            logger.error(f"Failed to initialize tracing: {e}")

    # Cố gắng áp dụng các tối ưu DB nếu module có sẵn, nhưng bỏ qua nếu lỗi
    try:
        from app.core.events import startup_event_handler

        await startup_event_handler(app)()
        logger.info("Startup event handler completed")
    except Exception as e:
        logger.error(f"Error in startup event handler: {e}")

    yield

    # Run shutdown handlers safely
    try:
        from app.core.events import shutdown_event_handler

        await shutdown_event_handler(app)()
        logger.info("Shutdown event handler completed")
    except Exception as e:
        logger.error(f"Error in shutdown event handler: {e}")

    logger.info("Shutting down Admin API application...")


def create_admin_app() -> FastAPI:
    """Create and configure the Admin FastAPI application."""
    logger.info("Initializing Admin FastAPI application...")

    # Import middlewares an toàn nếu cần
    try:
        from app.middlewares import (
            AuthMiddleware,
            RateLimitMiddleware,
            LoggingMiddleware,
            CacheMiddleware,
            SecurityMiddleware,
            TracingMiddleware,
        )

        middlewares_loaded = True
    except ImportError as e:
        logger.error(f"Không thể import middlewares: {e}")
        middlewares_loaded = False

    # Create FastAPI instance
    app = FastAPI(
        title=f"{settings.PROJECT_NAME} - Admin Site",
        version=settings.PROJECT_VERSION,
        description="API for Administrative tasks and dashboard.",
        docs_url="/admin/docs" if settings.DEBUG else None,
        redoc_url="/admin/redoc" if settings.DEBUG else None,
        openapi_url="/admin/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS Middleware configuration
    if settings.ADMIN_CORS_ORIGINS:
        logger.debug(f"Configuring CORS with origins: {settings.ADMIN_CORS_ORIGINS}")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.ADMIN_CORS_ORIGINS],
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=settings.CORS_ALLOW_METHODS,
            allow_headers=settings.CORS_ALLOW_HEADERS,
        )
    elif settings.BACKEND_CORS_ORIGINS:
        # Fallback to general CORS if admin specific is not set
        logger.debug(
            f"Using default CORS configuration: {settings.BACKEND_CORS_ORIGINS}"
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=settings.CORS_ALLOW_METHODS,
            allow_headers=settings.CORS_ALLOW_HEADERS,
        )

    # Thêm các middlewares nếu đã import thành công
    if middlewares_loaded:
        # Add middlewares in the correct order
        # Order is important - last added is executed first

        # 1. Security headers middleware (first to execute)
        logger.debug("Adding Security Middleware...")
        app.add_middleware(SecurityMiddleware)

        # 2. Tracing middleware for performance monitoring
        if settings.TRACING_ENABLED:
            logger.debug("Adding Tracing Middleware...")
            app.add_middleware(TracingMiddleware)

        # 3. Authentication middleware
        logger.debug("Adding Authentication Middleware...")
        app.add_middleware(
            AuthMiddleware,
            secret_key=settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            public_paths=settings.AUTH_EXCLUDED_PATHS.get(
                "admin",
                [
                    "/admin/docs",
                    "/admin/redoc",
                    "/admin/openapi.json",
                    f"{settings.API_V1_STR}/admin/auth/login",
                    f"{settings.API_V1_STR}/admin/health",
                    "/static/admin",
                ],
            ),
            admin_paths=[f"{settings.API_V1_STR}/admin/"],
            admin_roles=["admin", "superadmin"],
        )

        # 4. Rate limiting middleware
        if settings.RATE_LIMITING_ENABLED:
            logger.debug("Adding Rate Limiting Middleware...")
            app.add_middleware(
                RateLimitMiddleware,
                rate_limit_duration=settings.ADMIN_RATE_LIMIT_DURATION
                or settings.RATE_LIMIT_DURATION,
                rate_limit_requests=settings.ADMIN_RATE_LIMIT_REQUESTS
                or settings.RATE_LIMIT_REQUESTS,
                excluded_paths=[
                    "/admin/docs",
                    "/admin/redoc",
                    "/admin/openapi.json",
                    "/static/admin",
                ],
            )

        # 5. Logging middleware
        logger.debug("Adding Logging Middleware...")
        app.add_middleware(
            LoggingMiddleware,
            log_request_body=True,
            log_response_body=True,
            excluded_paths=[
                "/admin/docs",
                "/admin/redoc",
                "/admin/openapi.json",
                "/static/admin",
            ],
            sensitive_headers=settings.MIDDLEWARE_SENSITIVE_HEADERS,
            log_errors_only=False,
        )

        # 6. Cache middleware (last middleware to execute)
        if settings.CACHE_ENABLED:
            logger.debug("Adding Cache Middleware...")
            app.add_middleware(
                CacheMiddleware,
                default_ttl=settings.ADMIN_CACHE_DEFAULT_TTL
                or settings.CACHE_DEFAULT_TTL,
                excluded_paths=[
                    "/admin/docs",
                    "/admin/redoc",
                    "/admin/openapi.json",
                ],
            )
    else:
        logger.warning("Middlewares weren't loaded, using minimal configuration")

    # Include the Admin API routers
    logger.debug("Including Admin API routers...")
    try:
        from app.admin_site.api.router import admin_router

        app.include_router(admin_router)
        logger.info("Successfully included admin_router")
    except ImportError as e:
        logger.error(f"Failed to import admin API router: {str(e)}")
        # Create placeholder endpoint if router import fails
        from fastapi import APIRouter

        placeholder_router = APIRouter(prefix=f"{settings.API_V1_STR}/admin")

        @placeholder_router.get("/", tags=["Admin"])
        async def admin_root():
            return {"message": "Admin API not fully available due to import issues."}

        app.include_router(placeholder_router)

    # Mount static files if the directory exists
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static", "admin"
    )
    if os.path.exists(static_dir):
        logger.debug(f"Mounting static files from {static_dir}")
        app.mount(
            "/static/admin", StaticFiles(directory=static_dir), name="admin_static"
        )

    logger.info("Admin FastAPI application initialized successfully")
    return app


# Create the admin app instance
admin_app = create_admin_app()

# Export for ASGI servers
app = admin_app
