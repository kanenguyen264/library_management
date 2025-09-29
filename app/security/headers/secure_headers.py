from typing import Dict, List, Optional, Union
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send
from app.core.config import get_settings

settings = get_settings()

class SecureHeaders:
    """
    Middleware để thêm các HTTP security headers vào responses.
    Bao gồm các header được khuyến nghị bởi OWASP.
    """
    
    def __init__(
        self,
        csp_policy: Optional[str] = None,
        hsts_max_age: int = 31536000,  # 1 year
        frame_options: str = "DENY",
        content_type_options: str = "nosniff",
        xss_protection: str = "1; mode=block",
        referrer_policy: str = "strict-origin-when-cross-origin",
        permissions_policy: Optional[str] = None,
        cache_control: Optional[str] = None,
        include_powered_by: bool = False,
        server_name: Optional[str] = None,
        report_to: Optional[str] = None,
        report_uri: Optional[str] = None,
        clear_site_data_on_auth_paths: bool = True
    ):
        """
        Khởi tạo middleware.
        
        Args:
            csp_policy: Content-Security-Policy header value
            hsts_max_age: Strict-Transport-Security max-age in seconds
            frame_options: X-Frame-Options header value
            content_type_options: X-Content-Type-Options header value
            xss_protection: X-XSS-Protection header value
            referrer_policy: Referrer-Policy header value
            permissions_policy: Permissions-Policy header value
            cache_control: Cache-Control header value
            include_powered_by: Whether to include X-Powered-By header
            server_name: Server header value
            report_to: Report-To header value
            report_uri: Content-Security-Policy-Report-Only header value
            clear_site_data_on_auth_paths: Whether to send Clear-Site-Data on auth paths
        """
        self.csp_policy = csp_policy or settings.CSP_POLICY
        self.hsts_max_age = hsts_max_age
        self.frame_options = frame_options
        self.content_type_options = content_type_options
        self.xss_protection = xss_protection
        self.referrer_policy = referrer_policy
        
        self.permissions_policy = permissions_policy
        if not self.permissions_policy:
            self.permissions_policy = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
            
        self.cache_control = cache_control
        self.include_powered_by = include_powered_by
        self.server_name = server_name
        self.report_to = report_to
        self.report_uri = report_uri
        self.clear_site_data_on_auth_paths = clear_site_data_on_auth_paths
        
    def __call__(self, headers: Union[Headers, MutableHeaders], path: str = "") -> MutableHeaders:
        """
        Thêm security headers vào response headers.
        
        Args:
            headers: Response headers
            path: Request path
            
        Returns:
            Headers with security headers added
        """
        # Chuyển đổi sang MutableHeaders nếu cần
        if isinstance(headers, Headers):
            headers = MutableHeaders(headers=headers)
            
        # Thêm các security headers
        if self.csp_policy:
            headers["Content-Security-Policy"] = self.csp_policy
            
        headers["Strict-Transport-Security"] = f"max-age={self.hsts_max_age}; includeSubDomains"
        headers["X-Frame-Options"] = self.frame_options
        headers["X-Content-Type-Options"] = self.content_type_options
        headers["X-XSS-Protection"] = self.xss_protection
        headers["Referrer-Policy"] = self.referrer_policy
        
        if self.permissions_policy:
            headers["Permissions-Policy"] = self.permissions_policy
            
        # Cache control
        if self.cache_control:
            headers["Cache-Control"] = self.cache_control
        
        # Server identity headers (thường bỏ đi trong production)
        if self.include_powered_by:
            headers["X-Powered-By"] = "LibiStory API"
        else:
            headers.pop("X-Powered-By", None)
        
        if self.server_name:
            headers["Server"] = self.server_name
        else:
            headers.pop("Server", None)
            
        # Reporting headers
        if self.report_to:
            headers["Report-To"] = self.report_to
            
        if self.report_uri:
            headers["Content-Security-Policy-Report-Only"] = self.report_uri
            
        # Clear site data on logout, login
        if self.clear_site_data_on_auth_paths and any(auth_path in path for auth_path in ["/logout", "/login"]):
            headers["Clear-Site-Data"] = '"cookies", "storage"'
            
        return headers

class SecureHeadersMiddleware:
    """
    ASGI middleware để tự động thêm security headers vào tất cả responses.
    """
    
    def __init__(self, app: ASGIApp, secure_headers: Optional[SecureHeaders] = None):
        """
        Khởi tạo middleware.
        
        Args:
            app: ASGI application
            secure_headers: SecureHeaders instance
        """
        self.app = app
        self.secure_headers = secure_headers or SecureHeaders()
        
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI entry point.
        
        Args:
            scope: ASGI scope
            receive: ASGI receive function
            send: ASGI send function
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
            
        path = scope.get("path", "")
            
        async def send_with_secure_headers(message):
            """
            Intercept and modify response headers.
            
            Args:
                message: ASGI message
            """
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                self.secure_headers(headers, path)
                message["headers"] = headers.raw
                
            await send(message)
            
        await self.app(scope, receive, send_with_secure_headers)
