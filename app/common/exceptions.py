"""
Common exceptions.

Module cung cấp các exception chung được sử dụng trong nhiều modules.
Thường được import như `from app.common.exceptions import SomeException`.
"""

from typing import Dict, List, Optional, Any, Union
from fastapi import status


class BaseAppException(Exception):
    """Base exception class cho tất cả ứng dụng."""

    def __init__(self, message: str = "Có lỗi xảy ra", code: str = "app_error"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ValidationError(BaseAppException):
    """Exception cho các lỗi liên quan đến validation."""

    def __init__(
        self,
        message: str = "Dữ liệu không hợp lệ",
        code: str = "validation_error",
        errors: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(message, code)
        self.errors = errors or []


class BadRequestException(BaseAppException):
    """Exception cho các lỗi yêu cầu không hợp lệ."""

    def __init__(
        self,
        message: str = "Yêu cầu không hợp lệ",
        code: str = "bad_request",
        field: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(message, code)
        self.field = field
        self.detail = detail or {}
        self.headers = headers or {}
        self.status_code = status.HTTP_400_BAD_REQUEST


class ResourceError(BaseAppException):
    """Exception cho các lỗi liên quan đến tài nguyên."""

    def __init__(
        self,
        message: str = "Lỗi tài nguyên",
        code: str = "resource_error",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        super().__init__(message, code)
        self.resource_type = resource_type
        self.resource_id = resource_id


class ResourceNotFound(ResourceError):
    """Exception khi không tìm thấy tài nguyên."""

    def __init__(
        self,
        message: str = "Không tìm thấy tài nguyên",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code="resource_not_found",
            resource_type=resource_type,
            resource_id=resource_id,
        )


class ResourceAlreadyExists(ResourceError):
    """Exception khi tài nguyên đã tồn tại."""

    def __init__(
        self,
        message: str = "Tài nguyên đã tồn tại",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code="resource_already_exists",
            resource_type=resource_type,
            resource_id=resource_id,
        )


class ResourceConflictException(ResourceError):
    """Exception khi có xung đột giữa các tài nguyên."""

    def __init__(
        self,
        message: str = "Xung đột tài nguyên",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        conflict_details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="resource_conflict",
            resource_type=resource_type,
            resource_id=resource_id,
        )
        self.conflict_details = conflict_details or {}
        self.status_code = status.HTTP_409_CONFLICT


class DatabaseError(BaseAppException):
    """Exception cho các lỗi liên quan đến database."""

    def __init__(
        self,
        message: str = "Lỗi cơ sở dữ liệu",
        code: str = "database_error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code)
        self.details = details or {}


class ConfigurationError(BaseAppException):
    """Exception cho các lỗi cấu hình."""

    def __init__(self, message: str = "Lỗi cấu hình", config_key: Optional[str] = None):
        super().__init__(message, "configuration_error")
        self.config_key = config_key


class AuthenticationError(BaseAppException):
    """Exception cho các lỗi xác thực."""

    def __init__(
        self, message: str = "Lỗi xác thực", code: str = "authentication_error"
    ):
        super().__init__(message, code)


class AuthorizationError(BaseAppException):
    """Exception cho các lỗi phân quyền."""

    def __init__(
        self,
        message: str = "Không có quyền truy cập",
        code: str = "authorization_error",
        required_permission: Optional[str] = None,
    ):
        super().__init__(message, code)
        self.required_permission = required_permission


class ThirdPartyServiceError(BaseAppException):
    """Exception cho các lỗi từ dịch vụ bên thứ ba."""

    def __init__(
        self,
        message: str = "Lỗi dịch vụ bên thứ ba",
        service_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, "third_party_service_error")
        self.service_name = service_name
        self.details = details or {}


# Alias cho tương thích ngược - sử dụng khi code cũ import NotFoundException từ app.common.exceptions
NotFoundException = ResourceNotFound
ResourceNotFoundException = ResourceNotFound
PermissionDeniedException = AuthorizationError
