from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")  # Hex color code


class TagCreate(TagBase):
    pass


class TagUpdate(TagBase):
    name: Optional[str] = Field(None, min_length=1, max_length=50)


class TagResponse(TagBase):
    id: int
    book_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TagInfo(TagResponse):
    is_active: bool = True

    class Config:
        from_attributes = True


class TagListResponse(BaseModel):
    items: List[TagResponse]
    total: int


class TagList(BaseModel):
    items: List[TagInfo]
    total: int
    page: int
    size: int
    pages: int


class TagBrief(BaseModel):
    id: int
    name: str
    slug: str
    color: Optional[str] = None

    class Config:
        from_attributes = True


class TagWithBooks(TagResponse):
    books: List["BookBrief"] = []

    class Config:
        from_attributes = True


class BookBrief(BaseModel):
    id: int
    title: str
    cover_thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


class TagBulkResponse(BaseModel):
    """Phản hồi hàng loạt tag."""

    successful: List[TagResponse]
    failed: List[Dict[str, Any]]
    total: int

    class Config:
        from_attributes = True


class TagStats(BaseModel):
    """Thống kê tag."""

    total_books: int = 0
    total_users: int = 0
    average_rating: float = 0.0
    popularity_score: float = 0.0
    usage_by_month: Dict[str, int] = {}
    related_tags: List[Dict[str, Any]] = []


class TagStatsResponse(BaseModel):
    """Phản hồi thống kê tag."""

    tag_id: int
    name: str
    stats: TagStats

    class Config:
        from_attributes = True


class TagTrending(BaseModel):
    """Trend tag."""

    tag: TagResponse
    change_percentage: float
    rank: int
    previous_rank: Optional[int] = None


class TagTrendingResponse(BaseModel):
    """Phản hồi trend tag."""

    items: List[TagTrending]
    period: str  # day, week, month
    total: int

    class Config:
        from_attributes = True


class TagSearchParams(BaseModel):
    """Tham số tìm kiếm tag."""

    query: Optional[str] = None
    category_id: Optional[int] = None
    min_books: Optional[int] = None
    max_books: Optional[int] = None
    sort_by: Optional[str] = "popularity"  # popularity, name, books_count
    sort_desc: bool = True
    is_active: Optional[bool] = None
