from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from app.user_site.schemas.book import BookBrief, BookBriefResponse


class RecommendationTypeEnum(str, Enum):
    """Loại đề xuất."""

    PERSONALIZED = "personalized"
    SIMILAR = "similar"
    TRENDING = "trending"
    NEW_RELEASE = "new_release"
    EDITOR_PICK = "editor_pick"
    AUTHOR_BASED = "author_based"
    GENRE_BASED = "genre_based"
    TAG_BASED = "tag_based"
    FRIEND_READ = "friend_read"
    CONTINUE_READING = "continue_reading"


class RecommendationSourceType(str, Enum):
    """Nguồn của đề xuất."""

    SYSTEM = "system"
    EDITOR = "editor"
    USER = "user"
    AI = "ai"


class ReadingRecommendationBase(BaseModel):
    book_id: int
    recommendation_type: str
    confidence_score: float = 0.0
    is_dismissed: bool = False


class ReadingRecommendationCreate(ReadingRecommendationBase):
    pass


class ReadingRecommendationUpdate(BaseModel):
    recommendation_type: Optional[str] = None
    confidence_score: Optional[float] = None
    is_dismissed: Optional[bool] = None


class ReadingRecommendationResponse(ReadingRecommendationBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    book: Optional[BookBrief] = None

    class Config:
        from_attributes = True


class ReadingRecommendationListResponse(BaseModel):
    items: List[ReadingRecommendationResponse]
    total: int

    class Config:
        from_attributes = True


class RecommendationResponse(BaseModel):
    """Phản hồi đề xuất đọc."""

    id: int
    user_id: int
    book_id: int
    book: Optional[BookBriefResponse] = None
    recommendation_type: RecommendationTypeEnum
    confidence_score: float
    source: RecommendationSourceType = RecommendationSourceType.SYSTEM
    is_read: bool = False
    is_saved: bool = False
    is_dismissed: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class RecommendationListResponse(BaseModel):
    """Danh sách đề xuất đọc."""

    items: List[RecommendationResponse]
    total: int

    class Config:
        from_attributes = True


class RecommendationEngineResponse(BaseModel):
    """Phản hồi từ engine đề xuất."""

    recommendations: List[RecommendationResponse]
    engine_type: str
    processing_time: float  # Thời gian xử lý (giây)
    parameters: Dict[str, Any] = {}

    class Config:
        from_attributes = True


class RecommendationPreferences(BaseModel):
    """Tùy chọn đề xuất của người dùng."""

    enable_recommendations: bool = True
    preferred_genres: List[int] = []
    excluded_genres: List[int] = []
    preferred_authors: List[int] = []
    excluded_authors: List[int] = []
    preferred_tags: List[str] = []
    excluded_tags: List[str] = []
    recommendation_frequency: str = "daily"  # daily, weekly, monthly
    max_recommendations: int = 10
    content_maturity: List[str] = ["general", "teen"]  # general, teen, adult


class RecommendationFeedbackRequest(BaseModel):
    """Yêu cầu phản hồi về đề xuất."""

    recommendation_id: int
    feedback_type: str  # like, dislike, neutral, save, dismiss
    comment: Optional[str] = None


class RecommendationFeedbackCreate(BaseModel):
    """Tạo phản hồi về đề xuất."""

    recommendation_id: int
    user_id: int
    rating: int  # 1-5
    feedback_type: str
    comment: Optional[str] = None


class RecommendationExploreResponse(BaseModel):
    """Phản hồi khám phá đề xuất."""

    recommendations: List[RecommendationResponse]
    categories: List[Dict[str, Any]]
    trending_tags: List[Dict[str, Any]]
    collections: List[Dict[str, Any]]

    class Config:
        from_attributes = True


class RecommendationCollectionResponse(BaseModel):
    """Phản hồi bộ sưu tập đề xuất."""

    id: int
    name: str
    description: Optional[str] = None
    cover_image: Optional[str] = None
    recommendations: List[RecommendationResponse]
    recommendation_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RecommendationInsightResponse(BaseModel):
    """Phản hồi phân tích sâu về đề xuất."""

    user_id: int
    reading_trends: Dict[str, Any]
    genre_preferences: List[Dict[str, Any]]
    author_preferences: List[Dict[str, Any]]
    tag_preferences: List[Dict[str, Any]]
    reading_patterns: Dict[str, Any]
    similar_users: List[Dict[str, Any]]

    class Config:
        from_attributes = True


class RecommendationHistoryResponse(BaseModel):
    """Phản hồi lịch sử đề xuất."""

    items: List[RecommendationResponse]
    total: int
    interaction_stats: Dict[str, int]

    class Config:
        from_attributes = True


class RecommendationFilterParams(BaseModel):
    """Tham số lọc đề xuất."""

    recommendation_type: Optional[List[RecommendationTypeEnum]] = None
    source: Optional[List[RecommendationSourceType]] = None
    min_confidence: Optional[float] = None
    max_confidence: Optional[float] = None
    genre_ids: Optional[List[int]] = None
    author_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None
    is_read: Optional[bool] = None
    is_saved: Optional[bool] = None
    is_dismissed: Optional[bool] = None
    sort_by: Optional[str] = "confidence_score"
    sort_desc: bool = True


class PersonalizedRecommendationResponse(BaseModel):
    """Phản hồi đề xuất cá nhân hóa."""

    recommendations: List[RecommendationResponse]
    personalization_factors: Dict[str, Any]
    explanation: Dict[str, Any]

    class Config:
        from_attributes = True
