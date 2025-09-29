from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, root_validator
from app.user_site.schemas.book import BookResponse
from app.user_site.schemas.user import UserPublicResponse


class BookListBase(BaseModel):
    title: str
    description: Optional[str] = None
    is_public: bool = True
    cover_image: Optional[str] = None


class BookListCreate(BookListBase):
    pass


class BookListUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class BookListItemBase(BaseModel):
    book_id: int
    note: Optional[str] = None
    position: int = 0
    added_at: Optional[datetime] = None


class BookListItemCreate(BookListItemBase):
    pass


class BookListItemUpdate(BaseModel):
    note: Optional[str] = None
    position: Optional[int] = None


class BookListItemResponse(BookListItemBase):
    id: int
    book: Optional[BookResponse] = None

    class Config:
        from_attributes = True


class BookListResponse(BookListBase):
    id: int
    user_id: int
    user: Optional[UserPublicResponse] = None
    item_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookListDetailResponse(BookListResponse):
    items: List[BookListItemResponse] = []

    class Config:
        from_attributes = True


class BookListListResponse(BaseModel):
    items: List[BookListResponse]
    total: int

    class Config:
        from_attributes = True


class BookListSearchParams(BaseModel):
    """
    Các tham số tìm kiếm danh sách sách.
    """

    query: Optional[str] = None  # Từ khóa tìm kiếm
    user_id: Optional[int] = None  # ID người dùng
    is_public: Optional[bool] = None  # Lọc công khai hay riêng tư
    sort_by: str = Field("created_at", description="Trường sắp xếp")
    sort_desc: bool = Field(True, description="Sắp xếp giảm dần")
    skip: int = Field(0, ge=0, description="Số lượng bỏ qua")
    limit: int = Field(20, ge=1, le=100, description="Số lượng lấy")
