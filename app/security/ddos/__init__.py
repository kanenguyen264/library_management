"""
Module bảo vệ DDoS (DDoS Protection) - Cung cấp các tính năng bảo vệ chống tấn công từ chối dịch vụ.

Module này cung cấp:
- Phát hiện và chặn các cuộc tấn công DDoS
- Rate limiting cho các API dựa trên IP, người dùng và endpoint
- Hệ thống phân loại và theo dõi client theo tham số hành vi
- Whitelist và blacklist các IP
"""

from app.security.ddos.protection import DDoSProtection
from app.security.ddos.rate_limiter import AdvancedRateLimiter

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo singleton DDoS Protection
_ddos_protection = None


def get_ddos_protection():
    """
    Lấy hoặc khởi tạo singleton DDoSProtection.

    Returns:
        DDoSProtection instance
    """
    global _ddos_protection
    if _ddos_protection is None:
        # Lấy whitelist và blacklist từ cài đặt
        whitelist = settings.IP_WHITELIST if hasattr(settings, "IP_WHITELIST") else []
        blacklist = settings.IP_BLACKLIST if hasattr(settings, "IP_BLACKLIST") else []

        _ddos_protection = DDoSProtection(
            whitelist=whitelist,
            blacklist=blacklist,
            rate_limits={
                "normal": settings.RATE_LIMIT_PER_MINUTE,
                "suspicious": settings.RATE_LIMIT_PER_MINUTE // 3,
                "bot": settings.RATE_LIMIT_PER_MINUTE // 10,
            },
            window_seconds=60,
            block_duration=settings.BLOCK_DURATION_SECONDS,
        )

        logger.info("Đã khởi tạo DDoS Protection")

    return _ddos_protection


def setup_rate_limiter(app):
    """
    Thiết lập Rate Limiter middleware cho ứng dụng.

    Args:
        app: Ứng dụng FastAPI

    Returns:
        AdvancedRateLimiter instance
    """
    if not settings.RATE_LIMITING_ENABLED:
        logger.info("Rate limiting không được bật trong cài đặt")
        return None

    # Lấy danh sách đường dẫn được loại trừ
    whitelist_paths = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/favicon.ico",
        "/static/",
    ]

    # Lấy giới hạn tốc độ cho từng route
    per_route_limits = {
        "/api/v1/auth": settings.RATE_LIMIT_AUTH_PER_MINUTE,
        "/api/v1/admin": settings.RATE_LIMIT_ADMIN_PER_MINUTE,
    }

    # Thêm middleware
    rate_limiter = AdvancedRateLimiter(
        app=app,
        default_rate_limit=settings.RATE_LIMIT_PER_MINUTE,
        admin_rate_limit=settings.RATE_LIMIT_ADMIN_PER_MINUTE,
        ddos_protection=get_ddos_protection(),
        per_route_limits=per_route_limits,
        whitelist_paths=whitelist_paths,
    )

    app.add_middleware(AdvancedRateLimiter)
    logger.info("Đã thiết lập Advanced Rate Limiter")

    return rate_limiter


# Export các components
__all__ = [
    "DDoSProtection",
    "AdvancedRateLimiter",
    "get_ddos_protection",
    "setup_rate_limiter",
]
