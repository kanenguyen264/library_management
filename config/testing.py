"""
Cấu hình cho môi trường kiểm thử
"""

from config.settings import Settings as BaseSettings


class TestingSettings(BaseSettings):
    """Cấu hình môi trường kiểm thử"""

    APP_ENV: str = "testing"
    DEBUG: bool = True
    TESTING: bool = True

    # Sử dụng cơ sở dữ liệu riêng cho testing
    POSTGRES_DB: str = "readingbook_test"

    # Giảm thời gian hết hạn token trong testing
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 5

    # Cấu hình cache sử dụng memory cho testing
    CACHE_BACKEND: str = "memory"
    MEMORY_CACHE_DEFAULT_TTL: int = 60  # Thời gian cache ngắn hơn cho tests

    # Logging settings
    LOG_LEVEL: str = "ERROR"  # Chỉ log errors trong testing
    LOG_FILE: str = (
        "logs/test.log"  # Thêm đường dẫn mặc định cho file log trong môi trường test
    )

    # Tắt rate limiting cho testing
    RATE_LIMITING_ENABLED: bool = False

    # CORS settings - permissive for testing
    BACKEND_CORS_ORIGINS: list = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Không yêu cầu HTTPS trong testing
    REQUIRE_HTTPS: bool = False

    # Tắt các tính năng bảo mật có thể ảnh hưởng đến tests
    IP_WHITELIST_ENABLED: bool = False

    # Upload directory
    UPLOAD_DIR: str = "tests/uploads"  # Thư mục uploads riêng cho tests

    # Redis settings - sử dụng database riêng cho testing
    REDIS_DB: int = 15
    REDIS_CACHE_DB: int = 14

    class Config:
        env_prefix = "TEST_"


settings = TestingSettings()
