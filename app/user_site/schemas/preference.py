from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class ThemeType(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class FontSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    EXTRA_LARGE = "extra_large"


class UserPreferenceBase(BaseModel):
    theme: Optional[str] = "system"
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    reading_mode: Optional[str] = None
    language: Optional[str] = None
    notifications_enabled: bool = True
    email_notifications: bool = True
    push_notifications: bool = True
    reading_speed_wpm: Optional[int] = None
    auto_bookmark: bool = True
    display_recommendations: bool = True
    privacy_level: str = "public"


class UserPreferenceUpdate(BaseModel):
    theme: Optional[ThemeType] = None
    font_size: Optional[FontSize] = None
    enable_notifications: Optional[bool] = None
    email_notifications: Optional[bool] = None
    public_profile: Optional[bool] = None
    public_reading_activity: Optional[bool] = None
    public_bookshelves: Optional[bool] = None
    preferred_language: Optional[str] = None


class UserPreferenceResponse(UserPreferenceBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True


class ThemePreferenceResponse(BaseModel):
    """Schema cho thông tin theme."""

    id: int
    name: str
    description: Optional[str] = None
    colors: dict
    font_family: Optional[str] = None
    is_dark: bool = False
    is_system: bool = False
    is_default: bool = False
    preview_image: Optional[str] = None

    class Config:
        from_attributes = True


class ReadingPreferenceResponse(BaseModel):
    """Schema cho cài đặt đọc sách."""

    id: int
    user_id: int
    font_size: FontSize = FontSize.MEDIUM
    font_family: Optional[str] = "Default"
    line_spacing: float = 1.5
    margin: float = 1.0
    background_color: str = "#FFFFFF"
    text_color: str = "#000000"
    reading_mode: str = "continuous"
    enable_page_transitions: bool = True
    auto_scroll_speed: Optional[int] = None
    remember_position: bool = True
    highlight_style: str = "underline"
    show_reading_stats: bool = True
    reading_speed_wpm: Optional[int] = 250

    class Config:
        from_attributes = True


class NotificationPreferenceResponse(BaseModel):
    """Schema cho cài đặt thông báo."""

    id: int
    user_id: int
    email_notifications: bool = True
    push_notifications: bool = True
    in_app_notifications: bool = True
    social_notifications: bool = True
    system_notifications: bool = True
    marketing_notifications: bool = False
    quiet_hours_enabled: bool = False
    quiet_hours_start: Optional[str] = "22:00"
    quiet_hours_end: Optional[str] = "08:00"
    frequency: str = "realtime"  # realtime, daily, weekly

    class Config:
        from_attributes = True


class PrivacyPreferenceResponse(BaseModel):
    """Schema cho cài đặt quyền riêng tư."""

    id: int
    user_id: int
    public_profile: bool = True
    show_reading_activity: bool = True
    show_bookshelves: bool = True
    show_reviews: bool = True
    show_followers: bool = True
    show_following: bool = True
    allow_friend_requests: bool = True
    allow_recommendations: bool = True
    allow_messages: bool = True
    search_engine_visibility: bool = True

    class Config:
        from_attributes = True


class DeviceSyncRequest(BaseModel):
    """Schema cho yêu cầu đồng bộ thiết bị."""

    device_id: str
    device_name: str
    device_type: str  # mobile, tablet, desktop
    app_version: str
    preferences: Optional[Dict[str, Any]] = None
    last_sync_time: Optional[datetime] = None


class DeviceSyncResponse(BaseModel):
    """Schema cho phản hồi đồng bộ thiết bị."""

    success: bool
    sync_time: datetime
    preferences: Dict[str, Any]
    conflicts: Optional[List[str]] = None
    message: Optional[str] = None

    class Config:
        from_attributes = True
