from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class BookmarkBase(BaseModel):
    position_offset: str
    title: Optional[str] = None
    note: Optional[str] = None
    color: Optional[str] = None


class BookmarkCreate(BookmarkBase):
    book_id: int
    chapter_id: Optional[int] = None


class BookmarkUpdate(BaseModel):
    position_offset: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    color: Optional[str] = None


class BookBrief(BaseModel):
    id: int
    title: str
    cover_thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


class ChapterBrief(BaseModel):
    id: int
    title: str
    number: int

    class Config:
        from_attributes = True


class BookmarkResponse(BookmarkBase):
    id: int
    user_id: int
    book_id: int
    chapter_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    book: Optional[BookBrief] = None
    chapter: Optional[ChapterBrief] = None

    class Config:
        from_attributes = True


class BookmarkListResponse(BaseModel):
    items: List[BookmarkResponse]
    total: int
    page: Optional[int] = 1
    limit: Optional[int] = 20
    total_pages: Optional[int] = 1


class BookmarkSearchParams(BaseModel):
    """Tham số tìm kiếm nâng cao cho bookmark"""

    query: Optional[str] = None
    book_id: Optional[int] = None
    chapter_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_favorite: Optional[bool] = None
    has_notes: Optional[bool] = None
    color: Optional[str] = None
    page: int = 1
    limit: int = 20
    sort_by: str = "created_at"
    sort_desc: bool = True


class BookmarkStatsResponse(BaseModel):
    """Phản hồi thống kê bookmark của người dùng"""

    total_bookmarks: int
    favorite_bookmarks: int
    books_with_bookmarks: int
    recent_bookmarks: List[BookmarkResponse]
    bookmarks_by_color: dict

    class Config:
        from_attributes = True


class BookmarkHistoryResponse(BaseModel):
    """Phản hồi lịch sử hoạt động bookmark của người dùng"""

    created_count: int
    accessed_count: int
    deleted_count: int
    daily_activity: dict
    most_active_books: List[dict]

    class Config:
        from_attributes = True
