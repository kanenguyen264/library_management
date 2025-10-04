from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# Reading List Schemas
class ReadingListBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = False
    is_active: bool = True


class ReadingListCreate(ReadingListBase):
    user_id: Optional[int] = None


class ReadingListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    is_active: Optional[bool] = None


class ReadingListInDB(ReadingListBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReadingListResponse(ReadingListBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


# Reading List Item Schemas
class ReadingListItemBase(BaseModel):
    reading_list_id: int
    book_id: int
    added_at: Optional[datetime] = None
    notes: Optional[str] = None


class ReadingListItemCreate(ReadingListItemBase):
    pass


class ReadingListItemUpdate(BaseModel):
    reading_list_id: Optional[int] = None
    book_id: Optional[int] = None
    added_at: Optional[datetime] = None
    notes: Optional[str] = None


class ReadingListItemInDB(ReadingListItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReadingListItemResponse(ReadingListItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


# Schemas with Forward References
class ReadingListItemWithDetails(ReadingListItemResponse):
    model_config = ConfigDict(from_attributes=True)

    book: Optional["BookResponse"] = None


class ReadingListWithItems(ReadingListResponse):
    model_config = ConfigDict(from_attributes=True)

    items: List[ReadingListItemWithDetails] = []
    user: Optional["UserResponse"] = None


# Resolve forward references after all schemas are defined
def _rebuild_reading_list_schemas():
    """Rebuild reading list schemas to resolve forward references."""
    try:
        from app.schemas.book import BookResponse
        from app.schemas.user import UserResponse

        # Update the annotations with actual types
        ReadingListItemWithDetails.__annotations__["book"] = Optional[BookResponse]
        ReadingListWithItems.__annotations__["user"] = Optional[UserResponse]

        # Rebuild the models
        ReadingListItemWithDetails.model_rebuild()
        ReadingListWithItems.model_rebuild()
    except Exception:
        # If rebuild fails, continue with forward references
        pass


# Try to rebuild schemas on import
_rebuild_reading_list_schemas()
