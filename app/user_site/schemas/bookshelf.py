from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class BookshelfBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = True
    cover_image: Optional[str] = None

class BookshelfCreate(BookshelfBase):
    pass

class BookshelfUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None

class BookshelfItemBase(BaseModel):
    book_id: int
    notes: Optional[str] = None
    added_at: Optional[datetime] = None

class BookshelfItemCreate(BookshelfItemBase):
    pass

class BookshelfItemUpdate(BaseModel):
    note: Optional[str] = None

class BookBrief(BaseModel):
    id: int
    title: str
    cover_thumbnail_url: Optional[str] = None
    avg_rating: float
    
    class Config:
        from_attributes = True

class UserBrief(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    
    class Config:
        from_attributes = True

class BookshelfItemResponse(BookshelfItemBase):
    id: int
    bookshelf_id: int
    created_at: datetime
    updated_at: datetime
    book: Optional[BookBrief] = None
    
    class Config:
        from_attributes = True

class BookshelfResponse(BookshelfBase):
    id: int
    user_id: int
    book_count: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserBrief] = None
    
    class Config:
        from_attributes = True

class BookshelfDetailResponse(BookshelfResponse):
    items: List[BookshelfItemResponse] = []
    
    class Config:
        from_attributes = True
