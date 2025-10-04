from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BookBase(BaseModel):
    title: Optional[str] = None
    isbn: Optional[str] = None
    description: Optional[str] = None
    publication_date: Optional[date] = None
    pages: Optional[int] = None
    language: Optional[str] = None
    cover_url: Optional[str] = None
    pdf_url: Optional[str] = None
    epub_url: Optional[str] = None
    price: Optional[float] = None
    is_free: Optional[bool] = False
    is_active: Optional[bool] = True


class BookCreate(BookBase):
    title: str
    author_id: int
    category_id: int


class BookUpdate(BaseModel):
    title: Optional[str] = None
    isbn: Optional[str] = None
    description: Optional[str] = None
    publication_date: Optional[date] = None
    pages: Optional[int] = None
    language: Optional[str] = None
    cover_url: Optional[str] = None
    pdf_url: Optional[str] = None
    epub_url: Optional[str] = None
    price: Optional[float] = None
    is_free: Optional[bool] = None
    is_active: Optional[bool] = None
    author_id: Optional[int] = None
    category_id: Optional[int] = None


class BookInDB(BookBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    category_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class BookResponse(BookInDB):
    pass


class BookWithDetails(BookResponse):
    author: Optional["AuthorResponse"] = None
    category: Optional["CategoryResponse"] = None


# Resolve forward references after all schemas are defined
def _rebuild_book_schemas():
    """Rebuild book schemas to resolve forward references."""
    try:
        from app.schemas.author import AuthorResponse
        from app.schemas.category import CategoryResponse

        # Update the annotations with actual types
        BookWithDetails.__annotations__["author"] = Optional[AuthorResponse]
        BookWithDetails.__annotations__["category"] = Optional[CategoryResponse]

        # Rebuild the model
        BookWithDetails.model_rebuild()
    except Exception:
        # If rebuild fails, continue with forward references
        pass


# Try to rebuild schemas on import
_rebuild_book_schemas()
