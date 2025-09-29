from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class AnnotationBase(BaseModel):
    book_id: int
    chapter_id: Optional[int] = None
    highlighted_text: str
    start_offset: str
    end_offset: str
    note: Optional[str] = None
    color: Optional[str] = None
    is_public: bool = False


class AnnotationCreate(AnnotationBase):
    pass


class AnnotationUpdate(BaseModel):
    highlighted_text: Optional[str] = None
    start_offset: Optional[str] = None
    end_offset: Optional[str] = None
    note: Optional[str] = None
    color: Optional[str] = None
    is_public: Optional[bool] = None


class AnnotationResponse(AnnotationBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnnotationListResponse(BaseModel):
    items: List[AnnotationResponse]
    total: int
    page: Optional[int] = 1
    limit: Optional[int] = 20
    total_pages: Optional[int] = 1

    class Config:
        from_attributes = True


class AnnotationSearchParams(BaseModel):
    query: Optional[str] = None
    book_id: Optional[int] = None
    chapter_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    color: Optional[str] = None
    is_public: Optional[bool] = None
    page: int = 1
    limit: int = 20

    class Config:
        from_attributes = True


class AnnotationStatsResponse(BaseModel):
    total_annotations: int
    total_books_with_annotations: int
    annotations_by_color: dict
    annotations_by_month: dict

    class Config:
        from_attributes = True
