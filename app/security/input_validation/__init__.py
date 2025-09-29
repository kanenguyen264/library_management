"""
Module xác thực đầu vào (Input Validation) - Cung cấp các công cụ xác thực và làm sạch dữ liệu đầu vào.

Module này cung cấp:
- Xác thực các giá trị đầu vào (email, mật khẩu, username, URL, v.v.)
- Làm sạch HTML và ngăn chặn XSS
- Làm sạch các giá trị để ngăn SQL Injection
- Xác thực và làm sạch tên file để ngăn Path Traversal
"""

from app.security.input_validation.validators import (
    ValidationResult,
    validate_email,
    validate_password,
    validate_username,
    validate_url,
    validate_ip_address,
    validate_file_extension,
    validate_date_format,
    validate_request_data,
    ValidationMixin,
)

from app.security.input_validation.sanitizers import (
    sanitize_html,
    sanitize_text,
    sanitize_sql,
    sanitize_filename,
    sanitize_url,
    sanitize_dict,
    sanitize_list,
)

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Cấu hình validation mặc định
VALIDATION_CONFIG = {
    "password_min_length": settings.PASSWORD_MIN_LENGTH,
    "password_require_uppercase": settings.PASSWORD_REQUIRE_UPPERCASE,
    "password_require_numbers": settings.PASSWORD_REQUIRE_DIGITS,
    "password_require_special": settings.PASSWORD_REQUIRE_SPECIAL,
    "username_min_length": 3,
    "username_max_length": 50,
    "email_blocked_domains": ["tempmail.com", "throwawaymail.com", "mailinator.com"],
}

# Định nghĩa các loại file an toàn
SAFE_FILE_TYPES = {
    "image": ["jpg", "jpeg", "png", "gif", "webp", "svg"],
    "document": [
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
        "txt",
        "rtf",
        "odt",
    ],
    "audio": ["mp3", "wav", "ogg", "m4a", "flac"],
    "video": ["mp4", "webm", "avi", "mov", "wmv", "mkv"],
    "archive": ["zip", "rar", "7z", "tar", "gz"],
}


def validate_input(input_type, value):
    """
    Xác thực một giá trị đầu vào dựa trên loại.

    Args:
        input_type: Loại đầu vào ("email", "password", "username", "url", etc.)
        value: Giá trị cần xác thực

    Returns:
        ValidationResult object
    """
    if input_type == "email":
        return validate_email(value)
    elif input_type == "password":
        return validate_password(value)
    elif input_type == "username":
        return validate_username(value)
    elif input_type == "url":
        return validate_url(value)
    elif input_type == "ip":
        return validate_ip_address(value)
    else:
        result = ValidationResult(False)
        result.add_error(f"Unknown validation type: {input_type}")
        return result


def sanitize_input(input_type, value):
    """
    Làm sạch một giá trị đầu vào dựa trên loại.

    Args:
        input_type: Loại đầu vào ("html", "text", "sql", "filename", "url")
        value: Giá trị cần làm sạch

    Returns:
        Giá trị đã được làm sạch
    """
    if input_type == "html":
        return sanitize_html(value)
    elif input_type == "text":
        return sanitize_text(value)
    elif input_type == "sql":
        return sanitize_sql(value)
    elif input_type == "filename":
        return sanitize_filename(value)
    elif input_type == "url":
        return sanitize_url(value)
    elif input_type == "dict":
        return sanitize_dict(value)
    elif input_type == "list":
        return sanitize_list(value)
    else:
        logger.warning(f"Unknown sanitization type: {input_type}")
        return sanitize_text(value)  # Mặc định sanitize text để an toàn


# Export các components
__all__ = [
    "ValidationResult",
    "validate_email",
    "validate_password",
    "validate_username",
    "validate_url",
    "validate_ip_address",
    "validate_file_extension",
    "validate_date_format",
    "validate_request_data",
    "ValidationMixin",
    "sanitize_html",
    "sanitize_text",
    "sanitize_sql",
    "sanitize_filename",
    "sanitize_url",
    "sanitize_dict",
    "sanitize_list",
    "validate_input",
    "sanitize_input",
    "VALIDATION_CONFIG",
    "SAFE_FILE_TYPES",
]
