"""
Cấu hình Rate Limiting.

Module này định nghĩa các cấu hình giới hạn tần suất truy cập API:
- Giới hạn truy cập cho các đường dẫn khác nhau
- Giới hạn dựa trên IP, user, token
- Chiến lược xử lý khi vượt quá giới hạn
"""

from typing import Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RateLimitRule(BaseModel):
    """
    Quy tắc giới hạn tần suất truy cập.

    Attributes:
        limit: Số request tối đa trong khoảng thời gian
        period: Khoảng thời gian tính bằng giây
        path_pattern: Pattern đường dẫn để áp dụng quy tắc
        methods: Các HTTP methods áp dụng
        key_func: Hàm để lấy key từ request (ip, user, token)
    """

    limit: int
    period: int  # Seconds
    path_pattern: Optional[str] = None
    methods: Optional[List[str]] = None
    key_func: Literal["ip", "user", "token"] = "ip"

    class Config:
        json_schema_extra = {
            "example": {
                "limit": 100,
                "period": 60,
                "path_pattern": "/api/v1/*",
                "methods": ["GET", "POST"],
                "key_func": "ip",
            }
        }


class RateLimitConfig(BaseSettings):
    """
    Cấu hình giới hạn tần suất truy cập.

    Attributes:
        RATE_LIMIT_ENABLED: Bật/tắt rate limiting
        RATE_LIMIT_DEFAULT_LIMIT: Giới hạn mặc định cho mỗi phút
        RATE_LIMIT_ADMIN_LIMIT: Giới hạn cho admin mỗi phút
        RATE_LIMIT_AUTH_LIMIT: Giới hạn cho auth endpoints mỗi phút
        RATE_LIMIT_HEADER_ENABLED: Bật/tắt headers rate limit
        RATE_LIMIT_STORAGE: Loại lưu trữ cho rate limit (memory, redis)
        RATE_LIMIT_REDIS_URL: URL Redis nếu sử dụng Redis storage
        RATE_LIMIT_STRATEGY: Chiến lược xử lý vượt quá giới hạn (fixed-window, sliding-window)
        RATE_LIMIT_BLOCK_TIME: Thời gian chặn sau khi vượt quá giới hạn (giây)
    """

    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Bật/tắt rate limiting")

    RATE_LIMIT_DEFAULT_LIMIT: int = Field(
        default=120, description="Giới hạn mặc định cho mỗi phút"
    )

    RATE_LIMIT_ADMIN_LIMIT: int = Field(
        default=300, description="Giới hạn cho admin mỗi phút"
    )

    RATE_LIMIT_AUTH_LIMIT: int = Field(
        default=30, description="Giới hạn cho auth endpoints mỗi phút"
    )

    RATE_LIMIT_HEADER_ENABLED: bool = Field(
        default=True, description="Bật/tắt headers rate limit"
    )

    RATE_LIMIT_STORAGE: Literal["memory", "redis"] = Field(
        default="memory", description="Loại lưu trữ cho rate limit"
    )

    RATE_LIMIT_REDIS_URL: Optional[str] = Field(
        default=None, description="URL Redis nếu sử dụng Redis storage"
    )

    RATE_LIMIT_STRATEGY: Literal["fixed-window", "sliding-window"] = Field(
        default="sliding-window", description="Chiến lược xử lý vượt quá giới hạn"
    )

    RATE_LIMIT_BLOCK_TIME: int = Field(
        default=300, description="Thời gian chặn sau khi vượt quá giới hạn (giây)"
    )

    RATE_LIMIT_CUSTOM_RULES: List[Dict] = Field(
        default=[
            {
                "limit": 5,
                "period": 60,
                "path_pattern": "/api/v1/auth/*",
                "methods": ["POST"],
                "key_func": "ip",
            },
            {
                "limit": 300,
                "period": 60,
                "path_pattern": "/api/v1/admin/*",
                "key_func": "user",
            },
        ],
        description="Danh sách quy tắc tùy chỉnh",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="RATE_LIMIT_",
    )

    def get_custom_rules(self) -> List[RateLimitRule]:
        """
        Chuyển đổi danh sách quy tắc từ dict sang RateLimitRule.

        Returns:
            Danh sách RateLimitRule
        """
        return [RateLimitRule(**rule) for rule in self.RATE_LIMIT_CUSTOM_RULES]

    def get_middleware_config(self) -> dict:
        """
        Tạo cấu hình cho middleware rate limit.

        Returns:
            Dict cấu hình middleware
        """
        return {
            "enabled": self.RATE_LIMIT_ENABLED,
            "default_limit": self.RATE_LIMIT_DEFAULT_LIMIT,
            "admin_limit": self.RATE_LIMIT_ADMIN_LIMIT,
            "auth_limit": self.RATE_LIMIT_AUTH_LIMIT,
            "headers_enabled": self.RATE_LIMIT_HEADER_ENABLED,
            "storage": self.RATE_LIMIT_STORAGE,
            "redis_url": self.RATE_LIMIT_REDIS_URL,
            "strategy": self.RATE_LIMIT_STRATEGY,
            "block_time": self.RATE_LIMIT_BLOCK_TIME,
            "custom_rules": self.get_custom_rules(),
        }


# Khởi tạo cấu hình
rate_limit_config = RateLimitConfig()
