from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator, HttpUrl
from enum import Enum


class ChapterMediaBase(BaseModel):
    chapter_id: int
    media_type: str = Field(..., description="Loại media: 'image', 'audio', 'video'")
    url: str
    position: int = Field(..., description="Vị trí trong chương")
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None  # Thời lượng (giây) cho audio/video
    alt_text: Optional[str] = None


class ChapterMediaCreate(ChapterMediaBase):
    pass


class ChapterMediaUpdate(BaseModel):
    media_type: Optional[str] = Field(
        None, description="Loại media: 'image', 'audio', 'video'"
    )
    url: Optional[str] = None
    position: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    alt_text: Optional[str] = None


class ChapterMediaResponse(ChapterMediaBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChapterStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SCHEDULED = "scheduled"


class ChapterBase(BaseModel):
    book_id: int
    number: int = Field(..., description="Số thứ tự chương")
    title: str
    subtitle: Optional[str] = None
    is_free: bool = Field(False, description="Có phải chương miễn phí không")
    content: Optional[str] = None
    preview_text: Optional[str] = None
    status: str = Field("draft", description="Trạng thái: draft, published, scheduled")
    scheduled_publish_time: Optional[datetime] = None

    @validator("status")
    def validate_status(cls, v):
        allowed_statuses = ["draft", "published", "scheduled"]
        if v not in allowed_statuses:
            raise ValueError(f'Status must be one of {", ".join(allowed_statuses)}')
        return v


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(ChapterBase):
    title: Optional[str] = None
    number: Optional[int] = None
    scheduled_publish_time: Optional[datetime] = None
    is_published: Optional[bool] = None

    @validator("status")
    def validate_status(cls, v):
        if v is not None:
            allowed_statuses = ["draft", "published", "scheduled"]
            if v not in allowed_statuses:
                raise ValueError(f'Status must be one of {", ".join(allowed_statuses)}')
        return v


class ChapterBriefResponse(BaseModel):
    id: int
    book_id: int
    number: int
    title: str
    subtitle: Optional[str] = None
    is_free: bool
    is_published: bool
    word_count: Optional[int] = None
    estimated_read_time: Optional[int] = None
    view_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChapterResponse(ChapterBriefResponse):
    preview_text: Optional[str] = None
    content: Optional[str] = None
    status: str
    scheduled_publish_time: Optional[datetime] = None
    media: List[ChapterMediaResponse] = []

    class Config:
        from_attributes = True


class ChapterListResponse(BaseModel):
    items: List[ChapterBriefResponse]
    total: int
    has_previous: bool
    has_next: bool
    page: Optional[int] = 1
    size: Optional[int] = 10


class ChapterStatsResponse(BaseModel):
    total_chapters: int
    published_chapters: int
    draft_chapters: int
    scheduled_chapters: int
    chapters_by_book: Dict[str, int] = {}
    avg_word_count: float = 0
    avg_read_time: float = 0
    most_viewed_chapters: List[ChapterBriefResponse] = []
    recently_published: List[ChapterBriefResponse] = []
    scheduled_for_publication: List[ChapterBriefResponse] = []

    class Config:
        from_attributes = True


class ChapterDetailResponse(ChapterResponse):
    previous_chapter: Optional[ChapterBriefResponse] = None
    next_chapter: Optional[ChapterBriefResponse] = None
    comments_count: int = 0
    reading_position: Optional[float] = None
    is_bookmarked: bool = False

    class Config:
        from_attributes = True


class ChapterContentResponse(BaseModel):
    id: int
    book_id: int
    number: int
    title: str
    content: str
    is_encrypted: bool = False
    word_count: Optional[int] = None
    estimated_read_time: Optional[int] = None
    media: List[ChapterMediaResponse] = []

    class Config:
        from_attributes = True


# Chapter Comment Schemas
class ChapterCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    position: Optional[float] = Field(
        None, description="Vị trí trong chương (phần trăm)"
    )
    parent_id: Optional[int] = Field(
        None, description="ID của bình luận cha (nếu là trả lời)"
    )


class ChapterCommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class ChapterCommentResponse(BaseModel):
    id: int
    chapter_id: int
    user_id: int
    content: str
    position: Optional[float] = None
    parent_id: Optional[int] = None
    likes_count: int = 0
    created_at: datetime
    updated_at: datetime
    user: Dict[str, Any] = {}
    replies: List = []
    reply_count: int = 0
    is_liked: bool = False

    class Config:
        from_attributes = True


# Chapter Reading Position Schema
class ChapterReadingPosition(BaseModel):
    position: float = Field(..., ge=0, le=100, description="Vị trí đọc (0-100%)")


class ChapterProgressResponse(BaseModel):
    id: int
    user_id: int
    chapter_id: int
    book_id: int
    position: float
    completed: bool
    last_read_at: datetime

    class Config:
        from_attributes = True
