"""
Module kiểm soát truy cập (Access Control) - Cung cấp các cơ chế xác thực và phân quyền.

Module này cung cấp:
- Role-Based Access Control (RBAC): Kiểm soát truy cập dựa trên vai trò
- Attribute-Based Access Control (ABAC): Kiểm soát truy cập dựa trên thuộc tính
- Các hàm dependency cho FastAPI để xác thực người dùng và admin
"""

from app.security.access_control.rbac import (
    get_current_user,
    get_current_active_user,
    get_current_admin,
    get_current_super_admin,
    check_permissions,
    check_permission,
    requires_role,
    user_owns_resource,
    oauth2_scheme,
)

from app.security.access_control.abac import (
    Policy,
    OwnershipPolicy,
    SubscriptionPolicy,
    TimeWindowPolicy,
    CompositePolicy,
    check_policy,
)

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Danh sách quyền mặc định cho hệ thống
DEFAULT_PERMISSIONS = {
    # Admin permissions
    "admin": {
        "admin:access": "Quyền truy cập trang quản trị",
        "admin:manage_users": "Quản lý người dùng",
        "admin:manage_content": "Quản lý nội dung",
        "admin:view_reports": "Xem báo cáo",
        "admin:manage_settings": "Quản lý cài đặt hệ thống",
    },
    # User permissions
    "user": {
        "user:profile:edit": "Chỉnh sửa thông tin cá nhân",
        "user:books:read": "Đọc sách",
        "user:books:write_review": "Viết đánh giá sách",
        "user:books:bookmark": "Đánh dấu sách",
    },
}

# Export các components
__all__ = [
    # RBAC
    "get_current_user",
    "get_current_active_user",
    "get_current_admin",
    "get_current_super_admin",
    "check_permissions",
    "check_permission",
    "requires_role",
    "user_owns_resource",
    "oauth2_scheme",
    # ABAC
    "Policy",
    "OwnershipPolicy",
    "SubscriptionPolicy",
    "TimeWindowPolicy",
    "CompositePolicy",
    "check_policy",
    # Constants
    "DEFAULT_PERMISSIONS",
]
