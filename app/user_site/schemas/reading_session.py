from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
from pydantic import BaseModel, Field, validator
from app.user_site.schemas.book import BookBriefResponse


class ReadingSessionBase(BaseModel):
    book_id: int
    chapter_id: Optional[int] = None
    start_position: Optional[str] = None
    end_position: Optional[str] = None
    duration_seconds: int
    pages_read: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    device_info: Optional[str] = None
    ip_address: Optional[str] = None
    notes: Optional[str] = None

    @validator("end_time", pre=True, always=True)
    def set_end_time(cls, v, values):
        if v:
            return v
        if "start_time" in values and "duration_seconds" in values:
            start = values["start_time"]
            duration = values["duration_seconds"]
            return start + datetime.timedelta(seconds=duration)
        return v


class ReadingSessionCreate(ReadingSessionBase):
    pass


class ReadingSessionUpdate(BaseModel):
    end_position: Optional[str] = None
    duration_seconds: Optional[int] = None
    pages_read: Optional[int] = None
    end_time: Optional[datetime] = None
    notes: Optional[str] = None


class ReadingSessionResponse(ReadingSessionBase):
    id: int
    user_id: int
    book: Optional[BookBriefResponse] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReadingSessionListResponse(BaseModel):
    items: List[ReadingSessionResponse]
    total: int

    class Config:
        from_attributes = True


class ReadingStatsItem(BaseModel):
    date: date
    minutes_read: int
    pages_read: Optional[int] = None
    books_count: int


class ReadingStatsResponse(BaseModel):
    stats: List[ReadingStatsItem]
    total_minutes: int
    total_pages: Optional[int] = None
    total_books: int
    average_minutes_per_day: float
    longest_streak_days: int
    current_streak_days: int

    class Config:
        from_attributes = True


class ReadingGoalCreate(BaseModel):
    """Schema tạo mục tiêu đọc sách."""

    goal_type: str  # books, pages, minutes, chapters
    target_value: int
    start_date: datetime = Field(default_factory=datetime.now)
    end_date: datetime
    book_ids: Optional[List[int]] = None
    is_public: bool = False
    reminder_enabled: bool = True
    reminder_time: Optional[str] = None  # HH:MM format
    description: Optional[str] = None


class ReadingGoalResponse(BaseModel):
    """Phản hồi mục tiêu đọc sách."""

    id: int
    user_id: int
    goal_type: str
    target_value: int
    current_value: int = 0
    start_date: datetime
    end_date: datetime
    book_ids: List[int] = []
    is_public: bool
    is_completed: bool = False
    completion_date: Optional[datetime] = None
    progress_percentage: float = 0.0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReadingGoalUpdate(BaseModel):
    """Cập nhật mục tiêu đọc sách."""

    target_value: Optional[int] = None
    end_date: Optional[datetime] = None
    book_ids: Optional[List[int]] = None
    is_public: Optional[bool] = None
    reminder_enabled: Optional[bool] = None
    reminder_time: Optional[str] = None
    description: Optional[str] = None


class ReadingSessionSearchParams(BaseModel):
    """Tham số tìm kiếm phiên đọc."""

    book_id: Optional[int] = None
    user_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_duration: Optional[int] = None  # Thời gian tối thiểu (phút)
    max_duration: Optional[int] = None  # Thời gian tối đa (phút)
    device_type: Optional[str] = None
    sort_by: Optional[str] = "start_time"
    sort_desc: bool = True


class ReadingSessionBatchUpdate(BaseModel):
    """Cập nhật hàng loạt phiên đọc."""

    session_ids: List[int]
    book_id: Optional[int] = None
    duration: Optional[int] = None
    pages_read: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    notes: Optional[str] = None
    device_type: Optional[str] = None


class ReadingDeviceStats(BaseModel):
    """Thống kê thiết bị đọc."""

    device_id: str
    device_name: str
    device_type: str
    total_sessions: int = 0
    total_time: int = 0  # Tổng thời gian đọc (phút)
    total_pages: int = 0  # Tổng số trang đã đọc
    average_session_time: float = 0.0  # Thời gian trung bình mỗi phiên (phút)
    last_used: Optional[datetime] = None
    first_used: Optional[datetime] = None

    class Config:
        from_attributes = True
