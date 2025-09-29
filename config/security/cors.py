"""
Cấu hình Cross-Origin Resource Sharing (CORS).

Module này định nghĩa các cấu hình CORS cho ứng dụng:
- Các domain được phép truy cập
- Headers được phép
- Methods được phép
- Credentials
"""

from typing import List, Union, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CORSConfig(BaseSettings):
    """
    Cấu hình CORS (Cross-Origin Resource Sharing).

    Attributes:
        CORS_ALLOW_ORIGINS: Danh sách các domain được phép truy cập
        CORS_ALLOW_ORIGIN_REGEX: Regex cho domain được phép
        CORS_ALLOW_METHODS: Danh sách các HTTP methods được phép
        CORS_ALLOW_HEADERS: Danh sách các headers được phép
        CORS_ALLOW_CREDENTIALS: Cho phép gửi credentials
        CORS_EXPOSE_HEADERS: Headers được phơi bày cho client
        CORS_MAX_AGE: Thời gian cache preflight requests (giây)
    """

    CORS_ALLOW_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Danh sách các domain được phép truy cập",
    )

    CORS_ALLOW_ORIGIN_REGEX: Optional[str] = Field(
        default=None, description="Regex pattern cho các domain được phép"
    )

    CORS_ALLOW_METHODS: List[str] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="Danh sách các HTTP methods được phép",
    )

    CORS_ALLOW_HEADERS: List[str] = Field(
        default=["Authorization", "Content-Type", "Accept", "Origin", "User-Agent"],
        description="Danh sách các headers được phép",
    )

    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True, description="Cho phép gửi credentials (cookies, auth headers)"
    )

    CORS_EXPOSE_HEADERS: List[str] = Field(
        default=[], description="Headers được phơi bày cho client"
    )

    CORS_MAX_AGE: int = Field(
        default=600, description="Thời gian cache preflight requests (giây)"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="CORS_",
    )

    def get_cors_middleware_kwargs(self) -> dict:
        """
        Tạo kwargs cho CORSMiddleware của FastAPI.

        Returns:
            Dict tham số cho CORSMiddleware
        """
        return {
            "allow_origins": self.CORS_ALLOW_ORIGINS,
            "allow_origin_regex": self.CORS_ALLOW_ORIGIN_REGEX,
            "allow_methods": self.CORS_ALLOW_METHODS,
            "allow_headers": self.CORS_ALLOW_HEADERS,
            "allow_credentials": self.CORS_ALLOW_CREDENTIALS,
            "expose_headers": self.CORS_EXPOSE_HEADERS,
            "max_age": self.CORS_MAX_AGE,
        }


# Khởi tạo cấu hình
cors_config = CORSConfig()
