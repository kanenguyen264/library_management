"""
Cấu hình tuân thủ (Compliance).

Module này định nghĩa các cấu hình cho việc tuân thủ các quy định bảo mật:
- Chính sách mật khẩu
- Timeout của phiên đăng nhập
- Chính sách đăng nhập
- Yêu cầu HTTPS
- Bảo vệ CSRF
- Kiểm tra quyền đủ tối thiểu
"""

from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ComplianceConfig(BaseSettings):
    """
    Cấu hình tuân thủ (Compliance).

    Attributes:
        COMPLIANCE_REQUIRE_HTTPS: Yêu cầu sử dụng HTTPS
        COMPLIANCE_HSTS_ENABLED: Bật/tắt HSTS (HTTP Strict Transport Security)
        COMPLIANCE_HSTS_MAX_AGE: Thời gian HSTS (giây)
        COMPLIANCE_SESSION_TIMEOUT: Thời gian hết hạn phiên (giây)
        COMPLIANCE_PASSWORD_MIN_LENGTH: Độ dài tối thiểu của mật khẩu
        COMPLIANCE_PASSWORD_SPECIAL_CHARS: Yêu cầu ký tự đặc biệt trong mật khẩu
        COMPLIANCE_PASSWORD_NUMBERS: Yêu cầu chữ số trong mật khẩu
        COMPLIANCE_PASSWORD_UPPERCASE: Yêu cầu chữ in hoa trong mật khẩu
        COMPLIANCE_PASSWORD_LOWERCASE: Yêu cầu chữ thường trong mật khẩu
        COMPLIANCE_PASSWORD_EXPIRY_DAYS: Số ngày hết hạn mật khẩu
        COMPLIANCE_MAX_LOGIN_ATTEMPTS: Số lần đăng nhập thất bại tối đa
        COMPLIANCE_LOCKOUT_DURATION: Thời gian khóa tài khoản (giây)
        COMPLIANCE_CSRF_ENABLED: Bật/tắt bảo vệ CSRF
        COMPLIANCE_CSRF_COOKIE_SECURE: Cookie CSRF yêu cầu HTTPS
        COMPLIANCE_CSRF_TRUSTED_ORIGINS: Danh sách origin được tin tưởng cho CSRF
        COMPLIANCE_AUDIT_TRAIL_ENABLED: Bật/tắt ghi nhật ký hành động
        COMPLIANCE_INACTIVE_USER_DAYS: Số ngày không hoạt động trước khi vô hiệu hóa
        COMPLIANCE_MIN_PERMISSION_CHECK: Bật/tắt kiểm tra quyền tối thiểu
        COMPLIANCE_DATA_RETENTION_DAYS: Số ngày lưu trữ dữ liệu
    """

    COMPLIANCE_REQUIRE_HTTPS: bool = Field(
        default=True, description="Yêu cầu sử dụng HTTPS"
    )

    COMPLIANCE_HSTS_ENABLED: bool = Field(
        default=True, description="Bật/tắt HSTS (HTTP Strict Transport Security)"
    )

    COMPLIANCE_HSTS_MAX_AGE: int = Field(
        default=31536000, description="Thời gian HSTS (giây)"  # 1 năm
    )

    COMPLIANCE_SESSION_TIMEOUT: int = Field(
        default=3600, description="Thời gian hết hạn phiên (giây)"  # 1 giờ
    )

    COMPLIANCE_PASSWORD_MIN_LENGTH: int = Field(
        default=8, description="Độ dài tối thiểu của mật khẩu"
    )

    COMPLIANCE_PASSWORD_SPECIAL_CHARS: bool = Field(
        default=True, description="Yêu cầu ký tự đặc biệt trong mật khẩu"
    )

    COMPLIANCE_PASSWORD_NUMBERS: bool = Field(
        default=True, description="Yêu cầu chữ số trong mật khẩu"
    )

    COMPLIANCE_PASSWORD_UPPERCASE: bool = Field(
        default=True, description="Yêu cầu chữ in hoa trong mật khẩu"
    )

    COMPLIANCE_PASSWORD_LOWERCASE: bool = Field(
        default=True, description="Yêu cầu chữ thường trong mật khẩu"
    )

    COMPLIANCE_PASSWORD_EXPIRY_DAYS: int = Field(
        default=90, description="Số ngày hết hạn mật khẩu"
    )

    COMPLIANCE_MAX_LOGIN_ATTEMPTS: int = Field(
        default=5, description="Số lần đăng nhập thất bại tối đa"
    )

    COMPLIANCE_LOCKOUT_DURATION: int = Field(
        default=1800, description="Thời gian khóa tài khoản (giây)"  # 30 phút
    )

    COMPLIANCE_CSRF_ENABLED: bool = Field(
        default=True, description="Bật/tắt bảo vệ CSRF"
    )

    COMPLIANCE_CSRF_COOKIE_SECURE: bool = Field(
        default=True, description="Cookie CSRF yêu cầu HTTPS"
    )

    COMPLIANCE_CSRF_TRUSTED_ORIGINS: List[str] = Field(
        default=[], description="Danh sách origin được tin tưởng cho CSRF"
    )

    COMPLIANCE_AUDIT_TRAIL_ENABLED: bool = Field(
        default=True, description="Bật/tắt ghi nhật ký hành động"
    )

    COMPLIANCE_INACTIVE_USER_DAYS: int = Field(
        default=90, description="Số ngày không hoạt động trước khi vô hiệu hóa"
    )

    COMPLIANCE_MIN_PERMISSION_CHECK: bool = Field(
        default=True, description="Bật/tắt kiểm tra quyền tối thiểu"
    )

    COMPLIANCE_DATA_RETENTION_DAYS: int = Field(
        default=365, description="Số ngày lưu trữ dữ liệu"  # 1 năm
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="COMPLIANCE_",
    )

    def get_password_policy(self) -> dict:
        """
        Lấy chính sách mật khẩu.

        Returns:
            Dict chính sách mật khẩu
        """
        return {
            "min_length": self.COMPLIANCE_PASSWORD_MIN_LENGTH,
            "require_special_chars": self.COMPLIANCE_PASSWORD_SPECIAL_CHARS,
            "require_numbers": self.COMPLIANCE_PASSWORD_NUMBERS,
            "require_uppercase": self.COMPLIANCE_PASSWORD_UPPERCASE,
            "require_lowercase": self.COMPLIANCE_PASSWORD_LOWERCASE,
            "expiry_days": self.COMPLIANCE_PASSWORD_EXPIRY_DAYS,
        }

    def get_login_policy(self) -> dict:
        """
        Lấy chính sách đăng nhập.

        Returns:
            Dict chính sách đăng nhập
        """
        return {
            "max_attempts": self.COMPLIANCE_MAX_LOGIN_ATTEMPTS,
            "lockout_duration": self.COMPLIANCE_LOCKOUT_DURATION,
            "session_timeout": self.COMPLIANCE_SESSION_TIMEOUT,
            "inactive_user_days": self.COMPLIANCE_INACTIVE_USER_DAYS,
        }

    def get_security_headers(self) -> dict:
        """
        Lấy headers bảo mật.

        Returns:
            Dict headers bảo mật
        """
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:;",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }

        if self.COMPLIANCE_HSTS_ENABLED and self.COMPLIANCE_REQUIRE_HTTPS:
            headers["Strict-Transport-Security"] = (
                f"max-age={self.COMPLIANCE_HSTS_MAX_AGE}; includeSubDomains"
            )

        return headers

    def validate_password(self, password: str) -> tuple[bool, str]:
        """
        Kiểm tra mật khẩu có đáp ứng chính sách không.

        Args:
            password: Mật khẩu cần kiểm tra

        Returns:
            (bool, str): (Hợp lệ, Lý do nếu không hợp lệ)
        """
        if len(password) < self.COMPLIANCE_PASSWORD_MIN_LENGTH:
            return (
                False,
                f"Mật khẩu phải có ít nhất {self.COMPLIANCE_PASSWORD_MIN_LENGTH} ký tự",
            )

        if self.COMPLIANCE_PASSWORD_SPECIAL_CHARS and not any(
            c in "!@#$%^&*()_+{}[]|\:;'\"<>,.?/~`" for c in password
        ):
            return False, "Mật khẩu phải chứa ít nhất một ký tự đặc biệt"

        if self.COMPLIANCE_PASSWORD_NUMBERS and not any(c.isdigit() for c in password):
            return False, "Mật khẩu phải chứa ít nhất một chữ số"

        if self.COMPLIANCE_PASSWORD_UPPERCASE and not any(
            c.isupper() for c in password
        ):
            return False, "Mật khẩu phải chứa ít nhất một chữ in hoa"

        if self.COMPLIANCE_PASSWORD_LOWERCASE and not any(
            c.islower() for c in password
        ):
            return False, "Mật khẩu phải chứa ít nhất một chữ thường"

        return True, ""


# Khởi tạo cấu hình
compliance_config = ComplianceConfig()
