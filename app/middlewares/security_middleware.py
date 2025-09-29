from typing import Dict, List, Any, Optional, Union
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.security.headers import get_secure_headers, SecureHeaders

settings = get_settings()
logger = get_logger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware thêm các header bảo mật.
    """

    def __init__(
        self,
        app,
        secure_headers: Optional[SecureHeaders] = None,
        csp_report_uri: Optional[str] = None,
        hsts_max_age: int = 31536000,  # 1 year
        hsts_include_subdomains: bool = True,
        hsts_preload: bool = False,
        xss_protection: bool = True,
        content_type_options: bool = True,
        frame_options: str = "DENY",
        referrer_policy: str = "strict-origin-when-cross-origin",
        permitted_cross_domain_policies: str = "none",
    ):
        """
        Khởi tạo middleware.

        Args:
            app: ASGI app
            secure_headers: SecureHeaders object
            csp_report_uri: URI báo cáo CSP
            hsts_max_age: HSTS max age (seconds)
            hsts_include_subdomains: HSTS include subdomains
            hsts_preload: HSTS preload
            xss_protection: X-XSS-Protection header
            content_type_options: X-Content-Type-Options header
            frame_options: X-Frame-Options header
            referrer_policy: Referrer-Policy header
            permitted_cross_domain_policies: X-Permitted-Cross-Domain-Policies header
        """
        super().__init__(app)

        # SecureHeaders
        if secure_headers:
            self.secure_headers = secure_headers
        else:
            # Sử dụng singleton SecureHeaders từ module security thay vì tạo mới
            self.secure_headers = get_secure_headers()

            # Nếu có thêm cấu hình đặc biệt, có thể cập nhật
            if csp_report_uri:
                self.secure_headers.csp_report_uri = csp_report_uri

        logger.info(f"Khởi tạo SecurityMiddleware với SecureHeaders")

    async def dispatch(self, request: Request, call_next):
        """
        Xử lý request và thêm headers bảo mật.

        Args:
            request: Request object
            call_next: Hàm xử lý tiếp theo

        Returns:
            Response
        """
        # Xử lý request
        response = await call_next(request)

        # Thêm security headers
        response = self.secure_headers(headers=response.headers, path=request.url.path)

        return response
