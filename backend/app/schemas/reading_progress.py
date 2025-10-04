from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ReadingProgressBase(BaseModel):
    user_id: int
    book_id: int
    current_page: int = 0
    total_pages: Optional[int] = None
    progress_percentage: float = 0.0
    reading_time_minutes: int = 0
    status: str = "not_started"
    is_completed: bool = False
    notes: Optional[str] = None


class ReadingProgressCreate(ReadingProgressBase):
    pass


class ReadingProgressUpdate(BaseModel):
    user_id: Optional[int] = None
    book_id: Optional[int] = None
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
    progress_percentage: Optional[float] = None
    reading_time_minutes: Optional[int] = None
    status: Optional[str] = None
    is_completed: Optional[bool] = None
    notes: Optional[str] = None


class ReadingProgressInDB(ReadingProgressBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_read_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReadingProgressResponse(ReadingProgressBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_read_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReadingProgressWithDetails(ReadingProgressResponse):
    model_config = ConfigDict(from_attributes=True)

    book: Optional["BookResponse"] = None
    user: Optional["UserResponse"] = None


# Resolve forward references after all schemas are defined
def _rebuild_reading_progress_schemas():
    """Rebuild reading progress schemas to resolve forward references."""
    try:
        from app.schemas.book import BookResponse
        from app.schemas.user import UserResponse

        # Update the annotations with actual types
        ReadingProgressWithDetails.__annotations__["book"] = Optional[BookResponse]
        ReadingProgressWithDetails.__annotations__["user"] = Optional[UserResponse]

        # Rebuild the model
        ReadingProgressWithDetails.model_rebuild()
    except Exception:
        # If rebuild fails, continue with forward references
        pass


# Try to rebuild schemas on import
_rebuild_reading_progress_schemas()
