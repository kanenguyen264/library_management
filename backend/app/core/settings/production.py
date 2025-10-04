from typing import List, Optional

from pydantic import Field

from .base import BaseSettings


class ProductionSettings(BaseSettings):
    # ===============================
    # ENVIRONMENT SETTINGS
    # ===============================
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    # ===============================
    # APPLICATION SETTINGS
    # ===============================
    PROJECT_NAME: str = "Book Reading API"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Production Book Reading API"

    # ===============================
    # DATABASE SETTINGS - SUPABASE
    # ===============================
    DATABASE_URL: str = Field(..., description="Supabase PostgreSQL connection URL")
    DATABASE_ECHO: bool = False  # Never echo SQL in production

    # ===============================
    # SECURITY SETTINGS
    # ===============================
    SECRET_KEY: str = Field(..., description="JWT secret key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Shorter expiration for production

    # ===============================
    # CORS SETTINGS
    # ===============================
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default_factory=list, description="CORS origins for production frontends"
    )

    # ===============================
    # EMAIL SETTINGS
    # ===============================
    SMTP_HOST: Optional[str] = Field(default=None, description="SMTP server host")
    SMTP_USERNAME: Optional[str] = Field(default=None, description="SMTP username")
    SMTP_PASSWORD: Optional[str] = Field(default=None, description="SMTP password")

    # ===============================
    # REDIS SETTINGS
    # ===============================
    REDIS_URL: Optional[str] = Field(default=None, description="Redis connection URL")

    # ===============================
    # LOGGING SETTINGS
    # ===============================
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FILE: Optional[str] = Field(default=None, description="Log file path")

    # ===============================
    # SUPABASE SETTINGS
    # ===============================
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_KEY: str = Field(..., description="Supabase anon/service role key")
    BUCKET_NAME: str = Field(..., description="Supabase storage bucket name")

    # ===============================
    # MONITORING & OBSERVABILITY
    # ===============================
    SENTRY_DSN: Optional[str] = Field(
        default=None, description="Sentry DSN for error tracking"
    )
    MONITORING_ENABLED: bool = Field(default=True, description="Enable monitoring")

    # ===============================
    # SSL/TLS SETTINGS
    # ===============================
    SSL_KEYFILE: Optional[str] = Field(
        default=None, description="SSL private key file path"
    )
    SSL_CERTFILE: Optional[str] = Field(
        default=None, description="SSL certificate file path"
    )

    # ===============================
    # PRODUCTION SPECIFIC SETTINGS
    # ===============================
    RELOAD_ON_CHANGE: bool = False
    SHOW_DOCS: bool = False  # Hide API docs in production
    PROFILING_ENABLED: bool = False

    model_config = {
        "case_sensitive": True,
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
