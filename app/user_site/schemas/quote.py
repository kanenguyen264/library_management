from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, validator
from app.user_site.schemas.book import BookBriefResponse
from app.user_site.schemas.user import UserPublicResponse


class QuoteBase(BaseModel):
    book_id: int
    chapter_id: Optional[int] = None
    content: str
    start_offset: Optional[str] = None
    end_offset: Optional[str] = None
    is_public: bool = True


class QuoteCreate(QuoteBase):
    pass


class QuoteUpdate(BaseModel):
    content: Optional[str] = None
    start_offset: Optional[str] = None
    end_offset: Optional[str] = None
    is_public: Optional[bool] = None


class QuoteResponse(QuoteBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    likes_count: int = 0
    shares_count: int = 0
    user: Optional[UserPublicResponse] = None
    book: Optional[BookBriefResponse] = None
    is_liked: Optional[bool] = None

    class Config:
        from_attributes = True


class QuoteListResponse(BaseModel):
    items: List[QuoteResponse]
    total: int

    class Config:
        from_attributes = True


class QuoteLikeCreate(BaseModel):
    quote_id: int


class QuoteLikeResponse(BaseModel):
    id: int
    quote_id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class QuoteExportFormat(str, Enum):
    """Định dạng xuất trích dẫn."""

    TEXT = "text"
    HTML = "html"
    MARKDOWN = "markdown"
    IMAGE = "image"
    PDF = "pdf"


class BulkQuoteOperation(str, Enum):
    """Hoạt động hàng loạt trên trích dẫn."""

    DELETE = "delete"
    MAKE_PUBLIC = "make_public"
    MAKE_PRIVATE = "make_private"
    ADD_TO_COLLECTION = "add_to_collection"
    REMOVE_FROM_COLLECTION = "remove_from_collection"


class QuotePublicResponse(BaseModel):
    """Schema cho trích dẫn công khai."""

    id: int
    content: str
    book_title: str
    book_id: int
    user_name: str
    user_id: int
    created_at: datetime
    likes_count: int = 0
    shares_count: int = 0
    book_cover: Optional[str] = None
    author_name: Optional[str] = None

    class Config:
        from_attributes = True


class QuoteSearchParams(BaseModel):
    """Tham số tìm kiếm trích dẫn."""

    query: Optional[str] = None
    book_id: Optional[int] = None
    user_id: Optional[int] = None
    tag: Optional[str] = None
    is_public: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sort_by: Optional[str] = "created_at"
    sort_desc: bool = True


class QuoteStats(BaseModel):
    """Thống kê trích dẫn."""

    total_count: int = 0
    public_count: int = 0
    private_count: int = 0
    likes_received: int = 0
    shares_count: int = 0
    books_quoted: int = 0
    top_books: List[Dict[str, Any]] = []
    quotes_by_month: Dict[str, int] = {}


class QuoteStatsResponse(BaseModel):
    """Phản hồi thống kê trích dẫn."""

    stats: QuoteStats
    user_id: int

    class Config:
        from_attributes = True


class QuoteShareResponse(BaseModel):
    """Phản hồi chia sẻ trích dẫn."""

    success: bool
    share_url: Optional[str] = None
    share_image: Optional[str] = None
    platform: str
    message: Optional[str] = None

    class Config:
        from_attributes = True


class QuoteReportCreate(BaseModel):
    """Tạo báo cáo trích dẫn không phù hợp."""

    quote_id: int
    reason: str
    details: Optional[str] = None


class QuoteCollectionCreate(BaseModel):
    """Tạo bộ sưu tập trích dẫn."""

    name: str
    description: Optional[str] = None
    is_public: bool = True
    quote_ids: Optional[List[int]] = None


class QuoteCollectionResponse(BaseModel):
    """Phản hồi bộ sưu tập trích dẫn."""

    id: int
    name: str
    description: Optional[str] = None
    is_public: bool
    user_id: int
    created_at: datetime
    updated_at: datetime
    quotes_count: int = 0
    user: Optional[UserPublicResponse] = None

    class Config:
        from_attributes = True


class QuoteCollectionListResponse(BaseModel):
    """Danh sách bộ sưu tập trích dẫn."""

    items: List[QuoteCollectionResponse]
    total: int

    class Config:
        from_attributes = True
