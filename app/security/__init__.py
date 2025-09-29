"""
Module bảo mật (Security) - Cung cấp các giải pháp bảo mật toàn diện cho ứng dụng.

Module này bao gồm:
- Access Control: Kiểm soát truy cập dựa trên vai trò (RBAC) và thuộc tính (ABAC)
- Audit: Ghi nhật ký và kiểm toán hành động người dùng
- DDoS Protection: Bảo vệ chống tấn công từ chối dịch vụ
- Encryption: Mã hóa dữ liệu và lưu trữ
- Secure Headers: Bảo mật HTTP headers
- Input Validation: Xác thực và làm sạch đầu vào
- WAF: Web Application Firewall
- Secrets: Quản lý bí mật và thông tin nhạy cảm
"""

# Import các module con
from app.security import access_control
from app.security import audit
from app.security import ddos
from app.security import encryption
from app.security import headers
from app.security import input_validation
from app.security import waf
from app.security import secrets

# Import các class và hàm chính để dễ sử dụng
from app.security.access_control.rbac import (
    get_current_user,
    get_current_admin,
    get_current_active_user,
    get_current_super_admin,
    check_permissions,
    check_permission,
    requires_role,
)

from app.security.access_control.abac import (
    Policy,
    OwnershipPolicy,
    SubscriptionPolicy,
    TimeWindowPolicy,
    CompositePolicy,
    check_policy,
)

from app.security.audit.audit_trails import (
    log_auth_success,
    log_auth_failure,
    log_access_attempt,
    log_data_operation,
    log_security_event,
)

# Đã sửa lỗi null bytes, bật lại import
from app.security.audit.log_admin_action import (
    log_admin_action,
    log_admin_login,
    log_admin_logout,
    log_admin_access,
)

from app.security.ddos.protection import DDoSProtection
from app.security.ddos.rate_limiter import AdvancedRateLimiter

from app.security.encryption.field_encryption import (
    EncryptedType,
    EncryptedDict,
    EncryptedList,
    EncryptedString,
    EncryptedInteger,
    encrypt_sensitive_data,
    decrypt_sensitive_data,
    decrypt_sensitive_content,
)

from app.security.encryption.storage_encryption import FileEncryption

from app.security.headers.secure_headers import SecureHeaders, SecureHeadersMiddleware

from app.security.input_validation.validators import (
    validate_email,
    validate_password,
    validate_username,
    validate_url,
    validate_request_data,
)

from app.security.input_validation.sanitizers import (
    sanitize_html,
    sanitize_text,
    sanitize_sql,
    sanitize_filename,
    sanitize_url,
)

from app.security.waf import (
    setup_waf,
    detect_sql_injection,
    detect_xss,
    detect_path_traversal,
)


# Hàm tiện ích để thiết lập các tính năng bảo mật
def setup_security(app=None):
    """
    Thiết lập và khởi tạo các tính năng bảo mật cho ứng dụng.

    Args:
        app: Ứng dụng FastAPI (tùy chọn)

    Returns:
        Dict các thành phần bảo mật đã được cấu hình
    """
    security_components = {}

    if app:
        # Thiết lập WAF
        waf.setup_waf(app)
        security_components["waf"] = "configured"

        # Thiết lập Secure Headers
        app.add_middleware(SecureHeadersMiddleware)
        security_components["secure_headers"] = "configured"

        # Thiết lập Rate Limiter nếu cần
        from app.core.config import get_settings

        settings = get_settings()

        if settings.RATE_LIMITING_ENABLED:
            app.add_middleware(
                AdvancedRateLimiter,
                default_rate_limit=settings.RATE_LIMIT_PER_MINUTE,
                admin_rate_limit=settings.RATE_LIMIT_ADMIN_PER_MINUTE,
            )
            security_components["rate_limiter"] = "configured"

    return security_components


# Export các components
__all__ = [
    "setup_security",
    "access_control",
    "audit",
    "ddos",
    "encryption",
    "headers",
    "input_validation",
    "waf",
    "secrets",
    # RBAC
    "get_current_user",
    "get_current_admin",
    "get_current_active_user",
    "get_current_super_admin",
    "check_permissions",
    "check_permission",
    "requires_role",
    # ABAC
    "Policy",
    "OwnershipPolicy",
    "SubscriptionPolicy",
    "TimeWindowPolicy",
    "CompositePolicy",
    "check_policy",
    # Audit
    "log_auth_success",
    "log_auth_failure",
    "log_access_attempt",
    "log_data_operation",
    "log_security_event",
    "log_admin_action",
    "log_admin_login",
    "log_admin_logout",
    "log_admin_access",
    # DDoS
    "DDoSProtection",
    "AdvancedRateLimiter",
    # Encryption
    "EncryptedType",
    "EncryptedDict",
    "EncryptedList",
    "EncryptedString",
    "EncryptedInteger",
    "FileEncryption",
    # Headers
    "SecureHeaders",
    "SecureHeadersMiddleware",
    # Validation
    "validate_email",
    "validate_password",
    "validate_username",
    "validate_url",
    "validate_request_data",
    # Sanitization
    "sanitize_html",
    "sanitize_text",
    "sanitize_sql",
    "sanitize_filename",
    "sanitize_url",
    # WAF
    "setup_waf",
    "detect_sql_injection",
    "detect_xss",
    "detect_path_traversal",
]
