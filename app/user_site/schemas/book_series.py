from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.user_site.schemas.book import BookResponse


class BookSeriesBase(BaseModel):
    name: str
    description: Optional[str] = None
    cover_image: Optional[str] = None


class BookSeriesCreate(BookSeriesBase):
    pass


class BookSeriesUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cover_image: Optional[str] = None


class BookSeriesItemBase(BaseModel):
    book_id: int
    series_id: int
    position: int


class BookSeriesItemCreate(BookSeriesItemBase):
    pass


class BookSeriesItemResponse(BookSeriesItemBase):
    id: int
    book: Optional[BookResponse] = None

    class Config:
        from_attributes = True


class BookSeriesResponse(BookSeriesBase):
    id: int
    total_books: int
    created_at: datetime
    updated_at: datetime
    is_followed: Optional[bool] = False

    class Config:
        from_attributes = True


class BookSeriesDetailResponse(BookSeriesResponse):
    books: List[BookSeriesItemResponse] = []

    class Config:
        from_attributes = True


class BookSeriesListResponse(BaseModel):
    items: List[BookSeriesResponse]
    total: int
    page: Optional[int] = 1
    size: Optional[int] = 10

    class Config:
        from_attributes = True


class BookSeriesWithBooksResponse(BaseModel):
    """Phản hồi chứa thông tin series cùng danh sách sách đầy đủ"""

    series: BookSeriesResponse
    books: List[BookResponse] = []

    class Config:
        from_attributes = True


class BookSeriesItemListResponse(BaseModel):
    items: List[BookSeriesItemResponse]
    total: int
    page: Optional[int] = 1
    size: Optional[int] = 10

    class Config:
        from_attributes = True


class BookSeriesStatsResponse(BaseModel):
    total_series: int
    total_books_in_series: int
    avg_books_per_series: float
    longest_series_length: int
    longest_series_name: Optional[str] = None
    recent_series: List[BookSeriesResponse] = []
    popular_series: List[BookSeriesResponse] = []

    class Config:
        from_attributes = True
