from typing import Optional, List, Dict, Any
from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field, validator
from app.user_site.models.user import Gender


class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[Gender] = None
    country: Optional[str] = None
    language: Optional[str] = None

    class Config:
        from_attributes = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    password_confirm: str

    @validator("password_confirm")
    def passwords_match(cls, v, values, **kwargs):
        if "password" in values and v != values["password"]:
            raise ValueError("Mật khẩu không khớp")
        return v

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[Gender] = None
    country: Optional[str] = None
    language: Optional[str] = None

    class Config:
        from_attributes = True


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    new_password_confirm: str

    @validator("new_password_confirm")
    def passwords_match(cls, v, values, **kwargs):
        if "new_password" in values and v != values["new_password"]:
            raise ValueError("Mật khẩu không khớp")
        return v


class UserResponse(UserBase):
    id: int
    is_premium: bool
    premium_until: Optional[datetime] = None
    is_verified: bool
    last_login: Optional[datetime] = None
    last_active: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserPublicResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    is_premium: bool
    country: Optional[str] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class TokenData(BaseModel):
    user_id: Optional[int] = None


class UserListResponse(BaseModel):
    items: List[UserResponse]
    total: int
    page: Optional[int] = 1
    size: Optional[int] = 10

    class Config:
        from_attributes = True


class UserPreference(BaseModel):
    id: int
    user_id: int
    key: str
    value: Any
    data_type: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserStatsResponse(BaseModel):
    total_users: int
    active_users: int
    premium_users: int
    verified_users: int
    users_by_gender: Dict[str, int] = {}
    users_by_country: Dict[str, int] = {}
    users_by_language: Dict[str, int] = {}
    users_by_age_group: Dict[str, int] = {}
    registrations_by_month: Dict[str, int] = {}
    last_login_distribution: Dict[str, int] = {}
    recent_users: List[UserResponse] = []
    most_active_users: List[Dict[str, Any]] = []
    premium_percentage: float = 0
    verified_percentage: float = 0
    average_age: Optional[float] = None

    class Config:
        from_attributes = True


class UserPreferencesUpdate(BaseModel):
    """Schema cập nhật tùy chọn người dùng."""

    theme: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    enable_notifications: Optional[bool] = None
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    reading_preferences: Optional[Dict[str, Any]] = None
    privacy_settings: Optional[Dict[str, bool]] = None
    display_settings: Optional[Dict[str, Any]] = None


class UserActivity(BaseModel):
    """Hoạt động người dùng."""

    activity_type: str  # read, review, like, follow, etc.
    timestamp: datetime
    book_id: Optional[int] = None
    book_title: Optional[str] = None
    book_cover: Optional[str] = None
    target_user_id: Optional[int] = None
    target_user_name: Optional[str] = None
    target_user_avatar: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class UserActivityResponse(BaseModel):
    """Phản hồi hoạt động người dùng."""

    items: List[UserActivity]
    total: int

    class Config:
        from_attributes = True


class UserSecuritySettings(BaseModel):
    """Cài đặt bảo mật người dùng."""

    two_factor_enabled: bool = False
    two_factor_method: Optional[str] = None  # sms, app, email
    login_notifications: bool = False
    suspicious_activity_alerts: bool = True
    active_sessions: List[Dict[str, Any]] = []
    recent_logins: List[Dict[str, Any]] = []
    password_last_changed: Optional[datetime] = None
    security_questions_set: bool = False

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    """Chi tiết hồ sơ người dùng."""

    id: int
    username: str
    display_name: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[Gender] = None
    country: Optional[str] = None
    language: Optional[str] = None
    is_premium: bool = False
    is_verified: bool = False
    joined_date: datetime
    last_active: Optional[datetime] = None
    books_count: int = 0
    reviews_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    favorite_genres: List[str] = []
    reading_stats: Dict[str, Any] = {}
    social_links: Dict[str, str] = {}
    badges: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True
