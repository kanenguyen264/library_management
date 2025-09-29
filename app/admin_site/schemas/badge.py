from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
from datetime import datetime


class BadgeBase(BaseModel):
    """Schema cơ bản cho Badge."""

    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    criteria: Optional[str] = None
    badge_type: str
    is_featured: bool = False
    is_active: bool = True


class BadgeCreate(BadgeBase):
    """Schema tạo mới Badge."""

    @validator("badge_type")
    def validate_badge_type(cls, v):
        """Kiểm tra loại huy hiệu hợp lệ."""
        valid_types = ["achievement", "reward", "special", "milestone", "seasonal"]
        if v not in valid_types:
            raise ValueError(
                f"Loại huy hiệu phải là một trong: {', '.join(valid_types)}"
            )
        return v


class BadgeUpdate(BaseModel):
    """Schema cập nhật Badge."""

    name: Optional[str] = None
    description: Optional[str] = None
    icon_url: Optional[str] = None
    criteria: Optional[str] = None
    badge_type: Optional[str] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None

    @validator("badge_type")
    def validate_badge_type(cls, v):
        """Kiểm tra loại huy hiệu hợp lệ."""
        if v is None:
            return v

        valid_types = ["achievement", "reward", "special", "milestone", "seasonal"]
        if v not in valid_types:
            raise ValueError(
                f"Loại huy hiệu phải là một trong: {', '.join(valid_types)}"
            )
        return v


class BadgeInDB(BadgeBase):
    """Schema Badge trong database."""

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BadgeInfo(BadgeInDB):
    """Schema thông tin Badge."""

    class Config:
        from_attributes = True
