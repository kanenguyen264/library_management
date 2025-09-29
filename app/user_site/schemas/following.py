from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.user_site.schemas.user import UserPublicResponse


class FollowingBase(BaseModel):
    following_id: int


class FollowingCreate(FollowingBase):
    pass


class FollowResponse(BaseModel):
    success: bool
    message: str
    user_id: int


class FollowingResponse(BaseModel):
    follower_id: int
    following_id: int
    follower: Optional[UserPublicResponse] = None
    following: Optional[UserPublicResponse] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FollowerResponse(BaseModel):
    follower_id: int
    following_id: int
    follower: Optional[UserPublicResponse] = None
    following: Optional[UserPublicResponse] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FollowingListResponse(BaseModel):
    items: List[FollowingResponse]
    total: int

    class Config:
        from_attributes = True


class FollowerListResponse(BaseModel):
    items: List[FollowerResponse]
    total: int

    class Config:
        from_attributes = True


class SuggestedUserResponse(BaseModel):
    user: UserPublicResponse
    common_followers: int = 0
    common_interests: int = 0
    relevance_score: float = 0.0

    class Config:
        from_attributes = True


class FollowStatsResponse(BaseModel):
    following_count: int
    followers_count: int
    mutual_count: int = 0

    class Config:
        from_attributes = True


class UserNetworkResponse(BaseModel):
    user: UserPublicResponse
    is_following: bool = False
    is_follower: bool = False
    common_followers: int = 0
    common_following: int = 0

    class Config:
        from_attributes = True


class FollowSuggestionResponse(BaseModel):
    items: List[SuggestedUserResponse]
    generated_at: datetime

    class Config:
        from_attributes = True


class FollowActivityResponse(BaseModel):
    items: List[Any]
    days: int
    generated_at: datetime

    class Config:
        from_attributes = True


class FollowNotificationSettings(BaseModel):
    new_follower_notifications: bool = True
    follow_request_notifications: bool = True
    follow_activity_summary: bool = True
    email_notifications: bool = False

    class Config:
        from_attributes = True
