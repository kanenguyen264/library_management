from typing import Dict, List, Any, Optional, Union, Set, Tuple
import time
import logging
import jwt
from datetime import datetime, timedelta

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.core.db import Base
from app.logs_manager.services import AuthenticationLogService
from app.logs_manager.schemas.authentication_log import AuthenticationLogCreate
from app.security.audit import log_auth_success, log_auth_failure, log_access_attempt

settings = get_settings()
logger = get_logger(__name__)


async def log_auth_failure_db(
    request: Request, user_id: Optional[str], reason: str, user_agent: str
) -> None:
    """
    Log authentication failure to database

    Args:
        request: Request object
        user_id: User ID (if known)
        reason: Reason for failure
        user_agent: User agent string
    """
    try:
        # Create the authentication log service
        auth_log_service = AuthenticationLogService()

        # Ghi log vào database
        for db in Base():
            try:
                # Sử dụng AuthenticationLogService
                result = await auth_log_service.log_authentication(
                    db,
                    event_type="authentication_failure",
                    status="failed",
                    is_success=False,
                    user_id=int(user_id) if user_id else None,
                    ip_address=request.client.host if request.client else None,
                    user_agent=user_agent,
                    details={
                        "reason": reason,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
                if result:
                    break  # Thoát khỏi vòng lặp nếu thành công
            except Exception as e:
                logger.error(f"Error creating authentication log in DB: {str(e)}")
                # Tiếp tục với session tiếp theo nếu có

        # Ghi log security audit
        ip_address = request.client.host if request.client else None
        log_auth_failure(
            username=user_id or "unknown",
            ip_address=ip_address or "unknown",
            reason=reason,
            user_agent=user_agent,
            details={
                "path": request.url.path,
                "method": request.method,
            },
        )
    except Exception as e:
        logger.error(f"Error logging authentication failure: {str(e)}")


async def log_auth_success_db(request: Request, user_id: str, user_agent: str) -> None:
    """
    Log successful authentication to database

    Args:
        request: Request object
        user_id: User ID
        user_agent: User agent string
    """
    try:
        # Create the authentication log service
        auth_log_service = AuthenticationLogService()

        # Ghi log vào database
        for db in Base():
            try:
                # Sử dụng AuthenticationLogService
                result = await auth_log_service.log_authentication(
                    db,
                    event_type="authentication_success",
                    status="success",
                    is_success=True,
                    user_id=int(user_id),
                    ip_address=request.client.host if request.client else None,
                    user_agent=user_agent,
                    details={"path": request.url.path, "method": request.method},
                )
                if result:
                    break  # Thoát khỏi vòng lặp nếu thành công
            except Exception as e:
                logger.error(f"Error creating authentication log in DB: {str(e)}")
                # Tiếp tục với session tiếp theo nếu có

        # Ghi log security audit
        ip_address = request.client.host if request.client else None
        log_auth_success(
            user_id=user_id,
            user_type="user",  # Hoặc "admin" tùy thuộc vào đường dẫn
            ip_address=ip_address or "unknown",
            user_agent=user_agent,
            details={
                "path": request.url.path,
                "method": request.method,
            },
        )
    except Exception as e:
        logger.error(f"Error logging authentication success: {str(e)}")


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware xác thực JWT cho API.
    """

    def __init__(
        self,
        app,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        auth_header_name: str = "Authorization",
        auth_header_prefix: str = "Bearer",
        auth_url_param: Optional[str] = None,
        public_paths: Optional[List[str]] = None,
        admin_paths: Optional[List[str]] = None,
        admin_roles: Optional[List[str]] = None,
    ):
        """
        Khởi tạo middleware.

        Args:
            app: ASGI app
            secret_key: JWT secret key
            algorithm: JWT algorithm
            auth_header_name: Tên header xác thực
            auth_header_prefix: Tiền tố header xác thực
            auth_url_param: Tên tham số URL chứa token
            public_paths: Đường dẫn public
            admin_paths: Đường dẫn admin
            admin_roles: Danh sách vai trò admin
        """
        super().__init__(app)

        # Cấu hình xác thực
        self.secret_key = secret_key or settings.JWT_SECRET_KEY
        self.algorithm = algorithm
        self.auth_header_name = auth_header_name
        self.auth_header_prefix = auth_header_prefix
        self.auth_url_param = auth_url_param

        # Đường dẫn
        self.public_paths = public_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/metrics",
            "/health",
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/reset-password",
            "/static",
        ]

        self.admin_paths = admin_paths or ["/api/v1/admin/"]

        self.admin_roles = admin_roles or ["admin", "superadmin"]

        logger.info(
            f"Khởi tạo AuthMiddleware, public_paths={len(self.public_paths)}, admin_paths={len(self.admin_paths)}"
        )

    async def dispatch(self, request: Request, call_next):
        """
        Xử lý request và xác thực.

        Args:
            request: Request object
            call_next: Hàm xử lý tiếp theo

        Returns:
            Response
        """
        # Kiểm tra đường dẫn public
        path = request.url.path
        if any(path.startswith(public_path) for public_path in self.public_paths):
            # Public path, không yêu cầu xác thực
            return await call_next(request)

        # Lấy token
        token = self._get_token_from_request(request)

        if not token:
            # Không có token
            logger.warning(f"Không có token xác thực cho request: {path}")

            # Log auth failure
            await log_auth_failure_db(
                request, None, "missing_token", request.headers.get("user-agent", "")
            )

            return JSONResponse(
                status_code=HTTP_401_UNAUTHORIZED,
                content={"detail": "Không tìm thấy token xác thực"},
            )

        try:
            # Giải mã token
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Kiểm tra expiration
            exp = payload.get("exp", 0)
            if exp < time.time():
                # Token đã hết hạn
                logger.warning(f"Token xác thực đã hết hạn: {path}")

                # Log auth failure
                await log_auth_failure_db(
                    request,
                    payload.get("sub"),
                    "expired_token",
                    request.headers.get("user-agent", ""),
                )

                return JSONResponse(
                    status_code=HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token xác thực đã hết hạn"},
                )

            # Kiểm tra admin paths
            is_admin_path = any(
                path.startswith(admin_path) for admin_path in self.admin_paths
            )

            # Xác định user_type dựa trên đường dẫn
            user_type = "admin" if is_admin_path else "user"

            if is_admin_path:
                # Kiểm tra quyền admin
                user_roles = payload.get("roles", [])

                if not any(role in self.admin_roles for role in user_roles):
                    # Không có quyền admin
                    logger.warning(
                        f"Không có quyền admin cho: {path}, roles={user_roles}"
                    )

                    # Log auth failure và access attempt
                    await log_auth_failure_db(
                        request,
                        payload.get("sub"),
                        "insufficient_permissions",
                        request.headers.get("user-agent", ""),
                    )

                    # Log access attempt
                    client_ip = self._get_client_ip(request)
                    user_id = payload.get("sub")
                    log_access_attempt(
                        resource_type="admin_api",
                        resource_id=path,
                        user_id=user_id,
                        user_type=user_type,
                        action="access",
                        status="failure",
                        ip_address=client_ip,
                        reason="insufficient_permissions",
                        user_agent=request.headers.get("user-agent", ""),
                    )

                    return JSONResponse(
                        status_code=HTTP_403_FORBIDDEN,
                        content={"detail": "Không có quyền truy cập tài nguyên này"},
                    )

            # Thêm thông tin người dùng vào request
            request.state.user = payload
            request.state.user_id = (
                int(payload.get("sub")) if payload.get("sub") else None
            )
            request.state.user_type = user_type
            request.state.token = token

            # Log successful authentication
            await log_auth_success_db(
                request, payload.get("sub"), request.headers.get("user-agent", "")
            )

            # Log access attempt thành công
            client_ip = self._get_client_ip(request)
            user_id = payload.get("sub")
            log_access_attempt(
                resource_type="api",
                resource_id=path,
                user_id=user_id,
                user_type=user_type,
                action="access",
                status="success",
                ip_address=client_ip,
                user_agent=request.headers.get("user-agent", ""),
            )

            # Tiếp tục xử lý
            response = await call_next(request)
            return response

        except jwt.DecodeError:
            # Token không hợp lệ
            logger.warning(f"Token xác thực không hợp lệ: {path}")

            # Log auth failure
            await log_auth_failure_db(
                request, None, "invalid_token", request.headers.get("user-agent", "")
            )

            return JSONResponse(
                status_code=HTTP_401_UNAUTHORIZED,
                content={"detail": "Token xác thực không hợp lệ"},
            )

        except Exception as e:
            # Lỗi khác
            logger.error(f"Lỗi khi xác thực token: {str(e)}")

            # Log auth failure
            await log_auth_failure_db(
                request,
                None,
                "authentication_error",
                request.headers.get("user-agent", ""),
            )

            return JSONResponse(
                status_code=HTTP_401_UNAUTHORIZED,
                content={"detail": "Lỗi xác thực"},
            )

    def _get_token_from_request(self, request: Request) -> Optional[str]:
        """
        Lấy token từ request.

        Args:
            request: Request object

        Returns:
            Token hoặc None
        """
        # Lấy từ header
        auth_header = request.headers.get(self.auth_header_name)
        if auth_header:
            # Kiểm tra prefix
            parts = auth_header.split()
            if parts[0].lower() == self.auth_header_prefix.lower() and len(parts) == 2:
                return parts[1]

        # Lấy từ URL param nếu được cấu hình
        if self.auth_url_param:
            token = request.query_params.get(self.auth_url_param)
            if token:
                return token

        # Lấy từ cookie
        token = request.cookies.get("token")
        if token:
            return token

        return None

    def _get_client_ip(self, request: Request) -> str:
        """
        Lấy IP của client.

        Args:
            request: Request object

        Returns:
            IP address
        """
        # Lấy từ X-Forwarded-For header
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Lấy IP đầu tiên
            return forwarded_for.split(",")[0].strip()

        # Lấy từ client.host
        client_host = request.client.host if request.client else None

        return client_host or "unknown"
