"""
Security audit module for logging and tracking security events.

This module provides functionality for audit trail logging, admin actions,
user activities tracking, and security event monitoring.
"""

from app.security.audit.audit_trails import (
    log_data_operation,
    log_access_attempt,
    get_audit_trail,
    log_auth_success,
    log_auth_failure,
)

# Uncomment since the null bytes have been fixed
from app.security.audit.log_admin_action import (
    log_admin_action,
    log_admin_access,
    log_admin_login,
    log_admin_logout,
)

# Không cần hàm giả nữa vì đã sửa lỗi và thêm hàm thật vào log_admin_action.py

__all__ = [
    "log_data_operation",
    "log_access_attempt",
    "get_audit_trail",
    "log_admin_action",
    "log_admin_access",
    "log_admin_login",
    "log_admin_logout",
    "log_auth_success",
    "log_auth_failure",
]
