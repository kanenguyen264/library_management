import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal


# Configure logging
def setup_logging():
    """Configure logging for the application"""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        ],
    )

    # Set specific loggers to appropriate levels
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured with level: {settings.LOG_LEVEL}")


# Setup logging before creating the app
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger = logging.getLogger(__name__)

    # Startup
    logger.info("FastAPI Book Reading application starting up...")

    # Rebuild Pydantic schemas to resolve forward references
    try:
        from app.schemas import rebuild_schemas

        rebuild_schemas()
        logger.info("Pydantic schemas rebuilt successfully")
    except Exception as e:
        logger.warning(f"Failed to rebuild schemas: {e}")

    yield

    # Shutdown
    logger.info("FastAPI Book Reading application shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="A clean and modern book reading platform API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers để debug lỗi 422
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger = logging.getLogger(__name__)
    logger.error(f"422 Validation Error on {request.method} {request.url}")
    logger.error(f"Request headers: {dict(request.headers)}")
    logger.error(f"Query params: {dict(request.query_params)}")
    logger.error(f"Validation errors: {exc.errors()}")

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": exc.body,
            "url": str(request.url),
            "method": request.method,
        },
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    logger = logging.getLogger(__name__)
    logger.error(f"Pydantic Validation Error on {request.method} {request.url}")
    logger.error(f"Validation errors: {exc.errors()}")

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "url": str(request.url),
            "method": request.method,
        },
    )


# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and load balancers"""
    try:
        # Check database connection
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "database": "connected",
            "environment": settings.ENVIRONMENT,
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
                "database": "disconnected",
            },
        )


# Serve static files for frontend
import os

# Serve static files if they exist (for production Docker builds)
static_user_path = "static/user"
static_admin_path = "static/admin"

if os.path.exists(static_user_path):
    app.mount(
        "/static/user", StaticFiles(directory=static_user_path), name="static_user"
    )

    # Serve user frontend at root
    @app.get("/", include_in_schema=False)
    async def serve_user_frontend():
        return FileResponse(f"{static_user_path}/index.html")

    # Catch-all for user SPA routing
    @app.get("/{path:path}", include_in_schema=False)
    async def catch_all(path: str):
        # Don't serve static files for API routes
        if (
            path.startswith("api/")
            or path.startswith("docs")
            or path.startswith("redoc")
            or path.startswith("admin")
        ):
            raise HTTPException(status_code=404)

        # Check if file exists
        file_path = f"{static_user_path}/{path}"
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)

        # Fallback to index.html for SPA routing
        return FileResponse(f"{static_user_path}/index.html")


if os.path.exists(static_admin_path):
    app.mount(
        "/static/admin", StaticFiles(directory=static_admin_path), name="static_admin"
    )

    # Serve admin frontend
    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/", include_in_schema=False)
    async def serve_admin_frontend():
        return FileResponse(f"{static_admin_path}/index.html")

    # Admin SPA routing
    @app.get("/admin/{path:path}", include_in_schema=False)
    async def admin_catch_all(path: str):
        # Check if file exists
        file_path = f"{static_admin_path}/{path}"
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)

        # Fallback to index.html for SPA routing
        return FileResponse(f"{static_admin_path}/index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
