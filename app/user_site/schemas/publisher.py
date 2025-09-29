from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class PublisherBase(BaseModel):
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    contact_email: Optional[str] = None


class PublisherCreate(PublisherBase):
    pass


class PublisherUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None


class PublisherBrief(BaseModel):
    """
    Schema cho thông tin tóm tắt về nhà xuất bản.
    Sử dụng cho các API cần thông tin ngắn gọn.
    """

    id: int
    name: str
    logo_url: Optional[str] = None
    books_count: Optional[int] = Field(0, description="Số lượng sách đã xuất bản")

    class Config:
        from_attributes = True


class PublisherResponse(PublisherBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PublisherListResponse(BaseModel):
    items: List[PublisherResponse]
    total: int
    page: Optional[int] = 1
    size: Optional[int] = 10

    class Config:
        from_attributes = True


class BookResponse(BaseModel):
    id: int
    title: str
    author_id: int
    publisher_id: int
    isbn: Optional[str] = None
    publication_date: Optional[datetime] = None
    cover_image: Optional[str] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    page_count: Optional[int] = None
    language: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    author_name: Optional[str] = None
    publisher_name: Optional[str] = None

    class Config:
        from_attributes = True


class PublisherStatsResponse(BaseModel):
    total_publishers: int
    active_publishers: int
    publishers_with_books: int
    total_books_published: int
    new_publishers_this_month: int
    most_prolific_publishers: List[Dict[str, Any]] = []
    publishers_by_country: Dict[str, int] = {}
    recent_publishers: List[PublisherResponse] = []
    books_per_publisher_avg: float = 0

    class Config:
        from_attributes = True


class PublisherDetailResponse(PublisherResponse):
    """
    Schema for detailed publisher information.
    Extends the basic publisher response with additional details.
    """

    founded_year: Optional[int] = None
    country: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    social_media: Optional[Dict[str, str]] = Field(
        default_factory=dict, description="Social media links"
    )
    books_count: int = Field(0, description="Number of books published")
    authors_count: int = Field(0, description="Number of authors worked with")
    average_rating: Optional[float] = Field(None, description="Average rating of books")
    top_genres: List[Dict[str, Any]] = Field(
        default_factory=list, description="Most published genres"
    )
    latest_books: List[BookResponse] = Field(
        default_factory=list, description="Recently published books"
    )

    class Config:
        from_attributes = True


class PublisherSearchParams(BaseModel):
    """
    Parameters for advanced publisher search.
    """

    name: Optional[str] = None
    country: Optional[str] = None
    founded_year_min: Optional[int] = None
    founded_year_max: Optional[int] = None
    min_books: Optional[int] = None
    genres: Optional[List[str]] = None
    page: int = Field(1, ge=1, description="Page number")
    limit: int = Field(20, ge=1, le=100, description="Results per page")
    sort_by: str = Field("name", description="Field to sort by")
    sort_desc: bool = Field(False, description="Sort in descending order")
