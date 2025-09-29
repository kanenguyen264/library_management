import re
import ipaddress
from typing import Any, Dict, List, Optional, Union, Tuple
from pydantic import validator, BaseModel, EmailStr, SecretStr, ValidationError
from datetime import datetime
from app.security.waf.rules import (
    detect_sql_injection,
    detect_xss,
    detect_path_traversal,
)
from app.core.config import get_settings

settings = get_settings()


class ValidationResult:
    """Kết quả của quá trình validation."""

    def __init__(self, is_valid: bool, errors: Optional[List[str]] = None):
        """
        Khởi tạo ValidationResult.

        Args:
            is_valid: Whether the validation passed
            errors: List of validation errors
        """
        self.is_valid = is_valid
        self.errors = errors or []

    def __bool__(self):
        """Convert to boolean."""
        return self.is_valid

    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)
        self.is_valid = False

    def merge(self, other: "ValidationResult"):
        """Merge with another ValidationResult."""
        if not other.is_valid:
            self.is_valid = False
            self.errors.extend(other.errors)


def validate_email(email: str) -> ValidationResult:
    """
    Kiểm tra email hợp lệ với các quy tắc nghiêm ngặt.

    Args:
        email: Email address to validate

    Returns:
        ValidationResult
    """
    result = ValidationResult(True)

    # Basic format validation
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_pattern, email):
        result.add_error("Email không đúng định dạng")
        return result

    # Check for common temporary email domains
    temp_domains = [
        "10minutemail.com",
        "tempmail.com",
        "throwawaymail.com",
        "mailinator.com",
        "guerrillamail.com",
        "yopmail.com",
    ]

    domain = email.split("@")[-1]
    if domain in temp_domains:
        result.add_error("Không chấp nhận email tạm thời")

    # Additional security checks
    if len(email) > 254:
        result.add_error("Email quá dài")

    if detect_xss(email) or detect_sql_injection(email):
        result.add_error("Email chứa ký tự không hợp lệ")

    return result


def validate_password(password: str) -> ValidationResult:
    """
    Kiểm tra mật khẩu mạnh theo các tiêu chí bảo mật.

    Args:
        password: Password to validate

    Returns:
        ValidationResult
    """
    result = ValidationResult(True)

    # Length check
    min_length = settings.PASSWORD_MIN_LENGTH
    if len(password) < min_length:
        result.add_error(f"Mật khẩu phải có ít nhất {min_length} ký tự")

    # Complexity checks
    if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
        result.add_error("Mật khẩu phải chứa ít nhất một chữ cái viết hoa")

    if settings.PASSWORD_REQUIRE_DIGITS and not any(c.isdigit() for c in password):
        result.add_error("Mật khẩu phải chứa ít nhất một chữ số")

    if settings.PASSWORD_REQUIRE_SPECIAL and not any(
        c in "!@#$%^&*()_-+={}[]\\|:;\"'<>,.?/~`" for c in password
    ):
        result.add_error("Mật khẩu phải chứa ít nhất một ký tự đặc biệt")

    # Check for common patterns
    common_patterns = [
        r"12345",
        r"qwerty",
        r"password",
        r"admin",
        r"welcome",
        r"letmein",
        r"abc123",
        r"111111",
        r"654321",
    ]

    for pattern in common_patterns:
        if re.search(pattern, password, re.IGNORECASE):
            result.add_error("Mật khẩu chứa chuỗi phổ biến dễ đoán")
            break

    return result


def validate_username(username: str) -> ValidationResult:
    """
    Kiểm tra tên người dùng hợp lệ và an toàn.

    Args:
        username: Username to validate

    Returns:
        ValidationResult
    """
    result = ValidationResult(True)

    # Length check
    if len(username) < 3:
        result.add_error("Tên người dùng phải có ít nhất 3 ký tự")

    if len(username) > 50:
        result.add_error("Tên người dùng không được vượt quá 50 ký tự")

    # Character check
    if not re.match(r"^[a-zA-Z0-9_.-]+$", username):
        result.add_error(
            "Tên người dùng chỉ được chứa chữ cái, số, gạch dưới, dấu chấm và gạch ngang"
        )

    # Security checks
    if detect_xss(username) or detect_sql_injection(username):
        result.add_error("Tên người dùng chứa ký tự không hợp lệ")

    return result


def validate_url(url: str) -> ValidationResult:
    """
    Kiểm tra URL hợp lệ và an toàn.

    Args:
        url: URL to validate

    Returns:
        ValidationResult
    """
    result = ValidationResult(True)

    # Basic URL format
    url_pattern = r"^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$"
    if not re.match(url_pattern, url):
        result.add_error("URL không đúng định dạng")
        return result

    # Security checks
    if detect_xss(url) or detect_sql_injection(url):
        result.add_error("URL chứa ký tự không hợp lệ")

    # Check for open redirect attempts
    redirect_patterns = [
        r"\/\/([^\/]+\.)*example\.com",  # Replace with actual domains
        r"@",
        r"\\",
        r"%2f",
        r"%5c",
        r"javascript:",
    ]

    for pattern in redirect_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            result.add_error("URL có thể chứa mã độc")
            break

    return result


def validate_ip_address(ip: str) -> ValidationResult:
    """
    Kiểm tra địa chỉ IP hợp lệ.

    Args:
        ip: IP address to validate

    Returns:
        ValidationResult
    """
    result = ValidationResult(True)

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        result.add_error("Địa chỉ IP không hợp lệ")

    return result


def validate_file_extension(
    filename: str, allowed_extensions: List[str]
) -> ValidationResult:
    """
    Kiểm tra phần mở rộng của file.

    Args:
        filename: Filename to validate
        allowed_extensions: List of allowed extensions

    Returns:
        ValidationResult
    """
    result = ValidationResult(True)

    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        result.add_error(
            f"Phần mở rộng file không được chấp nhận. Cho phép: {', '.join(allowed_extensions)}"
        )

    return result


def validate_date_format(
    date_str: str, format_str: str = "%Y-%m-%d"
) -> ValidationResult:
    """
    Kiểm tra định dạng ngày tháng.

    Args:
        date_str: Date string to validate
        format_str: Expected date format

    Returns:
        ValidationResult
    """
    result = ValidationResult(True)

    try:
        datetime.strptime(date_str, format_str)
    except ValueError:
        result.add_error(
            f"Ngày tháng không đúng định dạng. Định dạng yêu cầu: {format_str}"
        )

    return result


def validate_request_data(
    data: Dict[str, Any], required_fields: List[str]
) -> ValidationResult:
    """
    Kiểm tra dữ liệu request có đầy đủ và hợp lệ không.

    Args:
        data: Request data
        required_fields: List of required fields

    Returns:
        ValidationResult
    """
    result = ValidationResult(True)

    # Check required fields
    for field in required_fields:
        if field not in data or data[field] is None:
            result.add_error(f"Thiếu trường bắt buộc: {field}")

    # Check for injection attempts in all string values
    for key, value in data.items():
        if isinstance(value, str):
            if detect_sql_injection(value):
                result.add_error(f"Phát hiện SQL injection trong trường: {key}")

            if detect_xss(value):
                result.add_error(f"Phát hiện XSS trong trường: {key}")

            if detect_path_traversal(value):
                result.add_error(f"Phát hiện path traversal trong trường: {key}")

    return result


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Kiểm tra độ mạnh của mật khẩu và trả về kết quả kèm lý do.

    Args:
        password: Mật khẩu cần kiểm tra

    Returns:
        tuple[bool, str]: (True, "") nếu mật khẩu đủ mạnh, (False, lý do) nếu không đạt yêu cầu
    """
    # Kiểm tra độ dài tối thiểu
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"Mật khẩu phải có ít nhất {settings.PASSWORD_MIN_LENGTH} ký tự"

    # Kiểm tra chữ hoa
    if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
        return False, "Mật khẩu phải chứa ít nhất một chữ cái viết hoa"

    # Kiểm tra chữ số
    if settings.PASSWORD_REQUIRE_DIGITS and not any(c.isdigit() for c in password):
        return False, "Mật khẩu phải chứa ít nhất một chữ số"

    # Kiểm tra ký tự đặc biệt
    if settings.PASSWORD_REQUIRE_SPECIAL and not any(
        c in "!@#$%^&*()_-+={}[]\\|:;\"'<>,.?/~`" for c in password
    ):
        return False, "Mật khẩu phải chứa ít nhất một ký tự đặc biệt"

    # Kiểm tra mẫu phổ biến
    common_patterns = [
        r"12345",
        r"qwerty",
        r"password",
        r"admin",
        r"welcome",
        r"letmein",
        r"abc123",
        r"111111",
        r"654321",
    ]

    for pattern in common_patterns:
        if re.search(pattern, password, re.IGNORECASE):
            return False, f"Mật khẩu không được chứa chuỗi dễ đoán ('{pattern}')"

    return True, ""


class ValidationMixin:
    """Mixin for Pydantic models to add custom validation methods."""

    @validator("email", check_fields=False)
    def validate_email_field(cls, v):
        """Validate email field."""
        result = validate_email(v)
        if not result:
            raise ValueError(result.errors[0])
        return v

    @validator("password", check_fields=False)
    def validate_password_field(cls, v):
        """Validate password field."""
        result = validate_password(v)
        if not result:
            raise ValueError(result.errors[0])
        return v

    @validator("username", check_fields=False)
    def validate_username_field(cls, v):
        """Validate username field."""
        result = validate_username(v)
        if not result:
            raise ValueError(result.errors[0])
        return v
