from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FavoriteBase(BaseModel):
    user_id: int
    book_id: int


class FavoriteCreate(FavoriteBase):
    pass


class FavoriteUpdate(BaseModel):
    user_id: Optional[int] = None
    book_id: Optional[int] = None


class FavoriteInDB(FavoriteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class FavoriteResponse(FavoriteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class FavoriteWithDetails(FavoriteResponse):
    model_config = ConfigDict(from_attributes=True)

    book: Optional["BookResponse"] = None
    user: Optional["UserResponse"] = None


# Resolve forward references after all schemas are defined
def _rebuild_favorite_schemas():
    """Rebuild favorite schemas to resolve forward references."""
    try:
        from app.schemas.book import BookResponse
        from app.schemas.user import UserResponse

        # Update the annotations with actual types
        FavoriteWithDetails.__annotations__["book"] = Optional[BookResponse]
        FavoriteWithDetails.__annotations__["user"] = Optional[UserResponse]

        # Rebuild the model
        FavoriteWithDetails.model_rebuild()
    except Exception:
        # If rebuild fails, continue with forward references
        pass


# Try to rebuild schemas on import
_rebuild_favorite_schemas()
