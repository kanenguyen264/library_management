"""
Cấu hình cơ bản cho toàn bộ ứng dụng, tải các biến môi trường
"""

import os
from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, EmailStr, PostgresDsn, field_validator, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình cơ bản cho ứng dụng"""

    # Thông tin ứng dụng
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "ReadingBook API"

    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Cấu hình cơ sở dữ liệu
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: str = "5432"
    DB_ECHO_LOG: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    SQLALCHEMY_DATABASE_URI: Optional[PostgresDsn] = None
    ASYNC_SQLALCHEMY_DATABASE_URI: Optional[str] = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v

        port = values.data.get("POSTGRES_PORT")
        # Chuyển string thành integer
        if isinstance(port, str):
            port = int(port)

        return PostgresDsn.build(
            scheme="postgresql",
            username=values.data.get("POSTGRES_USER"),
            password=values.data.get("POSTGRES_PASSWORD"),
            host=values.data.get("POSTGRES_SERVER"),
            port=port,  # Đã là integer
            path=f"{values.data.get('POSTGRES_DB') or ''}",
        )

    @field_validator("ASYNC_SQLALCHEMY_DATABASE_URI", mode="before")
    def assemble_async_db_connection(
        cls, v: Optional[str], values: Dict[str, Any]
    ) -> Any:
        if isinstance(v, str):
            return v

        postgres_dsn = values.data.get("SQLALCHEMY_DATABASE_URI")
        if postgres_dsn:
            return str(postgres_dsn).replace("postgresql://", "postgresql+asyncpg://")
        return None

    # Bảo mật
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_CACHE_DB: int = 1  # Separate DB for cache

    # Cache settings
    CACHE_BACKEND: str = "memory"  # memory, redis, multi_level
    CACHE_KEY_PREFIX: str = "api_readingbook"
    MEMORY_CACHE_MAX_SIZE: int = 10000
    MEMORY_CACHE_DEFAULT_TTL: int = 3600  # 1 hour

    # Email
    SMTP_TLS: bool = True
    SMTP_PORT: Optional[int] = None
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[EmailStr] = None
    EMAILS_FROM_NAME: Optional[str] = None

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: Optional[str] = None
    LOG_JSON_FORMAT: bool = False
    LOG_ROTATION: bool = True
    LOG_MAX_BYTES: int = 10485760  # 10MB
    LOG_BACKUP_COUNT: int = 5

    # Security settings - Integrated from security module
    # These values will be overridden by the security module's settings
    # if they are specified in the environment

    # Rate limiting
    RATE_LIMITING_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_ADMIN_PER_MINUTE: int = 300

    # IP whitelist
    IP_WHITELIST_ENABLED: bool = False

    # Compliance
    REQUIRE_HTTPS: bool = True
    SESSION_TIMEOUT: int = 3600  # 1 hour

    # File upload
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 5242880  # 5MB
    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "pdf"]

    # Feature flags
    ENABLE_SWAGGER: bool = True
    ENABLE_REDOC: bool = True
    ENABLE_ADMIN_SITE: bool = True
    ENABLE_USER_SITE: bool = True

    # Cấu hình model
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    # Helpers
    def get_db_pool_settings(self) -> Dict[str, Any]:
        """
        Lấy cấu hình pool cho SQLAlchemy.

        Returns:
            Dict cấu hình pool
        """
        # Import config from scaling module if autoscaling is enabled
        try:
            from config.scaling.autoscaling import autoscaling_config

            if autoscaling_config.AUTOSCALING_ENABLED:
                # Adjust DB pool size based on autoscaling config
                max_connections = autoscaling_config.calculate_max_db_connections()
                return {
                    "pool_size": min(
                        max_connections // 2, 20
                    ),  # Don't exceed 20 by default
                    "max_overflow": max_connections - (max_connections // 2),
                    "pool_timeout": self.DB_POOL_TIMEOUT,
                }
        except ImportError:
            pass

        # Default configuration
        return {
            "pool_size": self.DB_POOL_SIZE,
            "max_overflow": self.DB_MAX_OVERFLOW,
            "pool_timeout": self.DB_POOL_TIMEOUT,
        }

    def get_auth_settings(self) -> Dict[str, Any]:
        """
        Lấy cấu hình xác thực.

        Returns:
            Dict cấu hình xác thực
        """
        # Import config from security module
        try:
            from config.security.compliance import compliance_config

            return {
                "token_expire_minutes": self.ACCESS_TOKEN_EXPIRE_MINUTES,
                "algorithm": self.ALGORITHM,
                "password_policy": compliance_config.get_password_policy(),
                "login_policy": compliance_config.get_login_policy(),
                "session_timeout": compliance_config.COMPLIANCE_SESSION_TIMEOUT,
            }
        except ImportError:
            # Default configuration
            return {
                "token_expire_minutes": self.ACCESS_TOKEN_EXPIRE_MINUTES,
                "algorithm": self.ALGORITHM,
            }

    def get_cors_settings(self) -> Dict[str, Any]:
        """
        Lấy cấu hình CORS.

        Returns:
            Dict cấu hình CORS
        """
        # Import config from security module
        try:
            from config.security.cors import cors_config

            return cors_config.get_cors_middleware_kwargs()
        except ImportError:
            # Default configuration
            return {
                "allow_origins": self.BACKEND_CORS_ORIGINS,
                "allow_credentials": True,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
            }

    def get_redis_url(self) -> str:
        """
        Lấy URL Redis.

        Returns:
            URL Redis
        """
        auth_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def get_redis_cache_url(self) -> str:
        """
        Lấy URL Redis cho cache.

        Returns:
            URL Redis cho cache
        """
        auth_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_CACHE_DB}"

    def is_development(self) -> bool:
        """
        Kiểm tra xem có phải môi trường phát triển không.

        Returns:
            True nếu là môi trường phát triển
        """
        return self.APP_ENV.lower() == "development"

    def is_production(self) -> bool:
        """
        Kiểm tra xem có phải môi trường sản xuất không.

        Returns:
            True nếu là môi trường sản xuất
        """
        return self.APP_ENV.lower() == "production"

    def is_testing(self) -> bool:
        """
        Kiểm tra xem có phải môi trường kiểm thử không.

        Returns:
            True nếu là môi trường kiểm thử
        """
        return self.APP_ENV.lower() == "testing"


settings = Settings()
