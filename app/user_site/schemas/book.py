from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import date, datetime
from pydantic import BaseModel, Field, HttpUrl

# Sử dụng TYPE_CHECKING để tránh import vòng tròn trong runtime
if TYPE_CHECKING:
    from .author import AuthorBrief
else:
    # Trong runtime, import không đầy đủ để tránh vòng tròn
    from .author import AuthorBrief

from .category import CategoryBrief
from .tag import TagBrief
from .publisher import PublisherBrief  # Giả sử có PublisherBrief trong publisher.py


# Thêm class Publisher cho admin API
class Publisher(BaseModel):
    """
    Schema đầy đủ cho nhà xuất bản.
    """

    id: int
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    contact_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookBrief(BaseModel):
    """
    Schema tóm tắt cho sách.
    """

    id: int
    title: str
    cover_thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True


class BookBriefResponse(BookBrief):
    """
    Schema tóm tắt cho sách khi trả về API response.
    """

    author_name: Optional[str] = None
    avg_rating: Optional[float] = None
    publication_date: Optional[date] = None

    class Config:
        from_attributes = True


class ChapterInfo(BaseModel):
    """
    Schema thông tin chương sách.
    """

    id: int
    title: str
    chapter_number: int
    book_id: int
    word_count: Optional[int] = None
    is_published: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookBase(BaseModel):
    title: str
    subtitle: Optional[str] = None
    isbn: Optional[str] = None
    publication_date: Optional[date] = None
    language: Optional[str] = None
    page_count: Optional[int] = None
    cover_image_url: Optional[HttpUrl] = None
    cover_thumbnail_url: Optional[HttpUrl] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    mature_content: Optional[bool] = False
    is_featured: Optional[bool] = False

    class Config:
        from_attributes = True


class BookCreateRequest(BookBase):
    # Các trường chỉ được phép khi tạo sách (admin)
    is_published: Optional[bool] = False

    # Danh sách ID tác giả, danh mục, tags
    author_ids: Optional[List[int]] = Field(default_factory=list)
    category_ids: Optional[List[int]] = Field(default_factory=list)
    tag_ids: Optional[List[int]] = Field(default_factory=list)


class BookUpdateRequest(BookBase):
    title: Optional[str] = None

    # Danh sách ID tác giả, danh mục, tags
    author_ids: Optional[List[int]] = None
    category_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None


class BookAdminUpdate(BookUpdateRequest):
    # Các trường chỉ admin mới được phép cập nhật
    is_featured: Optional[bool] = None
    is_published: Optional[bool] = None
    avg_rating: Optional[float] = None
    review_count: Optional[int] = None
    popularity_score: Optional[float] = None


class BookResponse(BookBase):
    id: int
    publication_date: Optional[date] = None
    is_published: bool
    avg_rating: float
    review_count: int
    popularity_score: float
    created_at: datetime
    updated_at: datetime
    publisher: Optional[PublisherBrief] = None
    authors: List["AuthorBrief"] = []

    class Config:
        from_attributes = True


class BookDetailResponse(BookResponse):
    categories: List[CategoryBrief] = []
    tags: List[TagBrief] = []

    class Config:
        from_attributes = True


class BookInfo(BookResponse):
    """
    Schema thông tin chi tiết sách cho admin API.
    """

    categories: List[CategoryBrief] = []
    tags: List[TagBrief] = []
    is_active: bool = True
    chapter_count: Optional[int] = None

    class Config:
        from_attributes = True


class BookListResponse(BaseModel):
    items: List[BookResponse]
    total: int
    page: int
    pages: int


class BookSearchParams(BaseModel):
    skip: int = 0
    limit: int = 20
    sort_by: str = "popularity_score"
    sort_desc: bool = True
    category_id: Optional[int] = None
    tag_id: Optional[int] = None
    author_id: Optional[int] = None
    is_featured: Optional[bool] = None
    language: Optional[str] = None
    search: Optional[str] = None


class BookStatistics(BaseModel):
    total_books: int
    published_books: int
    unpublished_books: int
    featured_books: int
    total_chapters: int
    books_by_language: Dict[str, int] = {}
    books_by_category: Dict[str, int] = {}
    recent_books: List[BookResponse] = []
    popular_books: List[BookResponse] = []

    class Config:
        from_attributes = True


class BookRatingCreate(BaseModel):
    """
    Schema cho việc tạo đánh giá sách.
    """

    book_id: int
    rating: int = Field(..., ge=1, le=5, description="Đánh giá từ 1-5 sao")
    review: Optional[str] = Field(
        None, max_length=2000, description="Nhận xét của người dùng"
    )
    is_anonymous: bool = Field(False, description="Đánh giá ẩn danh")

    class Config:
        from_attributes = True


class BookRecommendationResponse(BaseModel):
    """
    Schema response cho đề xuất sách.
    """

    book: BookResponse
    confidence_score: float = Field(
        ..., ge=0, le=1, description="Độ tin cậy của đề xuất (0-1)"
    )
    recommendation_type: str = Field(
        ..., description="Loại đề xuất (personalized, similar, popular)"
    )
    reason: Optional[str] = None

    class Config:
        from_attributes = True


# Cập nhật các tham chiếu chuyển tiếp
BookResponse.update_forward_refs()
