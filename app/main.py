import logging
import os
import sys
import importlib
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings

# Import ColorizedFormatter first for initial logging setup
try:
    from app.logging.formatters import ColorizedFormatter

    colorized_formatter = ColorizedFormatter()

    # Set up a handler with the colorized formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(colorized_formatter)
    console_handler.setLevel(logging.DEBUG)  # Đảm bảo log tất cả các cấp độ

    # Đặt cấu hình logging cơ bản với colorized formatter
    logging.basicConfig(level=logging.DEBUG, handlers=[console_handler])
except ImportError:
    # Fallback to basic logging if formatter can't be imported
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

logger = logging.getLogger("main")

# Initialize settings
settings = get_settings()

# Sau đó mới import setup_logging
try:
    from app.logging.setup import setup_logging, get_logger, force_colorize_all_loggers

    # Cấu hình logging dựa trên thiết lập nếu có
    setup_logging(None)  # Không sử dụng file cấu hình
    logger = get_logger("main")

    # Force colorize all loggers to ensure consistent appearance
    force_colorize_all_loggers()
except ImportError as e:
    logger.warning(f"Không thể thiết lập logging: {e}")
    logger.warning(traceback.format_exc())
except Exception as e:
    logger.warning(f"Lỗi khi thiết lập logging: {e}")
    logger.warning(traceback.format_exc())

# Disable metrics to avoid startup issues (can be removed if metrics are properly configured)
sys.metrics_enabled = False
sys.prometheus_enabled = False

# Configure libuv event loop for better performance if not on Windows
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
    logger.info("Starting main API application...")

    # Yield first to ensure base application starts properly
    # before attempting any optimizations or risky operations
    try:
        yield

        # Apply optimizations after basic startup is complete
        try:
            from app.performance.db_optimization import apply_db_optimizations

            # Áp dụng và kiểm tra kết quả
            optimizations_result = apply_db_optimizations()
            if optimizations_result:
                logger.info("Applied database optimizations successfully")
            else:
                logger.warning("Database optimizations were only partially applied")
        except ImportError as e:
            logger.warning(f"Database optimization module not available: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to apply database optimizations: {e}")

        # Run shutdown code
        logger.info("Shutting down main API application...")
    except Exception as e:
        logger.error(f"Error in application lifespan: {e}")
        # Still need to yield to prevent hanging
        yield


def import_router(module_path, router_name):
    """
    Import router từ module path và tên router.
    Trả về router nếu thành công, None nếu thất bại.
    """
    try:
        module = importlib.import_module(module_path)
        return getattr(module, router_name, None)
    except ImportError as e:
        logger.error(f"Error importing {module_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error importing {module_path}: {e}")
        return None


def create_main_app() -> FastAPI:
    """Create and configure the main FastAPI application."""
    logger.info("Initializing Main FastAPI application...")

    try:
        # Create FastAPI instance with no docs URL (we'll add custom ones)
        app = FastAPI(
            title=settings.PROJECT_NAME,
            version=settings.PROJECT_VERSION,
            description=settings.PROJECT_DESCRIPTION,
            # Set docs_url to None as we'll use our custom implementation
            docs_url=None,
            redoc_url=None,
            # Keep the OpenAPI URL for our custom docs to use
            openapi_url="/openapi.json" if settings.DEBUG else None,
            lifespan=lifespan,
        )

        # Check database connection before proceeding
        @app.on_event("startup")
        async def startup_db_check():
            from app.core.db import check_database_connection

            logger.info("Checking database connection...")
            if not await check_database_connection():
                logger.error(
                    "Database connection failed! Application may not function correctly."
                )
                # We don't raise an exception here to allow the app to start even with DB issues
                # This makes troubleshooting easier

        # Root endpoint
        @app.get("/")
        async def read_root():
            """Main application endpoint."""
            return {
                "app": settings.PROJECT_NAME,
                "version": settings.PROJECT_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "endpoints": {
                    "user_api": "/api/v1",
                    "admin_api": "/api/v1/admin",
                    "docs": "/docs" if settings.DEBUG else None,
                    "health": "/health",
                },
            }

        # Health check endpoint
        @app.get("/health")
        async def health_check():
            """Health check endpoint for monitoring and load balancers."""
            return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

        # Add request ID middleware
        @app.middleware("http")
        async def add_request_id_middleware(request: Request, call_next):
            """Add a unique request ID and process time to each request."""
            import time

            request_id = str(uuid.uuid4())
            request.state.request_id = request_id

            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)

            return response

        # CORS Middleware
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

        # Exception Handlers for Validation Errors
        from pydantic import ValidationError

        def ensure_serializable(obj):
            """Recursively convert any non-serializable objects to strings"""
            if isinstance(obj, (str, int, float, bool, type(None))):
                return obj
            elif isinstance(obj, Exception):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: ensure_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [ensure_serializable(item) for item in obj]
            else:
                return str(obj)

        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(
            request: Request, exc: RequestValidationError
        ):
            errors = exc.errors()
            error_messages = []

            # Convert all errors to ensure they're serializable
            serializable_errors = ensure_serializable(errors)

            for error in serializable_errors:
                loc = " → ".join(str(l) for l in error.get("loc", []))
                msg = error.get("msg", "")
                error_messages.append(f"{loc}: {msg}")

            error_detail = ", ".join(error_messages)
            logger.warning(f"Request validation error: {error_detail}")

            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Lỗi validation dữ liệu đầu vào",
                    "errors": serializable_errors,
                    "message": error_detail,
                },
            )

        @app.exception_handler(ValidationError)
        async def pydantic_validation_exception_handler(
            request: Request, exc: ValidationError
        ):
            errors = exc.errors()
            error_messages = []

            # Convert all errors to ensure they're serializable
            serializable_errors = ensure_serializable(errors)

            for error in serializable_errors:
                loc = " → ".join(str(l) for l in error.get("loc", []))
                msg = error.get("msg", "")
                error_messages.append(f"{loc}: {msg}")

            error_detail = ", ".join(error_messages)
            logger.warning(f"Pydantic validation error: {error_detail}")

            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Lỗi validation dữ liệu",
                    "errors": serializable_errors,
                    "message": error_detail,
                },
            )

        # Thêm exception handler tổng quan để ghi log tất cả các lỗi
        @app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            """
            Global exception handler để đảm bảo mọi lỗi đều được ghi log
            cùng với traceback đầy đủ.
            """
            error_id = str(uuid.uuid4())
            request_path = request.url.path
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("User-Agent", "unknown")

            # Lấy traceback đầy đủ
            tb = traceback.format_exc()

            # Ghi log chi tiết
            logger.error(
                f"Unhandled exception - ID: {error_id} - Path: {request_path}",
                extra={
                    "error_id": error_id,
                    "path": request_path,
                    "method": request.method,
                    "ip": client_ip,
                    "user_agent": user_agent,
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
            )
            logger.error(f"Traceback for {error_id}:\n{tb}")

            # Trả về lỗi 500 cho client với error_id để theo dõi
            status_code = 500

            # Nếu là HTTPException, sử dụng status code từ nó
            if isinstance(exc, (HTTPException, StarletteHTTPException)):
                status_code = exc.status_code

            # Trả về response
            return JSONResponse(
                status_code=status_code,
                content={
                    "error_id": error_id,
                    "detail": str(exc),
                    "type": exc.__class__.__name__,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        # Kết hợp các router từ user_site và admin_site
        # Thay vì hardcode và fallback, sử dụng phương thức import_router

        # Thêm User API router
        user_router = import_router("app.user_site.api.router", "api_router")
        if user_router:
            logger.info("Kết hợp User API router...")
            app.include_router(user_router, prefix="/api/v1")
        else:
            logger.error("Không thể import User API router")

        # Thêm Admin API router
        admin_router = import_router("app.admin_site.api.router", "admin_router")
        if admin_router:
            logger.info("Kết hợp Admin API router...")
            # Không thêm tiền tố vì admin_router đã có prefix="/api/v1/admin"
            app.include_router(admin_router)
        else:
            logger.error("Không thể import Admin API router")

        # Mount static files if the directory exists
        static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
        if os.path.exists(static_dir):
            logger.debug(f"Mounting static files from {static_dir}")
            app.mount("/static", StaticFiles(directory=static_dir), name="static")

        # Setup categorized Swagger UI if in debug mode
        if settings.DEBUG:
            try:
                from app.core.swagger import setup_categorized_swagger_ui

                logger.info("Setting up categorized Swagger UI documentation")
                setup_categorized_swagger_ui(app)
            except Exception as e:
                logger.error(f"Could not set up Swagger UI: {e}")
                # Fallback to standard docs
                app.docs_url = "/docs"
                app.redoc_url = "/redoc"

        logger.info(
            f"Main FastAPI application initialized successfully. Available at http://{settings.SERVER_HOST}:{settings.SERVER_PORT}"
        )
        return app
    except Exception as e:
        logger.error(f"Error initializing Main FastAPI application: {e}")
        # Create a simple minimal app that can at least start and show error information
        basic_app = FastAPI(
            title=f"{settings.PROJECT_NAME} [ERROR MODE]",
            docs_url="/docs",
            redoc_url="/redoc",
        )

        @basic_app.get("/")
        async def error_root():
            return {
                "error": "Application failed to initialize properly",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        return basic_app


# Create the main app instance
app = create_main_app()
# Run directly with uvicorn
if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting server at {settings.SERVER_HOST}:{settings.SERVER_PORT}")
    uvicorn.run(
        "app.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
