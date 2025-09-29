from typing import List, Dict, Any, Optional
import logging

from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)


def create_cors_middleware(
    allow_origins: Optional[List[str]] = None,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
    allow_credentials: bool = True,
    allow_origin_regex: Optional[str] = None,
    expose_headers: Optional[List[str]] = None,
    max_age: int = 600,
):
    """
    Tạo CORS middleware.

    Args:
        allow_origins: Danh sách origins được phép
        allow_methods: Danh sách methods được phép
        allow_headers: Danh sách headers được phép
        allow_credentials: Cho phép credentials
        allow_origin_regex: Regex cho origins được phép
        expose_headers: Danh sách headers được phơi ra
        max_age: Thời gian cache preflight

    Returns:
        CORS middleware
    """
    # Sử dụng giá trị mặc định từ settings nếu không có tham số
    _allow_origins = allow_origins or settings.CORS_ALLOW_ORIGINS
    _allow_methods = allow_methods or settings.CORS_ALLOW_METHODS
    _allow_headers = allow_headers or settings.CORS_ALLOW_HEADERS
    _allow_credentials = (
        allow_credentials
        if allow_credentials is not None
        else settings.CORS_ALLOW_CREDENTIALS
    )
    _allow_origin_regex = allow_origin_regex or settings.CORS_ALLOW_ORIGIN_REGEX
    _expose_headers = expose_headers or settings.CORS_EXPOSE_HEADERS
    _max_age = max_age or settings.CORS_MAX_AGE

    logger.info(
        f"Tạo CORS middleware với allow_origins={_allow_origins}, "
        f"allow_methods={_allow_methods}, allow_credentials={_allow_credentials}"
    )

    # Trả về CORS middleware
    return CORSMiddleware(
        app=None,  # Sẽ được thiết lập khi add vào app
        allow_origins=_allow_origins,
        allow_methods=_allow_methods,
        allow_headers=_allow_headers,
        allow_credentials=_allow_credentials,
        allow_origin_regex=_allow_origin_regex,
        expose_headers=_expose_headers,
        max_age=_max_age,
    )


class CORSHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware thêm CORS headers cho API responses.
    Cho phép kiểm soát chi tiết hơn so với CORSMiddleware mặc định.
    """

    def __init__(
        self,
        app,
        allow_origins: Optional[List[str]] = None,
        allow_methods: Optional[List[str]] = None,
        allow_headers: Optional[List[str]] = None,
        allow_credentials: bool = True,
        expose_headers: Optional[List[str]] = None,
        max_age: int = 600,
        vary_header: bool = True,
    ):
        """
        Khởi tạo middleware.

        Args:
            app: ASGI app
            allow_origins: Danh sách origins được phép
            allow_methods: Danh sách methods được phép
            allow_headers: Danh sách headers được phép
            allow_credentials: Cho phép credentials
            expose_headers: Danh sách headers được phơi ra
            max_age: Thời gian cache preflight
            vary_header: Thêm header Vary: Origin
        """
        super().__init__(app)

        # Sử dụng giá trị mặc định từ settings nếu không có tham số
        self.allow_origins = allow_origins or settings.CORS_ALLOW_ORIGINS
        self.allow_methods = allow_methods or settings.CORS_ALLOW_METHODS
        self.allow_headers = allow_headers or settings.CORS_ALLOW_HEADERS
        self.allow_credentials = (
            allow_credentials
            if allow_credentials is not None
            else settings.CORS_ALLOW_CREDENTIALS
        )
        self.expose_headers = expose_headers or settings.CORS_EXPOSE_HEADERS
        self.max_age = max_age or settings.CORS_MAX_AGE
        self.vary_header = vary_header

        # Chuẩn bị header values
        self.allow_methods_value = ", ".join(self.allow_methods)
        self.allow_headers_value = ", ".join(self.allow_headers)
        self.expose_headers_value = (
            ", ".join(self.expose_headers) if self.expose_headers else ""
        )

        logger.info(
            f"Khởi tạo CORSHeadersMiddleware với allow_origins={len(self.allow_origins)}"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Xử lý request và thêm CORS headers.

        Args:
            request: Request object
            call_next: Hàm xử lý tiếp theo

        Returns:
            Response
        """
        # Lấy origin của request
        origin = request.headers.get("origin")

        # Xử lý preflight request (OPTIONS)
        if request.method == "OPTIONS":
            if origin and self._is_origin_allowed(origin):
                # Tạo preflight response
                response = Response(content="", status_code=200)

                # Thêm CORS headers
                self._add_cors_headers(response, origin)

                # Thêm headers đặc biệt cho preflight
                response.headers["Access-Control-Allow-Methods"] = (
                    self.allow_methods_value
                )
                response.headers["Access-Control-Allow-Headers"] = (
                    self.allow_headers_value
                )
                response.headers["Access-Control-Max-Age"] = str(self.max_age)

                return response

        # Xử lý request bình thường
        response = await call_next(request)

        # Thêm CORS headers cho response nếu có origin
        if origin and self._is_origin_allowed(origin):
            self._add_cors_headers(response, origin)

        return response

    def _is_origin_allowed(self, origin: str) -> bool:
        """
        Kiểm tra xem origin có được phép không.

        Args:
            origin: Origin từ request

        Returns:
            True nếu origin được phép
        """
        if "*" in self.allow_origins:
            return True

        return origin in self.allow_origins

    def _add_cors_headers(self, response: Response, origin: str) -> None:
        """
        Thêm CORS headers vào response.

        Args:
            response: Response object
            origin: Origin từ request
        """
        # Thêm header Access-Control-Allow-Origin
        if "*" in self.allow_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        else:
            response.headers["Access-Control-Allow-Origin"] = origin

        # Thêm các headers khác
        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        if self.expose_headers:
            response.headers["Access-Control-Expose-Headers"] = (
                self.expose_headers_value
            )

        # Thêm Vary header
        if self.vary_header:
            response.headers["Vary"] = "Origin"
