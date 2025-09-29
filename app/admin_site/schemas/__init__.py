# Import tất cả schemas của admin
from app.admin_site.schemas.achievement import (
    AchievementBase,
    AchievementCreate,
    AchievementUpdate,
    AchievementInDB,
    AchievementInfo,
)
from app.admin_site.schemas.admin import (
    AdminBase,
    AdminCreate,
    AdminUpdate,
    AdminInDB,
    AdminInfo,
    AdminWithRoles,
)
from app.admin_site.schemas.admin_session import (
    AdminSessionBase,
    AdminSessionCreate,
    AdminSessionResponse,
    AdminSessionList,
    AdminSessionInfo,
)
from app.admin_site.schemas.auth import (
    AdminLoginResponse,
    AdminRefreshTokenRequest,
    AdminChangePasswordRequest,
)
from app.admin_site.schemas.badge import (
    BadgeBase,
    BadgeCreate,
    BadgeUpdate,
    BadgeInDB,
    BadgeInfo,
)
from app.admin_site.schemas.content_approval import (
    ContentApprovalBase,
    ContentApprovalCreate,
    ContentApprovalUpdate,
    ContentApprovalInDB,
    ContentApprovalInfo,
    ContentApprovalAction,
)
from app.admin_site.schemas.featured_content import (
    FeaturedContentBase,
    FeaturedContentCreate,
    FeaturedContentUpdate,
    FeaturedContentInDB,
    FeaturedContentInfo,
)
from app.admin_site.schemas.permission import (
    PermissionBase,
    PermissionCreate,
    PermissionUpdate,
    PermissionInDB,
    PermissionInfo,
)
from app.admin_site.schemas.promotion import (
    PromotionBase,
    PromotionCreate,
    PromotionUpdate,
    PromotionInDB,
    PromotionInfo,
)
from app.admin_site.schemas.role import (
    RoleBase,
    RoleCreate,
    RoleUpdate,
    RoleInDB,
    RoleInfo,
    RoleWithPermissions,
)
from app.admin_site.schemas.system_health import (
    SystemHealthBase,
    SystemHealthCreate,
    SystemHealthUpdate,
    SystemHealthInDB,
    SystemHealthInfo,
)
from app.admin_site.schemas.system_metric import (
    SystemMetricBase,
    SystemMetricCreate,
    SystemMetricUpdate,
    SystemMetricInDB,
    SystemMetricInfo,
)
from app.admin_site.schemas.system_setting import (
    SystemSettingBase,
    SystemSettingCreate,
    SystemSettingUpdate,
    SystemSettingInDB,
    SystemSettingInfo,
    SystemSettingPublic,
)
from app.admin_site.schemas.analytics import (
    UserAnalyticsResponse,
    ContentAnalyticsResponse,
    RevenueAnalyticsResponse,
    EngagementAnalyticsResponse,
)
from app.admin_site.schemas.report import (
    UserReportResponse,
    ContentReportResponse,
    FinancialReportResponse,
    SystemReportResponse,
    ActivityReportResponse,
)

__all__ = [
    # Achievement
    "AchievementBase",
    "AchievementCreate",
    "AchievementUpdate",
    "AchievementInDB",
    "AchievementInfo",
    # Admin
    "AdminBase",
    "AdminCreate",
    "AdminUpdate",
    "AdminInDB",
    "AdminInfo",
    "AdminWithRoles",
    # Admin Session
    "AdminSessionBase",
    "AdminSessionCreate",
    "AdminSessionResponse",
    "AdminSessionList",
    "AdminSessionInfo",
    # Auth
    "AdminLoginResponse",
    "AdminRefreshTokenRequest",
    "AdminChangePasswordRequest",
    # Badge
    "BadgeBase",
    "BadgeCreate",
    "BadgeUpdate",
    "BadgeInDB",
    "BadgeInfo",
    # Content Approval
    "ContentApprovalBase",
    "ContentApprovalCreate",
    "ContentApprovalUpdate",
    "ContentApprovalInDB",
    "ContentApprovalInfo",
    "ContentApprovalAction",
    # Featured Content
    "FeaturedContentBase",
    "FeaturedContentCreate",
    "FeaturedContentUpdate",
    "FeaturedContentInDB",
    "FeaturedContentInfo",
    # Permission
    "PermissionBase",
    "PermissionCreate",
    "PermissionUpdate",
    "PermissionInDB",
    "PermissionInfo",
    # Promotion
    "PromotionBase",
    "PromotionCreate",
    "PromotionUpdate",
    "PromotionInDB",
    "PromotionInfo",
    # Role
    "RoleBase",
    "RoleCreate",
    "RoleUpdate",
    "RoleInDB",
    "RoleInfo",
    "RoleWithPermissions",
    # System Health
    "SystemHealthBase",
    "SystemHealthCreate",
    "SystemHealthUpdate",
    "SystemHealthInDB",
    "SystemHealthInfo",
    # System Metric
    "SystemMetricBase",
    "SystemMetricCreate",
    "SystemMetricUpdate",
    "SystemMetricInDB",
    "SystemMetricInfo",
    # System Setting
    "SystemSettingBase",
    "SystemSettingCreate",
    "SystemSettingUpdate",
    "SystemSettingInDB",
    "SystemSettingInfo",
    "SystemSettingPublic",
    # Analytics
    "UserAnalyticsResponse",
    "ContentAnalyticsResponse",
    "RevenueAnalyticsResponse",
    "EngagementAnalyticsResponse",
    # Report
    "UserReportResponse",
    "ContentReportResponse",
    "FinancialReportResponse",
    "SystemReportResponse",
    "ActivityReportResponse",
]
