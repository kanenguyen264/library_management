"""
Cấu hình cho môi trường sản xuất
"""

from config.settings import Settings as BaseSettings


class ProductionSettings(BaseSettings):
    """Cấu hình môi trường sản xuất"""

    APP_ENV: str = "production"
    DEBUG: bool = False
    DB_ECHO_LOG: bool = False

    # Tăng cường bảo mật và hiệu suất cho môi trường production
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30
    DB_POOL_TIMEOUT: int = 60

    # Token hết hạn sau thời gian ngắn hơn
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # Cache settings
    CACHE_BACKEND: str = "redis"  # Sử dụng Redis cho production

    # Logging settings
    LOG_LEVEL: str = "WARNING"
    LOG_JSON_FORMAT: bool = (
        True  # JSON logging for better integration with log management systems
    )
    LOG_ROTATION: bool = True
    LOG_FILE: str = "/var/log/api_readingbook/app.log"

    # Security settings
    RATE_LIMITING_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60  # Giảm rate limit trong production

    # CORS settings - should be restricted
    BACKEND_CORS_ORIGINS: list = ["https://readingbook.example.com"]

    # Force HTTPS
    REQUIRE_HTTPS: bool = True

    # Upload directory
    UPLOAD_DIR: str = "/var/data/api_readingbook/uploads"

    # Redis settings
    REDIS_HOST: str = "redis"  # Use service name in production

    class Config:
        env_prefix = "PROD_"


settings = ProductionSettings()
