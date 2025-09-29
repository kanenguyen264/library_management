from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AchievementBase(BaseModel):
    achievement_id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    earned_at: datetime


class AchievementResponse(AchievementBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class AchievementListResponse(BaseModel):
    items: List[AchievementResponse]
    total: int

    class Config:
        from_attributes = True


class AchievementProgressResponse(BaseModel):
    """Phản hồi về tiến độ đạt được thành tích."""

    achievement_id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    current_progress: int
    target_progress: int
    completed: bool
    earned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AchievementCategoryResponse(BaseModel):
    """Phản hồi thông tin về danh mục thành tích."""

    id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    achievements_count: Optional[int] = 0

    class Config:
        from_attributes = True


class AchievementTrackRequest(BaseModel):
    """Yêu cầu theo dõi tiến trình thành tích."""

    action_type: str = Field(
        ..., description="Loại hành động (book_read, chapter_completed, etc.)"
    )
    action_value: int = Field(
        ge=0, description="Giá trị của hành động (số trang, số chương, etc.)"
    )
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class AchievementCreate(AchievementBase):
    pass

    class Config:
        from_attributes = True


class AchievementUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[Dict[str, Any]] = None
    badge_image_url: Optional[str] = None
    points: Optional[int] = None
    achievement_type: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        from_attributes = True


class Achievement(AchievementBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool

    class Config:
        from_attributes = True
