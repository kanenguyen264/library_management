from typing import List, Optional

from pydantic import Field

from .base import BaseSettings


class DevelopmentSettings(BaseSettings):
    # ===============================
    # ENVIRONMENT SETTINGS
    # ===============================
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # ===============================
    # APPLICATION SETTINGS
    # ===============================
    PROJECT_NAME: str = "Book Reading API - Development"
    VERSION: str = "1.0.0-dev"
    DESCRIPTION: str = "Development environment for Book Reading API"

    # ===============================
    # DATABASE SETTINGS - SUPABASE
    # ===============================
    DATABASE_URL: str = "postgresql://postgres.lxijhkgzxpxcrutckfxk:Ay5OeoKy6aaOvnfr@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
    DATABASE_ECHO: bool = True  # Show SQL queries in development

    # ===============================
    # SECURITY SETTINGS
    # ===============================
    SECRET_KEY: str = (
        "development-secret-key-please-change-in-production-environment-32-chars"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # Longer expiration for development

    # ===============================
    # CORS SETTINGS
    # ===============================
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5174",  # Vite dev server alternate port
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    # ===============================
    # PAGINATION SETTINGS
    # ===============================
    DEFAULT_PAGE_SIZE: int = 10  # Smaller page size for development
    MAX_PAGE_SIZE: int = 50

    # ===============================
    # UPLOAD SETTINGS
    # ===============================
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB for development
    ALLOWED_EXTENSIONS: List[str] = [
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "pdf",
        "epub",
        "mobi",
        "txt",
        "docx",
    ]

    # ===============================
    # EMAIL SETTINGS
    # ===============================
    SMTP_HOST: Optional[str] = "smtp.gmail.com"
    SMTP_USERNAME: Optional[str] = "thaixs18@gmail.com"
    SMTP_PASSWORD: Optional[str] = "hyiz dykv bagn okfe"

    # ===============================
    # REDIS SETTINGS
    # ===============================
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    REDIS_EXPIRE: int = 1800  # 30 minutes

    # ===============================
    # LOGGING SETTINGS
    # ===============================
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: Optional[str] = "logs/app.log"

    # ===============================
    # RATE LIMITING
    # ===============================
    RATE_LIMIT_ENABLED: bool = False  # Disabled for development
    RATE_LIMIT_REQUESTS: int = 1000

    # ===============================
    # SUPABASE SETTINGS
    # ===============================
    SUPABASE_URL: str = "https://bhffkfkiseikbllmvzaj.supabase.co"
    SUPABASE_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJoZmZrZmtpc2Vpa2JsbG12emFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE5MDM3NDYsImV4cCI6MjA2NzQ3OTc0Nn0.2vDFuV8tveXwSbSGoVcmBOaYAt4CejAvMJk4iEAS1no"
    BUCKET_NAME: str = "book-file-dev"

    # ===============================
    # DEVELOPMENT SPECIFIC SETTINGS
    # ===============================
    RELOAD_ON_CHANGE: bool = True
    SHOW_DOCS: bool = True
    PROFILING_ENABLED: bool = True

    model_config = {
        "case_sensitive": True,
        "env_file": ".env.dev",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
