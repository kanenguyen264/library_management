"""
Module bảo mật HTTP Headers - Cung cấp các tính năng bảo mật thông qua HTTP headers.

Module này cung cấp:
- Content Security Policy (CSP)
- Strict Transport Security (HSTS)
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
"""

from app.security.headers.secure_headers import SecureHeaders, SecureHeadersMiddleware

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo singleton SecureHeaders
_secure_headers = None


def get_secure_headers():
    """
    Lấy hoặc khởi tạo singleton SecureHeaders.

    Returns:
        SecureHeaders instance
    """
    global _secure_headers
    if _secure_headers is None:
        _secure_headers = SecureHeaders(
            csp_policy=settings.CSP_POLICY,
            hsts_max_age=settings.HSTS_MAX_AGE,
            frame_options=settings.FRAME_OPTIONS,
            content_type_options="nosniff",
            xss_protection="1; mode=block",
            referrer_policy="strict-origin-when-cross-origin",
            include_powered_by=settings.INCLUDE_POWERED_BY,
        )
        logger.info("Đã khởi tạo Secure Headers")

    return _secure_headers


def setup_secure_headers(app):
    """
    Thiết lập Secure Headers middleware cho ứng dụng.

    Args:
        app: Ứng dụng FastAPI

    Returns:
        SecureHeadersMiddleware instance
    """
    headers = get_secure_headers()

    # Thêm middleware
    app.add_middleware(SecureHeadersMiddleware, secure_headers=headers)

    logger.info("Đã thiết lập Secure Headers Middleware")
    return headers


# Các HTTP Security Headers phổ biến và giá trị mặc định
DEFAULT_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
}

# Export các components
__all__ = [
    "SecureHeaders",
    "SecureHeadersMiddleware",
    "get_secure_headers",
    "setup_secure_headers",
    "DEFAULT_SECURITY_HEADERS",
]
