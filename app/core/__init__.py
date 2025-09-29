"""
Core module - Chứa các thành phần cốt lõi của ứng dụng

Module này bao gồm:
- Config: Cấu hình ứng dụng
- Constants: Các hằng số toàn cục
- Events: Các event handler khi khởi động/tắt ứng dụng
- Exceptions: Các exception tùy chỉnh
"""

from app.core.config import get_settings, Settings
from app.core.constants import *
from app.core.events import register_event_handlers
from app.core.exceptions import (
    APIException,
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    RateLimitException,
    ServerException,
    ServiceUnavailableException,
    ValidationException,
    TokenException,
    InvalidToken,
    TokenExpired,
)

__all__ = [
    "get_settings",
    "Settings",
    "register_event_handlers",
    "APIException",
    "BadRequestException",
    "UnauthorizedException",
    "ForbiddenException",
    "NotFoundException",
    "ConflictException",
    "RateLimitException",
    "ServerException",
    "ServiceUnavailableException",
    "ValidationException",
    "TokenException",
    "InvalidToken",
    "TokenExpired",
]
