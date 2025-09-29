from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    display_order: Optional[int] = 0


class CategoryCreate(CategoryBase):
    # Các trường chỉ được phép khi tạo danh mục (admin)
    is_active: Optional[bool] = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryBrief(BaseModel):
    id: int
    name: str
    slug: str
    icon: Optional[str] = None

    class Config:
        from_attributes = True


class CategoryResponse(CategoryBase):
    id: int
    is_active: bool
    book_count: int
    created_at: datetime
    updated_at: datetime
    parent: Optional[CategoryBrief] = None

    class Config:
        from_attributes = True


class CategoryDetailResponse(CategoryResponse):
    children: List[CategoryBrief] = []

    class Config:
        from_attributes = True


class CategoryListResponse(BaseModel):
    items: List[CategoryResponse]
    total: int
    page: Optional[int] = 1
    size: Optional[int] = 10
    pages: Optional[int] = 1

    class Config:
        from_attributes = True


# Alias và schema bổ sung
CategoryInfo = CategoryDetailResponse


class CategoryTreeItem(CategoryBrief):
    children: List["CategoryTreeItem"] = []
    level: int = 0
    is_featured: Optional[bool] = False

    class Config:
        from_attributes = True


CategoryTreeItem.update_forward_refs()


class CategoryTree(BaseModel):
    items: List[CategoryTreeItem]
    total: int

    class Config:
        from_attributes = True


class CategoryStatistics(BaseModel):
    total_categories: int
    active_categories: int
    inactive_categories: int
    featured_categories: int
    root_categories: int
    max_depth: int
    categories_by_level: Dict[int, int] = {}
    most_popular_categories: List[CategoryResponse] = []
    recently_updated_categories: List[CategoryResponse] = []

    class Config:
        from_attributes = True
