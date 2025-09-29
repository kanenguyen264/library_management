from typing import List, Optional, Dict
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field, validator
from enum import Enum


class GoalType(str, Enum):
    BOOKS = "books"
    PAGES = "pages"
    TIME = "time"


class GoalPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class ReadingGoalBase(BaseModel):
    goal_type: GoalType
    target_value: float
    period: GoalPeriod
    start_date: date
    end_date: Optional[date] = None
    is_completed: bool = False

    @validator("end_date", pre=True, always=True)
    def set_end_date(cls, v, values):
        if v:
            return v

        if "start_date" in values and "period" in values:
            start = datetime.combine(values["start_date"], datetime.min.time())
            period = values["period"]

            if period == GoalPeriod.DAILY:
                return start.date()
            elif period == GoalPeriod.WEEKLY:
                return (start + timedelta(days=7)).date()
            elif period == GoalPeriod.MONTHLY:
                # Approximate a month as 30 days - Consider using relativedelta for more accuracy
                return (start + timedelta(days=30)).date()
            elif period == GoalPeriod.YEARLY:
                # Approximate a year as 365 days - Consider leap years
                return (start + timedelta(days=365)).date()
        return v


class ReadingGoalCreate(ReadingGoalBase):
    pass


class ReadingGoalUpdate(BaseModel):
    target_value: Optional[float] = None
    end_date: Optional[date] = None
    is_completed: Optional[bool] = None


class ReadingGoalResponse(ReadingGoalBase):
    id: int
    user_id: int
    current_value: float
    created_at: datetime
    updated_at: datetime
    progress_percentage: float

    class Config:
        from_attributes = True


class ReadingGoalListResponse(BaseModel):
    items: List[ReadingGoalResponse]
    total: int

    class Config:
        from_attributes = True


class ReadingGoalProgressResponse(BaseModel):
    goal_id: int
    current_value: float
    target_value: float
    progress_percentage: float
    remaining_days: int
    daily_target: float

    class Config:
        from_attributes = True


class ReadingGoalStatsResponse(BaseModel):
    """Phản hồi thống kê mục tiêu đọc."""

    total_goals: int = 0
    completed_goals: int = 0
    in_progress_goals: int = 0
    completion_rate: float = 0.0
    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    by_month: Dict[str, int] = {}
    average_completion_time: Optional[int] = (
        None  # Thời gian trung bình để hoàn thành mục tiêu (ngày)
    )
    longest_streak: int = 0
    current_streak: int = 0

    class Config:
        from_attributes = True


class ReadingGoalSearchParams(BaseModel):
    """Tham số tìm kiếm mục tiêu đọc."""

    goal_type: Optional[GoalType] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    book_id: Optional[int] = None
    is_public: Optional[bool] = None
    sort_by: Optional[str] = "created_at"
    sort_desc: bool = True


class ReadingGoalShareResponse(BaseModel):
    """Phản hồi chia sẻ mục tiêu đọc."""

    success: bool
    share_url: Optional[str] = None
    share_image: Optional[str] = None
    platform: str
    message: Optional[str] = None

    class Config:
        from_attributes = True
