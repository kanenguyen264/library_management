from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class BadgeBase(BaseModel):
    badge_id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    earned_at: datetime


class BadgeResponse(BadgeBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class BadgeListResponse(BaseModel):
    items: List[BadgeResponse]
    total: int

    class Config:
        from_attributes = True


class BadgeCollectionResponse(BaseModel):
    """
    Schema response cho bộ sưu tập huy hiệu.
    """

    items: List[BadgeResponse]
    total: int
    earned_count: int
    completion_percentage: float

    class Config:
        from_attributes = True


class BadgeLeaderboardEntry(BaseModel):
    """
    Entry đơn lẻ trong bảng xếp hạng huy hiệu.
    """

    user_id: int
    username: str
    avatar_url: Optional[str] = None
    badge_count: int
    rank: int

    class Config:
        from_attributes = True


class BadgeLeaderboardResponse(BaseModel):
    """
    Schema response cho bảng xếp hạng huy hiệu.
    """

    items: List[BadgeLeaderboardEntry]
    total: int
    user_rank: Optional[int] = None  # Xếp hạng của người dùng hiện tại, nếu có

    class Config:
        from_attributes = True


class BadgeDisplayUpdate(BaseModel):
    """
    Schema cho việc cập nhật cách hiển thị huy hiệu.
    """

    display_order: Optional[List[int]] = None  # Thứ tự hiển thị các badge theo ID
    visible_badges: Optional[List[int]] = (
        None  # Danh sách ID của các huy hiệu được hiển thị
    )
    hidden_badges: Optional[List[int]] = None  # Danh sách ID của các huy hiệu bị ẩn
    favorite_badges: Optional[List[int]] = (
        None  # Danh sách ID của các huy hiệu được yêu thích
    )
    display_preferences: Optional[Dict[str, Any]] = Field(
        default_factory=dict
    )  # Tùy chọn hiển thị khác


class BadgeSearchParams(BaseModel):
    """
    Schema cho tham số tìm kiếm huy hiệu.
    """

    query: Optional[str] = None  # Từ khóa tìm kiếm
    category: Optional[str] = None  # Danh mục huy hiệu
    status: Optional[str] = None  # Trạng thái (earned, locked, etc.)
    sort_by: Optional[str] = Field("earned_at", description="Sắp xếp theo trường")
    sort_desc: bool = Field(True, description="Sắp xếp giảm dần")
    skip: int = Field(0, ge=0, description="Số lượng bỏ qua")
    limit: int = Field(20, ge=1, le=100, description="Số lượng lấy")
