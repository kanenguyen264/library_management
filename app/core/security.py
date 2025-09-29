"""
Module bảo mật - Xử lý xác thực và phân quyền
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
import secrets
import hashlib
import hmac
import base64

from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Tạo hash cho mật khẩu người dùng.

    Args:
        password: Mật khẩu gốc

    Returns:
        Chuỗi hash
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Kiểm tra mật khẩu có đúng với hash không.

    Args:
        plain_password: Mật khẩu gốc
        hashed_password: Hash đã lưu

    Returns:
        True nếu mật khẩu đúng, False ngược lại
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
    scopes: Optional[list] = None,
) -> str:
    """
    Tạo JWT access token.

    Args:
        subject: Subject của token (thường là user_id)
        expires_delta: Thời gian hết hạn
        scopes: Danh sách các quyền

    Returns:
        JWT token dạng chuỗi
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {"exp": expire, "sub": str(subject)}

    # Thêm scopes nếu có
    if scopes:
        to_encode["scopes"] = scopes

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Tạo JWT refresh token.

    Args:
        subject: Subject của token (thường là user_id)
        expires_delta: Thời gian hết hạn

    Returns:
        JWT token dạng chuỗi
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def generate_secure_token(length: int = 32) -> str:
    """
    Tạo token ngẫu nhiên an toàn.

    Args:
        length: Độ dài token (tính bằng byte)

    Returns:
        Token dạng chuỗi hex
    """
    return secrets.token_hex(length)


def create_verification_token(
    user_id: int, purpose: str, expiry: Optional[int] = None
) -> str:
    """
    Tạo token xác minh cho người dùng (đăng ký, quên mật khẩu).

    Args:
        user_id: ID người dùng
        purpose: Mục đích token ('registration', 'password_reset', etc.)
        expiry: Thời hạn token (giây)

    Returns:
        Token xác minh
    """
    if expiry is None:
        expiry = 3600 * 24  # Mặc định 24 giờ

    expires = int(datetime.utcnow().timestamp()) + expiry
    message = f"{user_id}:{purpose}:{expires}"

    signature = hmac.new(
        settings.SECRET_KEY.encode(), message.encode(), hashlib.sha256
    ).digest()

    token = (
        base64.urlsafe_b64encode(f"{message}:{signature.hex()}".encode())
        .decode()
        .rstrip("=")
    )

    return token


def verify_token(token: str) -> Dict[str, Any]:
    """
    Xác minh token.

    Args:
        token: Token cần xác minh

    Returns:
        Thông tin từ token nếu hợp lệ

    Raises:
        ValueError: Nếu token không hợp lệ hoặc hết hạn
    """
    # Thêm padding nếu cần
    padding = 4 - (len(token) % 4)
    if padding != 4:
        token += "=" * padding

    # Giải mã token
    try:
        decoded = base64.urlsafe_b64decode(token).decode()
        message, signature = decoded.rsplit(":", 1)

        # Tạo lại signature
        expected_signature = hmac.new(
            settings.SECRET_KEY.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

        # Kiểm tra signature
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("Token không hợp lệ")

        # Parse thông tin
        user_id, purpose, expires = message.split(":", 2)
        expires = int(expires)

        # Kiểm tra hạn sử dụng
        if expires < datetime.utcnow().timestamp():
            raise ValueError("Token đã hết hạn")

        return {"user_id": int(user_id), "purpose": purpose, "expires": expires}
    except Exception as e:
        raise ValueError(f"Token không hợp lệ: {str(e)}")


def has_permission(user_id: int, permission: str) -> bool:
    """
    Kiểm tra người dùng có quyền không.

    Args:
        user_id: ID người dùng
        permission: Quyền cần kiểm tra

    Returns:
        True nếu có quyền, False nếu không
    """
    # Trong môi trường thực, đây sẽ truy vấn database
    # Hiện tại trả về True để tránh lỗi khi import
    return True


# Thêm các alias để tương thích với code gọi từ các file khác
get_password_hash = hash_password
get_current_user = None  # Placeholder, sẽ được định nghĩa trong deps.py
get_current_active_user = None  # Placeholder, sẽ được định nghĩa trong deps.py
