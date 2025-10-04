from datetime import datetime
from typing import ForwardRef, Optional

from pydantic import BaseModel, ConfigDict

# Forward references for avoiding circular imports
BookResponse = ForwardRef("BookResponse")


class ChapterBase(BaseModel):
    title: str
    content: Optional[str] = None
    chapter_number: int
    image_url: Optional[str] = None
    is_published: bool = False
    is_active: bool = True
    book_id: int


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    chapter_number: Optional[int] = None
    image_url: Optional[str] = None
    is_published: Optional[bool] = None
    is_active: Optional[bool] = None
    book_id: Optional[int] = None


class ChapterInDB(ChapterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class ChapterResponse(ChapterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class ChapterWithDetails(ChapterResponse):
    model_config = ConfigDict(from_attributes=True)

    book: Optional[BookResponse] = None


# Resolve forward references after all schemas are defined
def _rebuild_chapter_schemas():
    """Rebuild chapter schemas to resolve forward references."""
    try:
        from app.schemas.book import BookResponse as BookResponseActual

        # Update the annotations with actual types
        ChapterWithDetails.__annotations__["book"] = Optional[BookResponseActual]

        # Rebuild the model
        ChapterWithDetails.model_rebuild()
    except ImportError:
        # Handle case where dependencies are not available yet
        pass


# Try to rebuild immediately, but don't fail if dependencies not ready
try:
    _rebuild_chapter_schemas()
except Exception:
    pass
