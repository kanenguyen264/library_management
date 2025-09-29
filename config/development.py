"""
Cấu hình cho môi trường phát triển
"""

from config.settings import Settings as BaseSettings


class DevelopmentSettings(BaseSettings):
    """Cấu hình môi trường phát triển"""

    APP_ENV: str = "development"
    DEBUG: bool = True
    DB_ECHO_LOG: bool = True

    # Cấu hình cache sử dụng memory cho development
    CACHE_BACKEND: str = "memory"

    # Dùng thời gian token dài hơn cho development
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 ngày

    # Logging verbose
    LOG_LEVEL: str = "DEBUG"

    # Rate limit cao hơn cho development
    RATE_LIMITING_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 300

    # CORS settings - permissive for development
    BACKEND_CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
    ]

    # Không yêu cầu HTTPS trong development
    REQUIRE_HTTPS: bool = False

    # Tắt một số tính năng bảo mật để dễ phát triển
    IP_WHITELIST_ENABLED: bool = False

    # Upload directory
    UPLOAD_DIR: str = "uploads"  # Relative path

    # File upload settings
    MAX_UPLOAD_SIZE: int = 10485760  # 10MB - Lớn hơn cho development

    class Config:
        env_prefix = "DEV_"


settings = DevelopmentSettings()
