from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from app.user_site.schemas.book import BookBrief
from app.user_site.schemas.user import UserPublicResponse


class SearchFilter(BaseModel):
    """Filter cho kết quả tìm kiếm."""

    resource_types: Optional[List[str]] = None  # books, authors, users, tags, etc.
    genres: Optional[List[int]] = None
    tags: Optional[List[str]] = None
    publication_years: Optional[List[int]] = None
    languages: Optional[List[str]] = None
    rating_min: Optional[float] = None
    rating_max: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    is_free: Optional[bool] = None
    is_premium: Optional[bool] = None
    sort_by: Optional[str] = "relevance"  # relevance, date, title, rating, popularity
    sort_direction: Optional[str] = "desc"  # asc, desc


class SearchResponse(BaseModel):
    """Phản hồi kết quả tìm kiếm."""

    query: str
    total_results: int
    books: List[BookBrief] = []
    users: List[UserPublicResponse] = []
    tags: List[Dict[str, Any]] = []
    authors: List[Dict[str, Any]] = []
    publishers: List[Dict[str, Any]] = []
    processing_time: float  # Thời gian xử lý (giây)
    filters_applied: Dict[str, Any] = {}
    facets: Dict[str, List[Dict[str, Any]]] = {}

    class Config:
        from_attributes = True


class SearchAllResponse(BaseModel):
    """Phản hồi kết quả tìm kiếm tất cả."""

    query: str
    total_results: int
    results_by_type: Dict[str, List[Any]] = {}
    processing_time: float

    class Config:
        from_attributes = True


class SearchSuggestionResponse(BaseModel):
    """Phản hồi gợi ý tìm kiếm."""

    query: str
    suggestions: List[str] = []
    popular_searches: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True


class AdvancedSearchParams(BaseModel):
    """Tham số tìm kiếm nâng cao."""

    query: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    isbn: Optional[str] = None
    publisher: Optional[str] = None
    genre_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None
    language: Optional[str] = None
    publication_year_min: Optional[int] = None
    publication_year_max: Optional[int] = None
    rating_min: Optional[float] = None
    rating_max: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    is_free: Optional[bool] = None
    has_audio: Optional[bool] = None
    is_premium: Optional[bool] = None
    date_added_min: Optional[datetime] = None
    date_added_max: Optional[datetime] = None
    sort_by: str = "relevance"
    sort_direction: str = "desc"
    page: int = 1
    page_size: int = 20


class SearchHistoryCreate(BaseModel):
    """Tạo lịch sử tìm kiếm."""

    user_id: int
    query: str
    resource_type: Optional[str] = None
    filters_applied: Optional[Dict[str, Any]] = None
    results_count: int = 0


class SearchHistoryResponse(BaseModel):
    """Phản hồi lịch sử tìm kiếm."""

    id: int
    user_id: int
    query: str
    resource_type: Optional[str] = None
    filters_applied: Optional[Dict[str, Any]] = None
    results_count: int
    created_at: datetime

    class Config:
        from_attributes = True
