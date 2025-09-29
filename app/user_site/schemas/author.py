from typing import Optional, List, Dict, Any, ForwardRef
from datetime import date, datetime
from pydantic import BaseModel, Field, HttpUrl


# Định nghĩa lại BookBrief để tránh import vòng tròn
class BookBriefBase(BaseModel):
    """
    Schema tóm tắt cho sách (định nghĩa trong author.py).
    """

    id: int
    title: str
    cover_thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


# Sử dụng ForwardRef cho các reference type
BookBrief = ForwardRef("BookBrief")


class AuthorBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    biography: Optional[str] = None
    photo_url: Optional[str] = None
    website: Optional[str] = None
    birthdate: Optional[date] = None
    country: Optional[str] = None
    social_media_links: Optional[Dict[str, Any]] = None


class AuthorCreate(AuthorBase):
    pass


class AuthorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    biography: Optional[str] = None
    photo_url: Optional[str] = None
    website: Optional[str] = None
    birthdate: Optional[date] = None
    country: Optional[str] = None
    social_media_links: Optional[Dict[str, Any]] = None


class AuthorBrief(BaseModel):
    id: int
    name: str
    photo_url: Optional[str] = None

    class Config:
        from_attributes = True


class AuthorResponse(AuthorBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AuthorDetailResponse(AuthorResponse):
    books: List[BookBriefBase] = []

    class Config:
        from_attributes = True


class AuthorListResponse(BaseModel):
    items: List[AuthorResponse]
    total: int


class AuthorStatsResponse(BaseModel):
    """Schema thống kê về tác giả."""

    author_id: int
    name: str
    total_books: int
    total_reviews: int
    average_rating: float
    most_popular_book: Optional[BookBriefBase] = None
    total_readers: int
    total_views: int
    country_distribution: Optional[Dict[str, int]] = None
    genre_distribution: Optional[Dict[str, int]] = None

    class Config:
        from_attributes = True


class AuthorWithBooksResponse(BaseModel):
    """Schema phản hồi tác giả với danh sách sách."""

    id: int
    name: str
    biography: Optional[str] = None
    photo_url: Optional[str] = None
    website: Optional[str] = None
    birthdate: Optional[date] = None
    country: Optional[str] = None
    books: List[BookBriefBase] = []
    books_count: int
    average_rating: Optional[float] = None

    class Config:
        from_attributes = True
