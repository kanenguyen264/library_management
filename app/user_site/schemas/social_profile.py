from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl
from app.user_site.schemas.user import UserPublicResponse


class SocialProviderType(str, Enum):
    """Loại nhà cung cấp mạng xã hội."""

    FACEBOOK = "facebook"
    TWITTER = "twitter"
    GOOGLE = "google"
    GITHUB = "github"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    GOODREADS = "goodreads"


class SocialProfileBase(BaseModel):
    """Schema cơ bản cho hồ sơ mạng xã hội."""

    provider: str
    provider_user_id: str
    username: Optional[str] = None
    profile_url: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None


class SocialProfileCreate(SocialProfileBase):
    """Schema tạo hồ sơ mạng xã hội."""

    user_id: int
    is_verified: bool = False
    token_data: Optional[Dict[str, Any]] = None


class SocialProfileUpdate(BaseModel):
    """Schema cập nhật hồ sơ mạng xã hội."""

    username: Optional[str] = None
    profile_url: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    last_synced_at: Optional[datetime] = None


class SocialProfileResponse(SocialProfileBase):
    """Phản hồi hồ sơ mạng xã hội."""

    id: int
    user_id: int
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SocialProfileListResponse(BaseModel):
    """Danh sách phản hồi hồ sơ mạng xã hội."""

    items: List[SocialProfileResponse]
    total: int

    class Config:
        from_attributes = True


class FollowRequest(BaseModel):
    """Yêu cầu theo dõi."""

    user_id: int
    message: Optional[str] = None


class FollowersResponse(BaseModel):
    """Phản hồi người theo dõi."""

    items: List[UserPublicResponse]
    total: int

    class Config:
        from_attributes = True


class FollowingResponse(BaseModel):
    """Phản hồi người đang theo dõi."""

    items: List[UserPublicResponse]
    total: int

    class Config:
        from_attributes = True


class SocialStats(BaseModel):
    """Thống kê mạng xã hội."""

    followers_count: int = 0
    following_count: int = 0
    books_read_count: int = 0
    reviews_count: int = 0
    quotes_count: int = 0
    likes_received: int = 0
    comments_received: int = 0
    shares_received: int = 0
    total_engagement: int = 0
    activity_level: str = "low"  # low, medium, high, very_high


class SocialStatsResponse(BaseModel):
    """Phản hồi thống kê mạng xã hội."""

    user_id: int
    stats: SocialStats

    class Config:
        from_attributes = True


class SocialActivity(BaseModel):
    """Hoạt động mạng xã hội."""

    activity_type: str  # follow, like, comment, share, review, etc.
    timestamp: datetime
    user: UserPublicResponse
    target_type: str  # user, book, review, quote, etc.
    target_id: int
    target_title: Optional[str] = None
    target_image: Optional[str] = None
    content: Optional[str] = None


class SocialActivityResponse(BaseModel):
    """Phản hồi hoạt động mạng xã hội."""

    items: List[SocialActivity]
    total: int

    class Config:
        from_attributes = True


class RecommendedUser(BaseModel):
    """Người dùng được đề xuất."""

    user: UserPublicResponse
    mutual_followers_count: int = 0
    mutual_interests: List[str] = []
    relevance_score: float = 0.0
    is_following: bool = False


class RecommendedUsersResponse(BaseModel):
    """Phản hồi người dùng được đề xuất."""

    items: List[RecommendedUser]
    total: int

    class Config:
        from_attributes = True


class SocialSearchParams(BaseModel):
    """Tham số tìm kiếm mạng xã hội."""

    query: str
    user_type: Optional[str] = None  # all, following, followers, suggested
    interests: Optional[List[str]] = None
    location: Optional[str] = None
    min_followers: Optional[int] = None
    max_followers: Optional[int] = None
    sort_by: Optional[str] = "relevance"  # relevance, followers, activity, date_joined
    sort_desc: bool = True
