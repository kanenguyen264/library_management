import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple
from passlib.context import CryptContext

# Cấu hình bcrypt với các tham số bảo mật cao
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # Số round cao hơn = bảo mật hơn nhưng chậm hơn
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Xác minh mật khẩu khớp với hash.

    Args:
        plain_password: Mật khẩu dạng plain text
        hashed_password: Mật khẩu đã được hash

    Returns:
        True nếu mật khẩu khớp, False nếu không
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash mật khẩu bằng bcrypt.

    Args:
        password: Mật khẩu cần hash

    Returns:
        Mật khẩu đã được hash
    """
    return pwd_context.hash(password)


def generate_password_reset_token(
    user_id: int, expires_delta: Optional[timedelta] = None
) -> Tuple[str, datetime]:
    """
    Tạo token đặt lại mật khẩu an toàn.

    Args:
        user_id: ID của người dùng
        expires_delta: Thời gian hết hạn của token

    Returns:
        Tuple chứa token và thời gian hết hạn
    """
    # Tạo token ngẫu nhiên an toàn có độ dài 32 ký tự
    token = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(32)
    )

    # Thiết lập thời gian hết hạn (mặc định 24 giờ)
    if not expires_delta:
        expires_delta = timedelta(hours=24)

    expire_time = datetime.utcnow() + expires_delta

    return token, expire_time


def check_password_strength(password: str) -> Tuple[bool, str]:
    """
    Kiểm tra độ mạnh của mật khẩu.

    Args:
        password: Mật khẩu cần kiểm tra

    Returns:
        Tuple (hợp lệ, lý do)
    """
    if len(password) < 8:
        return False, "Mật khẩu phải có ít nhất 8 ký tự"

    if not any(c.isupper() for c in password):
        return False, "Mật khẩu phải chứa ít nhất một chữ cái viết hoa"

    if not any(c.islower() for c in password):
        return False, "Mật khẩu phải chứa ít nhất một chữ cái viết thường"

    if not any(c.isdigit() for c in password):
        return False, "Mật khẩu phải chứa ít nhất một chữ số"

    special_chars = set("!@#$%^&*()_-+={}[]\\|:;\"'<>,.?/~`")
    if not any(c in special_chars for c in password):
        return False, "Mật khẩu phải chứa ít nhất một ký tự đặc biệt"

    return True, "Mật khẩu hợp lệ"
