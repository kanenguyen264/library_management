import logging
from typing import Callable
from fastapi import FastAPI
from app.core.db import engine

# Xóa import này để tránh circular import
# from app.logging.setup import setup_logging
from app.core.config import get_settings
from app.security.headers.secure_headers import SecureHeaders
from app.core.db import Base
from app.admin_site.models import Admin, Role, Permission, AdminRole, RolePermission
from app.user_site.models import User
from app.logs_manager.models import (
    UserActivityLog,
    AdminActivityLog,
    ApiRequestLog,
    AuthenticationLog,
    ErrorLog,
    PerformanceLog,
    SearchLog,
)
from app.core.db_events import register_events
from app.core.model_mixins import register_mixin_events

settings = get_settings()
logger = logging.getLogger(__name__)


async def startup_event_handler(app: FastAPI) -> Callable:
    """
    Khởi tạo các tài nguyên khi ứng dụng khởi động.

    Args:
        app: FastAPI application

    Returns:
        Startup handler function
    """

    async def startup() -> None:
        """Setup các tài nguyên ứng dụng."""
        logger.info("Running application startup handlers")

        # Import trong hàm để tránh circular import
        from app.logging.setup import setup_logging

        # Thiết lập logging
        setup_logging()

        # Khởi tạo database
        logger.info("Creating database tables if they don't exist")
        async with engine.begin() as conn:
            if settings.APP_ENV != "production":
                await conn.run_sync(Base.metadata.create_all)

        # Register database events and mixins
        logger.info("Registering database events and mixins")
        register_events()
        register_mixin_events()

        # Initialize redis connection
        logger.info("Initializing Redis connection")
        try:
            import redis.asyncio as redis

            app.state.redis = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
            )
            # Check connection
            await app.state.redis.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(
                f"Redis connection failed: {e}. Some features may be unavailable."
            )
            app.state.redis = None

        # Initialize secure headers
        app.state.secure_headers = SecureHeaders(csp_policy=settings.CSP_POLICY)

        # Initialize APM if configured
        if settings.APP_ENV == "production":
            try:
                from elasticapm.contrib.starlette import ElasticAPM
                import elasticapm

                apm_config = {
                    "SERVICE_NAME": "api_readingbook",
                    "SERVER_URL": settings.APM_SERVER_URL,
                    "ENVIRONMENT": settings.APP_ENV,
                    "CAPTURE_BODY": "errors",
                    "TRANSACTIONS_IGNORE_PATTERNS": [
                        "^GET /health",
                        "^GET /docs",
                        "^GET /openapi.json",
                    ],
                }

                apm = elasticapm.Client(config=apm_config)
                app.add_middleware(ElasticAPM, client=apm)
                logger.info("APM initialized")
            except ImportError:
                logger.info("ElasticAPM not installed, skipping APM setup")
            except Exception as e:
                logger.warning(f"APM initialization failed: {e}")

        # Load system settings from database
        logger.info("Loading system settings")
        try:
            # This will be implemented according to your system settings logic
            pass
        except Exception as e:
            logger.warning(f"Failed to load system settings: {e}")

        logger.info("Application startup complete")

    return startup


async def shutdown_event_handler(app: FastAPI) -> Callable:
    """
    Giải phóng tài nguyên khi ứng dụng tắt.

    Args:
        app: FastAPI application

    Returns:
        Shutdown handler function
    """

    async def shutdown() -> None:
        """Clean up application resources."""
        logger.info("Running application shutdown handlers")

        # Close database connections
        logger.info("Closing database connections")
        await engine.dispose()

        # Close Redis connections
        if hasattr(app.state, "redis") and app.state.redis:
            logger.info("Closing Redis connections")
            await app.state.redis.close()

        # Close any other resources

        logger.info("Application shutdown complete")

    return shutdown


def register_event_handlers(app: FastAPI) -> None:
    """
    Register event handlers with the application.

    Args:
        app: FastAPI application
    """
    app.add_event_handler("startup", startup_event_handler(app))
    app.add_event_handler("shutdown", shutdown_event_handler(app))
