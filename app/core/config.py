import os
import json
from typing import Any, Dict, List, Optional, Set, Union
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import validator, model_validator, PostgresDsn, Field


class Settings(BaseSettings):
    """Application settings."""

    # App config
    PROJECT_NAME: str = "API ReadingBook"
    APP_NAME: str = Field(PROJECT_NAME)  # Alias for backward compatibility if needed
    APP_VERSION: str = "0.1.0"
    PROJECT_VERSION: str = Field(APP_VERSION)
    PROJECT_DESCRIPTION: str = "API for ReadingBook"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = ""
    API_PREFIX: str = Field(API_V1_STR)  # Alias
    DOCS_URL: str = "/docs"
    OPENAPI_URL: str = f"{API_V1_STR}/openapi.json"  # Default openapi url
    REDOC_URL: str = "/redoc"
    LOGGING_CONFIG_PATH: str = "logging.conf"

    # Server Config
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 8000

    # Security
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "secret-key-for-dev-only")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = Field(ALGORITHM)
    JWT_PUBLIC_KEY: Optional[str] = None
    JWT_PRIVATE_KEY: Optional[str] = None
    AUTH_EXCLUDED_PATHS: Dict[str, List[str]] = {
        "user": [
            # Documentation
            "/user/docs",
            "/user/redoc",
            "/api/v1/user/openapi.json",
            # Auth endpoints
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/reset-password",
            # Basic endpoints
            "/health",
            "/static",
            # Public content browsing APIs
            # Books
            "/api/v1/books",
            "/api/v1/books/trending",
            "/api/v1/books/new-releases",
            "/api/v1/books/*/similar",
            "/api/v1/books/*",
            "/api/v1/books/*/chapters",
            # Categories
            "/api/v1/categories",
            "/api/v1/categories/all",
            "/api/v1/categories/popular",
            "/api/v1/categories/*",
            "/api/v1/categories/slug/*",
            "/api/v1/categories/*/books",
            "/api/v1/categories/*/subcategories",
            "/api/v1/categories/stats/book-counts",
            "/api/v1/categories/path/*",
            # Authors
            "/api/v1/authors",
            "/api/v1/authors/popular",
            "/api/v1/authors/trending",
            "/api/v1/authors/*",
            "/api/v1/authors/slug/*",
            "/api/v1/authors/*/books",
            "/api/v1/authors/*/similar",
            "/api/v1/authors/*/stats",
            "/api/v1/authors/*/complete",
            "/api/v1/authors/genre/*/popular",
            # Tags
            "/api/v1/tags",
            "/api/v1/tags/popular",
            "/api/v1/tags/trending",
            "/api/v1/tags/stats",
            "/api/v1/tags/*",
            "/api/v1/tags/*/books",
            "/api/v1/tags/related/*",
            "/api/v1/tags/suggest/*",
            # Search
            "/api/v1/search",
            "/api/v1/search/suggestions",
            "/api/v1/search/filters",
            "/api/v1/search/popular",
            "/api/v1/search/trending",
            # Chapters - limited to public content
            "/api/v1/chapters/*/content",
            "/api/v1/chapters/*",
            "/api/v1/chapters/book/*",
        ],
        "admin": [
            "/admin/docs",
            "/admin/redoc",
            "/api/v1/admin/openapi.json",
            "/api/v1/admin/auth/login",
            "/api/v1/admin/health",
            "/static/admin",
        ],
    }

    # CAPTCHA settings
    CAPTCHA_ENABLED: bool = False
    CAPTCHA_TYPE: str = "recaptcha"
    RECAPTCHA_SECRET_KEY: str = os.environ.get("RECAPTCHA_SECRET_KEY", "")
    RECAPTCHA_V3_MIN_SCORE: float = 0.5
    HCAPTCHA_SECRET_KEY: str = os.environ.get("HCAPTCHA_SECRET_KEY", "")
    CUSTOM_CAPTCHA_VERIFY_URL: str = os.environ.get("CUSTOM_CAPTCHA_VERIFY_URL", "")

    # Encryption key used for field_encryption and layered_cache
    ENCRYPTION_KEY: str = os.environ.get(
        "ENCRYPTION_KEY", "wU2L_QvYaUCkMZe-v4v2IjJc2kaMTYXTB7MlCO2U8Ko="
    )

    # Password policy
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_MAX_LENGTH: int = 64
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGITS: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True
    PASSWORD_SPECIAL_CHARS: str = "!@#$%^&*()-_=+[]{}|;:,.<>?/~"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    ADMIN_CORS_ORIGINS: List[str] = []
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # Database Components
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "LibiStory"
    POSTGRES_PORT: int = 5432
    # DATABASE_URL will be built or read from env
    DATABASE_URL: Optional[PostgresDsn] = None
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False  # False để tắt logging SQL, True để bật

    # DB Optimization
    DB_MONITOR_CONNECTIONS: bool = False  # Giám sát kết nối database
    DB_INDEX_OPTIMIZER_ENABLED: bool = False  # Bật tối ưu hóa index
    DB_AUTO_CREATE_INDEXES: bool = False  # Tự động tạo index được đề xuất

    # Redis
    REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.environ.get("REDIS_PASSWORD")
    REDIS_DB: int = int(os.environ.get("REDIS_DB", "0"))

    # Cache
    CACHE_ENABLED: bool = True
    CACHE_TYPE: str = os.environ.get(
        "CACHE_TYPE", "redis"
    )  # Default to redis if available
    CACHE_BACKEND: str = os.environ.get(
        "CACHE_BACKEND", "memory"
    )  # memory, redis, memcached
    CACHE_DEFAULT_TTL: int = 3600
    ADMIN_CACHE_DEFAULT_TTL: Optional[int] = None
    CACHE_ALLOW_PICKLE: bool = False
    MEMORY_CACHE_DEFAULT_TTL: int = 3600  # Default TTL for memory cache
    MEMORY_CACHE_MAX_SIZE: int = 10000  # Maximum entries in memory cache

    # Rate limiting
    RATE_LIMITING_ENABLED: bool = True
    RATE_LIMIT_DURATION: int = 60  # seconds
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PER_MINUTE: int = 120  # Số request tối đa trong 1 phút
    RATE_LIMIT_ADMIN_PER_MINUTE: int = 300  # Số request tối đa trong 1 phút cho admin
    ADMIN_RATE_LIMIT_DURATION: Optional[int] = None
    ADMIN_RATE_LIMIT_REQUESTS: Optional[int] = None
    RATE_LIMIT_STORAGE_URL: Optional[str] = None
    RATE_LIMIT_DEFAULT: str = (
        f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_DURATION}s"  # Construct default
    )

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_STRUCTURED: bool = True
    LOG_FILE: Optional[str] = None
    SENTRY_DSN: Optional[str] = os.environ.get("SENTRY_DSN")

    # APM & Tracing
    TRACING_ENABLED: bool = False
    APM_SERVER_URL: Optional[str] = os.environ.get("APM_SERVER_URL")
    APM_PROVIDER: str = "elastic"
    APM_TRANSACTION_SAMPLE_RATE: float = 1.0
    APM_CONFIG_FILE_PATH: Optional[str] = None
    ENVIRONMENT: str = Field(default="development")

    # Security Headers
    CSP_POLICY: Dict[str, str] = {
        "default-src": "'self'",
        "script-src": "'self'",
        "style-src": "'self'",
        "img-src": "'self' data:",
        "font-src": "'self'",
        "connect-src": "'self'",
    }

    # File Storage
    STORAGE_PROVIDER: str = "local"
    STORAGE_LOCAL_PATH: str = "./uploads"

    # Vault (optional)
    VAULT_URL: Optional[str] = os.environ.get("VAULT_URL")
    VAULT_TOKEN: Optional[str] = os.environ.get("VAULT_TOKEN")
    VAULT_MOUNT_POINT: str = "secret"

    # Alerting system
    ALERTING_ENABLED: bool = False
    ALERTING_EMAIL_ENABLED: bool = False
    ALERTING_SLACK_ENABLED: bool = False
    ALERTING_RATE_LIMIT_SECONDS: int = 300
    ALERTING_EMAIL_RECIPIENTS: List[str] = []
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 25
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "alerts@readingbook.com"
    SMTP_TLS: bool = False

    # Middleware shared config
    MIDDLEWARE_EXCLUDED_PATHS: List[str] = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
        "/health",
        "/static",
    ]
    MIDDLEWARE_SENSITIVE_HEADERS: List[str] = ["Authorization", "Cookie", "Set-Cookie"]

    # Logging middleware
    LOG_REQUEST_BODY: bool = False
    LOG_RESPONSE_BODY: bool = False
    LOG_TO_DATABASE: bool = True

    # Metrics settings
    PROMETHEUS_ENABLED: bool = False  # Tắt prometheus để tránh lỗi khi khởi động
    METRICS_ENABLED: bool = False  # Tắt metrics
    METRICS_EXPOSITION_TYPE: str = "http"  # "http" hoặc "push"
    METRICS_PORT: int = 9090
    METRICS_PUSH_GATEWAY: Optional[str] = None
    METRICS_PUSH_INTERVAL: int = 60  # seconds
    APP_METRICS_COLLECTION_INTERVAL: int = 15  # seconds
    SLOW_REQUEST_THRESHOLD: float = 1.0  # seconds
    BUSINESS_METRICS_ENABLED: bool = False  # Ghi nhận metrics kinh doanh

    class Config:
        env_file = ".env"
        case_sensitive = True
        # Allow extra fields from env to avoid breaking if others are present
        extra = "ignore"

    # Validator to build DATABASE_URL if not provided directly
    @model_validator(mode="before")
    @classmethod
    def build_database_url(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if "DATABASE_URL" not in values or not values.get("DATABASE_URL"):
            pg_password = os.environ.get(
                "POSTGRES_PASSWORD", values.get("POSTGRES_PASSWORD")
            )
            if not pg_password:
                print(
                    "Warning: POSTGRES_PASSWORD not found in environment or settings."
                )

            # Ensure asyncpg driver is used for async engine
            driver = "postgresql+asyncpg"
            db_url_str = (
                f"{driver}://{values.get('POSTGRES_USER')}:{pg_password}"
                f"@{values.get('POSTGRES_SERVER')}:{values.get('POSTGRES_PORT')}/{values.get('POSTGRES_DB')}"
            )
            values["DATABASE_URL"] = db_url_str
        # Ensure the final URL is a string if it was parsed as DSN
        elif not isinstance(values.get("DATABASE_URL"), str):
            values["DATABASE_URL"] = str(values["DATABASE_URL"])
        return values

    @validator("APP_ENV")
    def validate_app_env(cls, v: str) -> str:
        """Validate app environment."""
        allowed_envs = {"development", "testing", "staging", "production"}
        if v not in allowed_envs:
            raise ValueError(f"APP_ENV must be one of: {', '.join(allowed_envs)}")
        return v

    @validator("CSP_POLICY", pre=True)
    def parse_csp_policy(cls, v: Union[str, Dict[str, str]]) -> Dict[str, str]:
        """Parse CSP policy from string or dict."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                raise ValueError("CSP_POLICY must be a valid JSON string")
        return v

    @model_validator(mode="after")
    def set_debug_based_on_env(self) -> "Settings":
        """Set DEBUG based on APP_ENV."""
        if self.APP_ENV == "production":
            self.DEBUG = False
        # Also ensure rate limiting uses correct format string after calculation
        self.RATE_LIMIT_DEFAULT = (
            f"{self.RATE_LIMIT_REQUESTS}/{self.RATE_LIMIT_DURATION}s"
        )
        return self

    @property
    def fastapi_kwargs(self) -> Dict[str, Any]:
        """
        Get FastAPI configuration.

        Returns:
            Dictionary with FastAPI configuration
        """
        # Use API_V1_STR for openapi_url consistency
        return {
            "debug": self.DEBUG,
            "docs_url": self.DOCS_URL if self.DEBUG else None,
            "openapi_url": self.OPENAPI_URL if self.DEBUG else None,
            "redoc_url": self.REDOC_URL if self.DEBUG else None,
            "title": self.PROJECT_NAME,
            "version": self.PROJECT_VERSION,
        }

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.APP_ENV == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV == "production"

    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.APP_ENV == "testing"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns:
        Settings instance
    """
    return Settings()
