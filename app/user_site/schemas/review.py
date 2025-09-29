from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = None
    comment: str = Field(..., min_length=10)
    is_spoiler: bool = False
    is_verified_purchase: bool = False
    is_approved: bool = True


class ReviewCreate(ReviewBase):
    book_id: int


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    title: Optional[str] = None
    comment: Optional[str] = Field(None, min_length=10)
    is_spoiler: Optional[bool] = None


class UserBrief(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class BookBrief(BaseModel):
    id: int
    title: str
    cover_thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


class ReviewResponse(ReviewBase):
    id: int
    user_id: int
    book_id: int
    likes_count: int
    reports_count: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserBrief] = None
    book: Optional[BookBrief] = None
    is_liked: Optional[bool] = None  # Được thêm bởi service

    class Config:
        from_attributes = True


class ReviewBriefResponse(BaseModel):
    id: int
    rating: int
    title: Optional[str] = None
    comment: str
    user_id: int
    book_id: int
    likes_count: int
    created_at: datetime
    user: Optional[UserBrief] = None

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    items: List[ReviewResponse]
    total: int
    page: Optional[int] = 1
    size: Optional[int] = 10

    class Config:
        from_attributes = True


class ReportReviewRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class ReviewLikeCreate(BaseModel):
    review_id: int


class ReviewReportBase(BaseModel):
    reason: str = Field(..., min_length=5, max_length=100)
    description: Optional[str] = None


class ReviewReportCreate(ReviewReportBase):
    review_id: int


class ReviewReportUpdate(BaseModel):
    status: str = Field(..., description="Trạng thái: pending, approved, rejected")
    resolved_by: Optional[int] = None


class ReviewReportResponse(ReviewReportBase):
    id: int
    review_id: int
    reporter_id: int
    status: str
    resolved_by: Optional[int] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    reporter: Optional[UserBrief] = None
    review: Optional[ReviewResponse] = None

    class Config:
        from_attributes = True


class ReviewStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FLAGGED = "flagged"
    REMOVED = "removed"


class ReviewLikeResponse(BaseModel):
    id: int
    user_id: int
    review_id: int
    created_at: datetime
    user: Optional[UserBrief] = None

    class Config:
        from_attributes = True


class ReviewStatsResponse(BaseModel):
    total_reviews: int
    average_rating: float
    rating_distribution: Dict[int, int] = {}  # Map of rating -> count
    reviews_by_status: Dict[str, int] = {}
    recent_reviews: List[ReviewResponse] = []
    most_liked_reviews: List[ReviewResponse] = []
    most_active_reviewers: List[Dict[str, Any]] = []
    reviews_over_time: Dict[str, int] = {}  # Map of date -> count

    class Config:
        from_attributes = True


class ReviewBulkActionRequest(BaseModel):
    review_ids: List[int]
    action: str = Field(..., description="Action: delete, approve, reject, flag")
    reason: Optional[str] = None

    @validator("action")
    def validate_action(cls, v):
        valid_actions = ["delete", "approve", "reject", "flag"]
        if v not in valid_actions:
            raise ValueError(f"Action must be one of: {', '.join(valid_actions)}")
        return v
