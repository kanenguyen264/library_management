from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ReadingHistoryBase(BaseModel):
    progress_percentage: Optional[float] = Field(0.0, ge=0, le=100)
    last_position: Optional[str] = None
    time_spent_seconds: Optional[int] = 0
    is_completed: bool = False


class ReadingHistoryCreate(ReadingHistoryBase):
    book_id: int
    chapter_id: Optional[int] = None


class ReadingHistoryUpdate(BaseModel):
    chapter_id: Optional[int] = None
    progress_percentage: Optional[float] = Field(None, ge=0, le=100)
    last_position: Optional[str] = None
    time_spent_seconds: Optional[int] = None
    is_completed: Optional[bool] = None


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


class ReadingHistoryResponse(ReadingHistoryBase):
    id: int
    user_id: int
    book_id: int
    chapter_id: Optional[int] = None
    last_read_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    book: Optional[BookBrief] = None
    chapter: Optional[ChapterBrief] = None

    class Config:
        from_attributes = True


class ReadingHistoryListResponse(BaseModel):
    items: List[ReadingHistoryResponse]
    total: int


class ReadingHistoryStats(BaseModel):
    """Thống kê lịch sử đọc."""

    total_reading_time: int = 0  # Tổng thời gian đọc (phút)
    total_pages_read: int = 0  # Tổng số trang đã đọc
    total_books_read: int = 0  # Tổng số sách đã đọc
    total_books_completed: int = 0  # Tổng số sách đã hoàn thành
    reading_days: int = 0  # Số ngày đọc sách
    average_time_per_day: float = 0.0  # Thời gian đọc trung bình mỗi ngày (phút)
    average_time_per_session: float = 0.0  # Thời gian đọc trung bình mỗi phiên (phút)
    average_pages_per_day: float = 0.0  # Số trang đọc trung bình mỗi ngày
    longest_streak: int = 0  # Chuỗi ngày đọc dài nhất
    current_streak: int = 0  # Chuỗi ngày đọc hiện tại
    daily_reading: Dict[str, int] = {}  # Thời gian đọc theo ngày
    weekly_reading: Dict[str, int] = {}  # Thời gian đọc theo tuần
    monthly_reading: Dict[str, int] = {}  # Thời gian đọc theo tháng

    class Config:
        from_attributes = True


class ReadingHistorySearchParams(BaseModel):
    """Tham số tìm kiếm lịch sử đọc."""

    book_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None  # in_progress, completed, abandoned
    min_progress: Optional[float] = None  # Tối thiểu phần trăm hoàn thành
    max_progress: Optional[float] = None  # Tối đa phần trăm hoàn thành
    sort_by: Optional[str] = "last_read_at"
    sort_desc: bool = True


class ReadingHistorySyncRequest(BaseModel):
    """Yêu cầu đồng bộ lịch sử đọc."""

    device_id: str
    user_id: int
    items: List[Dict[str, Any]]
    sync_time: datetime = Field(default_factory=datetime.now)
    last_sync_time: Optional[datetime] = None
    force_sync: bool = False


class ReadingProgressReport(BaseModel):
    """Báo cáo tiến độ đọc."""

    daily_stats: Dict[str, Any]
    weekly_stats: Dict[str, Any]
    monthly_stats: Dict[str, Any]
    books_completed: int
    total_time_spent: int  # Phút
    pages_read: int
    current_streak: int
    longest_streak: int
    top_books: List[Dict[str, Any]]
    reading_speed: Optional[float] = None  # Tốc độ đọc (trang/phút)
    time_of_day: Dict[str, int]  # Thời gian đọc theo thời điểm trong ngày

    class Config:
        from_attributes = True
