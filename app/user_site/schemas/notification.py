from typing import List, Optional, Dict, Any, Set, Union, Literal
from datetime import datetime
from enum import Enum, auto
from pydantic import BaseModel, Field, validator


class NotificationCategoryEnum(str, Enum):
    """Enum cho các loại danh mục thông báo."""

    SYSTEM = "system"
    USER = "user"
    SOCIAL = "social"
    BOOK = "book"
    READING = "reading"
    ACHIEVEMENT = "achievement"
    MARKETING = "marketing"
    OTHER = "other"


class NotificationPriorityEnum(str, Enum):
    """Enum cho mức độ ưu tiên của thông báo."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationBase(BaseModel):
    type: str
    title: str
    message: str
    link: Optional[str] = None
    is_read: bool = False


class NotificationResponse(NotificationBase):
    id: int
    user_id: int
    created_at: datetime
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int

    class Config:
        from_attributes = True


class NotificationSettingsResponse(BaseModel):
    """Schema cho cài đặt thông báo của người dùng."""

    email_notifications: bool = False
    push_notifications: bool = True
    browser_notifications: bool = True
    notification_types: Dict[str, bool] = Field(
        default_factory=lambda: {
            "activity": True,
            "mentions": True,
            "follows": True,
            "comments": True,
            "likes": True,
            "system": True,
            "marketing": False,
        }
    )
    quiet_hours: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": False,
            "start_time": "22:00",
            "end_time": "08:00",
            "timezone": "UTC",
        }
    )

    class Config:
        from_attributes = True


class NotificationSettingsUpdate(BaseModel):
    """Schema cho cập nhật cài đặt thông báo của người dùng."""

    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    browser_notifications: Optional[bool] = None
    notification_types: Optional[Dict[str, bool]] = None
    quiet_hours: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class DeviceNotificationToken(BaseModel):
    """Schema cho token thông báo thiết bị."""

    token: str
    device_type: str = Field(..., description="Loại thiết bị: ios, android, web")
    device_name: Optional[str] = None
    device_id: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class NotificationCategoryResponse(BaseModel):
    """Schema cho danh mục thông báo."""

    id: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_enabled: bool = True

    class Config:
        from_attributes = True


class NotificationFilterParams(BaseModel):
    """Tham số lọc thông báo."""

    category: Optional[NotificationCategoryEnum] = None
    is_read: Optional[bool] = None
    priority: Optional[NotificationPriorityEnum] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class NotificationPreferences(BaseModel):
    """Tùy chọn nhận thông báo."""

    email: bool = True
    push: bool = True
    in_app: bool = True


class NotificationPreferencesResponse(BaseModel):
    """Phản hồi về tùy chọn thông báo."""

    categories: Dict[str, NotificationPreferences] = {}

    class Config:
        from_attributes = True


class NotificationPreferencesUpdate(BaseModel):
    """Cập nhật tùy chọn thông báo."""

    categories: Dict[str, NotificationPreferences]


class NotificationCountResponse(BaseModel):
    """Phản hồi số lượng thông báo."""

    total: int = 0
    unread: int = 0

    class Config:
        from_attributes = True


class NotificationStats(BaseModel):
    """Thống kê thông báo."""

    total_received: int = 0
    read_count: int = 0
    unread_count: int = 0
    email_sent: int = 0
    push_sent: int = 0
    by_category: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}


class NotificationStatsResponse(BaseModel):
    """Phản hồi thống kê thông báo."""

    stats: NotificationStats
    period: str

    class Config:
        from_attributes = True


class NotificationSearchParams(BaseModel):
    """Tham số tìm kiếm thông báo."""

    query: str
    categories: Optional[List[NotificationCategoryEnum]] = None
    date_range: Optional[List[datetime]] = None
    is_read: Optional[bool] = None


class BulkNotificationAction(str, Enum):
    """Các hành động xử lý hàng loạt thông báo."""

    MARK_READ = "mark_read"
    MARK_UNREAD = "mark_unread"
    DELETE = "delete"


class NotificationBulkAction(str, Enum):
    """Alias cho BulkNotificationAction."""

    MARK_READ = "mark_read"
    MARK_UNREAD = "mark_unread"
    DELETE = "delete"


class NotificationBulkUpdateRequest(BaseModel):
    """Yêu cầu cập nhật hàng loạt thông báo."""

    ids: List[int]
    action: BulkNotificationAction


class NotificationCreate(BaseModel):
    """Tạo mới thông báo."""

    user_id: int
    type: str
    category: NotificationCategoryEnum
    priority: NotificationPriorityEnum = NotificationPriorityEnum.MEDIUM
    title: str
    message: str
    link: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    image_url: Optional[str] = None
    expires_at: Optional[datetime] = None


class PushNotificationToken(BaseModel):
    """Token thiết bị cho thông báo đẩy."""

    token: str
    platform: str

    class Config:
        from_attributes = True


class DeviceRegistration(BaseModel):
    """Đăng ký thiết bị."""

    token: str
    platform: str = Field(..., description="Nền tảng thiết bị: ios, android, web")
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    app_version: Optional[str] = None


class NotificationCategory(BaseModel):
    """Danh mục thông báo."""

    id: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationPriority(BaseModel):
    """Mức độ ưu tiên của thông báo."""

    id: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationPreferenceResponse(BaseModel):
    """Tùy chọn thông báo chi tiết."""

    category_id: str
    email_enabled: bool = True
    push_enabled: bool = True
    in_app_enabled: bool = True

    class Config:
        from_attributes = True


class NotificationMarkRequest(BaseModel):
    """Yêu cầu đánh dấu thông báo."""

    notification_id: int
    is_read: bool
