# Tệp này được tạo để đánh dấu thư mục này là một gói Python
# Đồng thời xuất các module và router để sử dụng ở nơi khác

# Remove circular import: from app.admin_site.api.router import admin_router
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    get_super_admin,
    secure_admin_access,
)

# Export tất cả các module API
from app.admin_site.api.v1 import (
    auth,
    admins,
    roles,
    permissions,
    admin_sessions,
    system_settings,
    system_metrics,
    system_health,
    content_approval,
    featured_content,
    promotions,
    achievements,
    badges,
    books,
    users,
    analytics,
    reports,
    authors,
    categories,
    chapters,
    tags,
    logs,
    dashboard,
    discussions,
    publishers,
    reviews,
    subscriptions,
    book_series,
)

__all__ = [
    # "admin_router",  # Remove this from exports
    "get_current_admin",
    "check_admin_permissions",
    "get_super_admin",
    "secure_admin_access",
    # Modules
    "auth",
    "admins",
    "roles",
    "permissions",
    "admin_sessions",
    "system_settings",
    "system_metrics",
    "system_health",
    "content_approval",
    "featured_content",
    "promotions",
    "achievements",
    "badges",
    "books",
    "users",
    "analytics",
    "reports",
    "authors",
    "categories",
    "chapters",
    "tags",
    "logs",
    "dashboard",
    "discussions",
    "publishers",
    "reviews",
    "subscriptions",
    "book_series",
]

# Imports for the v1 API
# Cần rỗng để tránh circular import
