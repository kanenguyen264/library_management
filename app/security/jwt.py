from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
from pydantic import ValidationError
from app.core.config import get_settings
from app.core.exceptions import InvalidToken, TokenExpired

settings = get_settings()


def create_access_token(
    subject: Union[str, int, Dict[str, Any]],
    expires_delta: Optional[timedelta] = None,
    scopes: Optional[list] = None,
) -> str:
    """
    Tạo JWT access token.

    Args:
        subject: Thông tin để mã hóa (thường là user ID hoặc dict với user data)
        expires_delta: Thời gian tồn tại token, nếu không set sẽ lấy từ cấu hình
        scopes: Danh sách quyền của token

    Returns:
        JWT token đã ký
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {
        "exp": expire,
        "iat": datetime.utcnow(),
        "sub": str(subject) if not isinstance(subject, dict) else None,
    }

    # Nếu subject là dict, merge vào payload
    if isinstance(subject, dict):
        to_encode.update(subject)

    # Thêm scopes nếu có
    if scopes:
        to_encode["scopes"] = scopes

    # Thêm thông tin môi trường (chỉ cho dev để debug)
    if settings.APP_ENV == "development":
        to_encode["env"] = settings.APP_ENV

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(
    subject: Union[str, int], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Tạo JWT refresh token.

    Args:
        subject: User ID
        expires_delta: Thời gian tồn tại token, nếu không set sẽ lấy từ cấu hình

    Returns:
        JWT refresh token đã ký
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {
        "exp": expire,
        "iat": datetime.utcnow(),
        "sub": str(subject),
        "type": "refresh",
    }

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Giải mã JWT token.

    Args:
        token: JWT token cần giải mã

    Returns:
        Payload trong token

    Raises:
        InvalidToken: Khi token không hợp lệ
        TokenExpired: Khi token đã hết hạn
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except ExpiredSignatureError:
        raise TokenExpired()
    except (InvalidTokenError, ValidationError):
        raise InvalidToken()
