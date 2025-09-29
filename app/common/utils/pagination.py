"""
Utilities for pagination.
"""

from typing import Generic, List, Optional, Type, TypeVar, Dict, Any
from fastapi import Query, Depends, HTTPException
import math

T = TypeVar("T")


class PaginationParams:
    """
    Class chứa tham số phân trang cho các API endpoints.
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Số trang, bắt đầu từ 1"),
        size: int = Query(
            20, ge=1, le=100, description="Số lượng items trên mỗi trang"
        ),
        sort_by: Optional[str] = Query(
            None, description="Sắp xếp theo trường (default: created_at)"
        ),
        sort_desc: bool = Query(True, description="Sắp xếp giảm dần nếu True"),
    ):
        """
        Khởi tạo tham số phân trang.

        Args:
            page: Số trang
            size: Số lượng items trên mỗi trang
            sort_by: Sắp xếp theo trường
            sort_desc: Sắp xếp giảm dần nếu True
        """
        self.page = page
        self.size = size
        self.sort_by = sort_by
        self.sort_desc = sort_desc

    @property
    def skip(self) -> int:
        """
        Số lượng items bỏ qua.

        Returns:
            Số lượng items bỏ qua
        """
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        """
        Số lượng items tối đa trả về.

        Returns:
            Số lượng items tối đa trả về
        """
        return self.size

    def to_dict(self) -> Dict[str, Any]:
        """
        Chuyển đổi thành dictionary.

        Returns:
            Dictionary chứa các tham số phân trang
        """
        return {
            "page": self.page,
            "size": self.size,
            "skip": self.skip,
            "limit": self.limit,
            "sort_by": self.sort_by,
            "sort_desc": self.sort_desc,
        }


class PagedResponse(Generic[T]):
    """
    Class chứa dữ liệu phân trang cho API response.
    """

    def __init__(
        self,
        items: List[T],
        total: int,
        page: int,
        size: int,
        pages: Optional[int] = None,
        has_prev: Optional[bool] = None,
        has_next: Optional[bool] = None,
    ):
        """
        Khởi tạo PagedResponse.

        Args:
            items: Danh sách items trong trang hiện tại
            total: Tổng số items
            page: Số trang hiện tại
            size: Số lượng items trên mỗi trang
            pages: Tổng số trang
            has_prev: Có trang trước không
            has_next: Có trang sau không
        """
        self.items = items
        self.total = total
        self.page = page
        self.size = size

        # Tính các thông tin phân trang nếu chưa cung cấp
        self.pages = pages or math.ceil(total / size) if size > 0 else 0
        self.has_prev = has_prev or (page > 1)
        self.has_next = has_next or (page < self.pages)

    def dict(self) -> Dict[str, Any]:
        """
        Chuyển đổi thành dictionary.

        Returns:
            Dictionary representation of the paged response
        """
        return {
            "items": self.items,
            "pagination": {
                "total": self.total,
                "page": self.page,
                "size": self.size,
                "pages": self.pages,
                "has_prev": self.has_prev,
                "has_next": self.has_next,
            },
        }


def paginate(items: List[T], total: int, params: PaginationParams) -> PagedResponse[T]:
    """
    Tạo PagedResponse từ danh sách items và tham số phân trang.

    Args:
        items: Danh sách items trong trang hiện tại
        total: Tổng số items
        params: Tham số phân trang

    Returns:
        PagedResponse object
    """
    return PagedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


def get_pagination_params(
    page: int = Query(1, ge=1, description="Số trang, bắt đầu từ 1"),
    size: int = Query(20, ge=1, le=100, description="Số lượng items trên mỗi trang"),
    sort_by: Optional[str] = Query(
        None, description="Sắp xếp theo trường (default: created_at)"
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần nếu True"),
) -> PaginationParams:
    """
    FastAPI dependency để lấy tham số phân trang.

    Args:
        page: Số trang
        size: Số lượng items trên mỗi trang
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần nếu True

    Returns:
        PaginationParams object
    """
    return PaginationParams(
        page=page,
        size=size,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )
