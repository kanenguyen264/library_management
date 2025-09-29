from typing import Dict, List, Optional, Any, Union
from fastapi import HTTPException, status
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Model for standardized error responses."""

    detail: str
    code: Optional[str] = None
    field: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class ValidationErrorResponse(BaseModel):
    """Model for validation error responses."""

    detail: str = "Validation error"
    errors: List[ErrorResponse]


class APIException(HTTPException):
    """
    Base exception class cho API errors.
    Mở rộng từ HTTPException để thêm error code, và các thông tin chi tiết thêm.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: Optional[str] = None,
        field: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        """
        Khởi tạo exception.

        Args:
            status_code: HTTP status code
            detail: Error detail message
            code: Error code
            field: Field that caused the error
            params: Additional parameters
            headers: HTTP headers
        """
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
        self.field = field
        self.params = params

    def to_response(self) -> Dict[str, Any]:
        """Convert to response dict."""
        response = {"detail": self.detail}

        if self.code:
            response["code"] = self.code

        if self.field:
            response["field"] = self.field

        if self.params:
            response["params"] = self.params

        return response


class BadRequestException(APIException):
    """400 Bad Request exception."""

    def __init__(
        self,
        detail: str = "Bad request",
        code: Optional[str] = "bad_request",
        field: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code=code,
            field=field,
            params=params,
            headers=headers,
        )


class UnauthorizedException(APIException):
    """401 Unauthorized exception."""

    def __init__(
        self,
        detail: str = "Not authenticated",
        code: Optional[str] = "unauthorized",
        headers: Optional[Dict[str, str]] = None,
    ):
        if headers is None:
            headers = {"WWW-Authenticate": "Bearer"}

        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            code=code,
            headers=headers,
        )


class ForbiddenException(APIException):
    """403 Forbidden exception."""

    def __init__(
        self,
        detail: str = "Permission denied",
        code: Optional[str] = "forbidden",
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            code=code,
            headers=headers,
        )


class NotFoundException(APIException):
    """404 Not Found exception."""

    def __init__(
        self,
        detail: str = "Resource not found",
        code: Optional[str] = "not_found",
        field: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            code=code,
            field=field,
            headers=headers,
        )


class ConflictException(APIException):
    """409 Conflict exception."""

    def __init__(
        self,
        detail: str = "Resource conflict",
        code: Optional[str] = "conflict",
        field: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            code=code,
            field=field,
            headers=headers,
        )


class RateLimitException(APIException):
    """429 Too Many Requests exception."""

    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        code: Optional[str] = "rate_limit",
        retry_after: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        if headers is None:
            headers = {}

        if retry_after:
            headers["Retry-After"] = str(retry_after)

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            code=code,
            headers=headers,
        )


class ServerException(APIException):
    """500 Internal Server Error exception."""

    def __init__(
        self,
        detail: str = "Internal server error",
        code: Optional[str] = "server_error",
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            code=code,
            headers=headers,
        )


class ServiceUnavailableException(APIException):
    """503 Service Unavailable exception."""

    def __init__(
        self,
        detail: str = "Service temporarily unavailable",
        code: Optional[str] = "service_unavailable",
        retry_after: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        if headers is None:
            headers = {}

        if retry_after:
            headers["Retry-After"] = str(retry_after)

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            code=code,
            headers=headers,
        )


class ValidationException(APIException):
    """422 Validation Error exception."""

    def __init__(
        self,
        errors: List[Dict[str, Any]],
        detail: str = "Validation error",
        code: Optional[str] = "validation_error",
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            code=code,
            headers=headers,
        )
        self.errors = errors

    def to_response(self) -> Dict[str, Any]:
        """Convert to response dict."""
        return {"detail": self.detail, "code": self.code, "errors": self.errors}


class ClientException(APIException):
    """400 Client Error exception.

    Exception chung cho các lỗi phía client với status code tùy chỉnh.
    """

    def __init__(
        self,
        detail: str = "Client error",
        code: Optional[str] = "client_error",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        field: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.error_code = code
        self.details = details
        super().__init__(
            status_code=status_code,
            detail=detail,
            code=code,
            field=field,
            params=params,
            headers=headers,
        )


# JWT related exceptions
class TokenException(Exception):
    """Base exception for token errors."""

    pass


class InvalidToken(TokenException):
    """Invalid token exception."""

    pass


class TokenExpired(TokenException):
    """Expired token exception."""

    pass


class AuthenticationException(UnauthorizedException):
    """Authentication exception."""

    def __init__(
        self,
        detail: str = "Authentication failed",
        code: Optional[str] = "authentication_error",
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(detail=detail, code=code, headers=headers)


# Custom exceptions
class DatabaseException(Exception):
    """Database related exception."""

    pass


class CacheException(Exception):
    """Cache related exception."""

    pass


class ExternalServiceException(Exception):
    """External service related exception."""

    pass


class BusinessLogicException(Exception):
    """Business logic related exception."""

    pass


class PaymentException(APIException):
    """Exception liên quan đến thanh toán."""

    def __init__(
        self,
        detail: str = "Payment processing error",
        code: Optional[str] = "payment_error",
        field: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code=code,
            field=field,
            params=params,
            headers=headers,
        )


class InvalidOperationException(APIException):
    """Exception khi thực hiện một thao tác không hợp lệ."""

    def __init__(
        self,
        detail: str = "Thao tác không hợp lệ",
        code: Optional[str] = "invalid_operation",
        field: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code=code,
            field=field,
            params=params,
            headers=headers,
        )


# Thêm class RateLimitExceededException để tương thích với code cũ
class RateLimitExceededException(RateLimitException):
    """429 Too Many Requests exception - Class tương thích với code cũ."""

    def __init__(
        self,
        detail: str = "Vượt quá giới hạn rate limit",
        code: Optional[str] = "rate_limit_exceeded",
        retry_after: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(
            detail=detail, code=code, retry_after=retry_after, headers=headers
        )
