import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import PlainTextResponse
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.errors import (
    http_error_handler,
    http_422_error_handler,
    server_error_handler,
    api_error_handler,
)

# Đặt cấu hình logging cơ bản trước
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("user")

# Initialize settings
settings = get_settings()

# Sau đó mới import setup_logging
try:
    from app.logging.setup import setup_logging, get_user_logger

    # Cấu hình logging dựa trên thiết lập nếu có
    setup_logging(None)  # Không sử dụng file cấu hình
    logger = get_user_logger("app")
except ImportError as e:
    logger.warning(f"Không thể thiết lập logging: {e}")
except Exception as e:
    logger.warning(f"Lỗi khi thiết lập logging: {e}")

# Config libuv event loop for better performance if not on Windows
try:
    if os.name != "nt":
        import uvloop

        uvloop.install()
        logger.info("Using uvloop for improved async performance")
except ImportError:
    logger.warning("uvloop not available, using default event loop")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Setup application on startup
    logger.info("Starting User API application...")

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

            setup_tracing(app, "user_api", settings.APM_PROVIDER)
            logger.info("Tracing initialized")
        except Exception as e:
            logger.error(f"Failed to initialize tracing: {e}")

    # Run startup handlers
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

    logger.info("Shutting down User API application...")


def create_user_app() -> FastAPI:
    """Create and configure the User FastAPI application."""
    logger.info("Initializing User FastAPI application...")

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
        title=f"{settings.PROJECT_NAME} - User Site",
        version=settings.PROJECT_VERSION,
        description=settings.PROJECT_DESCRIPTION,
        docs_url="/user/docs" if not settings.is_production else None,
        redoc_url="/user/redoc" if not settings.is_production else None,
        openapi_url=(
            f"{settings.API_V1_STR}/user/openapi.json"
            if not settings.is_production
            else None
        ),
        lifespan=lifespan,
    )

    # Setup exception handlers
    logger.debug("Registering exception handlers...")
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, http_422_error_handler)
    app.add_exception_handler(Exception, server_error_handler)
    app.add_exception_handler(ValueError, api_error_handler)

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint for monitoring and load balancers."""
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

    # Middleware configuration - order is important
    logger.debug("Configuring middleware...")

    # 1. Request ID middleware - outermost middleware
    @app.middleware("http")
    async def add_request_id_middleware(request: Request, call_next):
        """Add a unique request ID to each request."""
        import uuid

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = datetime.now(timezone.utc)

        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        process_time = (
            datetime.now(timezone.utc) - request.state.start_time
        ).total_seconds()
        response.headers["X-Process-Time"] = str(process_time)

        return response

    # Chỉ thêm các middleware nếu đã import thành công
    if middlewares_loaded:
        # 2. Security Middleware (Headers)
        logger.debug("Adding Security Middleware...")
        app.add_middleware(SecurityMiddleware)

        # 3. CORS Middleware
        if settings.BACKEND_CORS_ORIGINS:
            logger.debug(
                f"Configuring CORS with origins: {settings.BACKEND_CORS_ORIGINS}"
            )
            app.add_middleware(
                CORSMiddleware,
                allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
                allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
                allow_methods=settings.CORS_ALLOW_METHODS,
                allow_headers=settings.CORS_ALLOW_HEADERS,
            )

        # 4. Tracing Middleware (if enabled)
        if settings.TRACING_ENABLED:
            logger.debug("Adding Tracing Middleware...")
            app.add_middleware(TracingMiddleware)

        # 5. Authentication Middleware
        logger.debug("Adding Authentication Middleware...")
        app.add_middleware(
            AuthMiddleware,
            secret_key=settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            public_paths=settings.AUTH_EXCLUDED_PATHS.get(
                "user",
                [
                    # Documentation
                    "/user/docs",
                    "/user/redoc",
                    f"{settings.API_V1_STR}/user/openapi.json",
                    # Auth endpoints
                    f"{settings.API_V1_STR}/auth/login",
                    f"{settings.API_V1_STR}/auth/register",
                    f"{settings.API_V1_STR}/auth/refresh",
                    f"{settings.API_V1_STR}/auth/forgot-password",
                    f"{settings.API_V1_STR}/auth/reset-password",
                    # Basic endpoints
                    "/health",
                    "/static",
                    # Public content browsing APIs
                    # Books
                    f"{settings.API_V1_STR}/books",
                    f"{settings.API_V1_STR}/books/trending",
                    f"{settings.API_V1_STR}/books/new-releases",
                    f"{settings.API_V1_STR}/books/*/similar",
                    f"{settings.API_V1_STR}/books/*",
                    f"{settings.API_V1_STR}/books/*/chapters",
                    # Categories
                    f"{settings.API_V1_STR}/categories",
                    f"{settings.API_V1_STR}/categories/all",
                    f"{settings.API_V1_STR}/categories/popular",
                    f"{settings.API_V1_STR}/categories/*",
                    f"{settings.API_V1_STR}/categories/slug/*",
                    f"{settings.API_V1_STR}/categories/*/books",
                    f"{settings.API_V1_STR}/categories/*/subcategories",
                    f"{settings.API_V1_STR}/categories/stats/book-counts",
                    f"{settings.API_V1_STR}/categories/path/*",
                    # Authors
                    f"{settings.API_V1_STR}/authors",
                    f"{settings.API_V1_STR}/authors/popular",
                    f"{settings.API_V1_STR}/authors/trending",
                    f"{settings.API_V1_STR}/authors/*",
                    f"{settings.API_V1_STR}/authors/slug/*",
                    f"{settings.API_V1_STR}/authors/*/books",
                    f"{settings.API_V1_STR}/authors/*/similar",
                    f"{settings.API_V1_STR}/authors/*/stats",
                    f"{settings.API_V1_STR}/authors/*/complete",
                    f"{settings.API_V1_STR}/authors/genre/*/popular",
                    # Tags
                    f"{settings.API_V1_STR}/tags",
                    f"{settings.API_V1_STR}/tags/popular",
                    f"{settings.API_V1_STR}/tags/trending",
                    f"{settings.API_V1_STR}/tags/stats",
                    f"{settings.API_V1_STR}/tags/*",
                    f"{settings.API_V1_STR}/tags/*/books",
                    f"{settings.API_V1_STR}/tags/related/*",
                    f"{settings.API_V1_STR}/tags/suggest/*",
                    # Search
                    f"{settings.API_V1_STR}/search",
                    f"{settings.API_V1_STR}/search/suggestions",
                    f"{settings.API_V1_STR}/search/filters",
                    f"{settings.API_V1_STR}/search/popular",
                    f"{settings.API_V1_STR}/search/trending",
                    # Chapters - limited to public content
                    f"{settings.API_V1_STR}/chapters/*/content",  # Kiểm tra quyền sẽ xử lý trong endpoint
                    f"{settings.API_V1_STR}/chapters/*",  # Kiểm tra quyền sẽ xử lý trong endpoint
                    f"{settings.API_V1_STR}/chapters/book/*",
                ],
            ),
        )

        # 6. Rate Limiting Middleware
        if settings.RATE_LIMITING_ENABLED:
            logger.debug("Adding Rate Limiting Middleware...")
            app.add_middleware(
                RateLimitMiddleware,
                rate_limit_duration=settings.RATE_LIMIT_DURATION,
                rate_limit_requests=settings.RATE_LIMIT_REQUESTS,
                excluded_paths=[
                    "/user/docs",
                    "/user/redoc",
                    f"{settings.API_V1_STR}/user/openapi.json",
                    "/static",
                    "/health",
                ],
                path_rates={
                    # Đặt giới hạn thấp hơn cho các API public để tránh lạm dụng
                    f"{settings.API_V1_STR}/books": 60,  # 60 req/min
                    f"{settings.API_V1_STR}/books/*": 30,
                    f"{settings.API_V1_STR}/categories": 60,
                    f"{settings.API_V1_STR}/categories/*": 30,
                    f"{settings.API_V1_STR}/authors": 60,
                    f"{settings.API_V1_STR}/authors/*": 30,
                    f"{settings.API_V1_STR}/tags": 60,
                    f"{settings.API_V1_STR}/search": 30,  # Giới hạn nghiêm ngặt hơn cho search
                    f"{settings.API_V1_STR}/chapters/*": 40,
                },
            )

        # 7. Logging Middleware
        logger.debug("Adding Logging Middleware...")
        app.add_middleware(
            LoggingMiddleware,
            log_request_body=settings.LOG_REQUEST_BODY,
            log_response_body=settings.LOG_RESPONSE_BODY,
            excluded_paths=settings.MIDDLEWARE_EXCLUDED_PATHS,
            sensitive_headers=settings.MIDDLEWARE_SENSITIVE_HEADERS,
        )

        # 8. Cache Middleware
        if settings.CACHE_ENABLED:
            logger.debug("Adding Cache Middleware...")
            app.add_middleware(
                CacheMiddleware,
                default_ttl=settings.CACHE_DEFAULT_TTL,
                excluded_paths=[
                    "/user/docs",
                    "/user/redoc",
                    f"{settings.API_V1_STR}/user/openapi.json",
                    f"{settings.API_V1_STR}/auth/login",
                    f"{settings.API_V1_STR}/auth/register",
                    f"{settings.API_V1_STR}/auth/refresh",
                ],
            )
    else:
        # Nếu không import được middlewares, vẫn thêm CORS cơ bản
        if settings.BACKEND_CORS_ORIGINS:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        logger.warning("Middlewares weren't loaded, using minimal configuration")

    # API Routers - Import safely to avoid circular imports
    logger.debug("Including API routers...")
    try:
        from app.user_site.api.router import api_router

        app.include_router(api_router)
        logger.info("Successfully included user_site API router")
    except ImportError as e:
        logger.error(f"Failed to import user API router: {str(e)}")
        # Create placeholder endpoint if router import fails
        from fastapi import APIRouter

        placeholder_router = APIRouter(prefix=settings.API_V1_STR)

        @placeholder_router.get("/", tags=["User"])
        async def user_root():
            return {"message": "User API not fully available due to import issues."}

        app.include_router(placeholder_router)

    # Mount static files if the directory exists
    static_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static", "user"
    )
    if os.path.exists(static_dir):
        logger.debug(f"Mounting static files from {static_dir}")
        app.mount("/static", StaticFiles(directory=static_dir), name="user_static")

    logger.info("User FastAPI application initialized successfully")
    return app


# Create the user app instance
user_app = create_user_app()

# Export for ASGI servers
app = user_app
