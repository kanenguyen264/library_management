from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Path, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_user
from app.user_site.models.user import User
from app.user_site.schemas.category import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    CategoryDetailResponse,
    CategoryBrief,
    CategoryListResponse,
)
from app.user_site.services.category_service import CategoryService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response
from app.core.exceptions import NotFoundException, ServerException, BadRequestException

router = APIRouter()
logger = get_logger("category_api")


@router.get("/", response_model=CategoryListResponse)
@track_request_time(endpoint="list_categories")
@cache_response(ttl=3600, vary_by=["parent_id", "skip", "limit"])
async def list_categories(
    parent_id: Optional[int] = Query(None, ge=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách danh mục. Có thể lọc theo danh mục cha (parent_id).

    - **parent_id**: ID của danh mục cha (nếu không có, lấy tất cả danh mục gốc)
    - **skip**: Số lượng bản ghi bỏ qua (phân trang)
    - **limit**: Số lượng bản ghi lấy về
    """
    category_service = CategoryService(db)

    try:
        categories, total = await category_service.list_categories(
            parent_id=parent_id, skip=skip, limit=limit
        )

        return {"items": categories, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách danh mục: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách danh mục")


@router.get("/all", response_model=List[CategoryResponse])
@track_request_time(endpoint="get_all_categories")
@cache_response(ttl=3600)
async def get_all_categories(db: AsyncSession = Depends(get_db)):
    """
    Lấy tất cả các danh mục, bao gồm cả cấu trúc phân cấp.

    Kết quả trả về các danh mục theo cấu trúc cây với danh mục con được lồng trong danh mục cha.
    """
    category_service = CategoryService(db)

    try:
        return await category_service.get_all_categories_hierarchical()
    except Exception as e:
        logger.error(f"Lỗi khi lấy tất cả danh mục: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy tất cả danh mục")


@router.get("/popular", response_model=List[CategoryResponse])
@track_request_time(endpoint="get_popular_categories")
@cache_response(ttl=7200, vary_by=["limit"])
async def get_popular_categories(
    limit: int = Query(10, ge=1, le=50), db: AsyncSession = Depends(get_db)
):
    """
    Lấy danh sách các danh mục phổ biến nhất.

    - **limit**: Số lượng danh mục trả về
    """
    category_service = CategoryService(db)

    try:
        return await category_service.get_popular_categories(limit=limit)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh mục phổ biến: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh mục phổ biến")


@router.get("/{category_id}", response_model=CategoryDetailResponse)
@track_request_time(endpoint="get_category")
@cache_response(ttl=1800, vary_by=["category_id"])
async def get_category(
    category_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)
):
    """
    Lấy thông tin chi tiết của một danh mục.

    - **category_id**: ID của danh mục
    """
    category_service = CategoryService(db)

    try:
        category = await category_service.get_category_by_id(category_id)

        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID: {category_id}",
                code="category_not_found",
            )

        return category
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin danh mục {category_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin danh mục")


@router.get("/slug/{slug}", response_model=CategoryDetailResponse)
@track_request_time(endpoint="get_category_by_slug")
@cache_response(ttl=1800, vary_by=["slug"])
async def get_category_by_slug(
    slug: str = Path(..., min_length=1), db: AsyncSession = Depends(get_db)
):
    """
    Lấy thông tin chi tiết của một danh mục theo slug.

    - **slug**: Slug của danh mục
    """
    category_service = CategoryService(db)

    try:
        category = await category_service.get_category_by_slug(slug)

        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với slug: {slug}",
                code="category_not_found",
            )

        return category
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin danh mục theo slug {slug}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin danh mục")


@router.get("/{category_id}/books", response_model=Dict[str, Any])
@track_request_time(endpoint="get_category_books")
@cache_response(
    ttl=300, vary_by=["category_id", "page", "page_size", "sort_by", "sort_desc"]
)
async def get_category_books(
    category_id: int = Path(..., gt=0),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=100, description="Số lượng sách mỗi trang"),
    sort_by: str = Query(
        "popularity", regex="^(title|publication_date|avg_rating|popularity)$"
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    include_subcategories: bool = Query(
        True, description="Bao gồm sách từ danh mục con"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách sách thuộc một danh mục.

    - **category_id**: ID của danh mục
    - **page**: Trang hiện tại
    - **page_size**: Số lượng sách mỗi trang
    - **sort_by**: Sắp xếp theo trường (title, publication_date, avg_rating, popularity)
    - **sort_desc**: Sắp xếp giảm dần (True) hoặc tăng dần (False)
    - **include_subcategories**: Bao gồm sách từ các danh mục con
    """
    category_service = CategoryService(db)

    try:
        # Kiểm tra danh mục có tồn tại không
        category = await category_service.get_category_by_id(category_id)
        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID: {category_id}",
                code="category_not_found",
            )

        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách sách
        books, total = await category_service.get_category_books(
            category_id=category_id,
            skip=skip,
            limit=page_size,
            sort_by=sort_by,
            sort_desc=sort_desc,
            include_subcategories=include_subcategories,
            user_id=current_user.id if current_user else None,
        )

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size  # Làm tròn lên

        return {
            "items": books,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "category": {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
            },
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy sách thuộc danh mục {category_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy sách thuộc danh mục")


@router.get("/{category_id}/subcategories", response_model=List[CategoryResponse])
@track_request_time(endpoint="get_subcategories")
@cache_response(ttl=1800, vary_by=["category_id"])
async def get_subcategories(
    category_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)
):
    """
    Lấy danh sách các danh mục con của một danh mục.

    - **category_id**: ID của danh mục cha
    """
    category_service = CategoryService(db)

    try:
        # Kiểm tra danh mục có tồn tại không
        category = await category_service.get_category_by_id(category_id)
        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID: {category_id}",
                code="category_not_found",
            )

        subcategories = await category_service.get_subcategories(category_id)
        return subcategories
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh mục con của danh mục {category_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh mục con")


@router.get("/stats/book-counts", response_model=List[Dict[str, Any]])
@track_request_time(endpoint="get_category_book_counts")
@cache_response(ttl=7200)
async def get_category_book_counts(db: AsyncSession = Depends(get_db)):
    """
    Lấy thống kê số lượng sách trong mỗi danh mục.
    """
    category_service = CategoryService(db)

    try:
        return await category_service.get_category_book_counts()
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê số lượng sách: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thống kê số lượng sách")


@router.get("/path/{category_id}", response_model=List[CategoryBrief])
@track_request_time(endpoint="get_category_path")
@cache_response(ttl=1800, vary_by=["category_id"])
async def get_category_path(
    category_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)
):
    """
    Lấy đường dẫn từ danh mục gốc đến danh mục hiện tại (breadcrumbs).

    - **category_id**: ID của danh mục
    """
    category_service = CategoryService(db)

    try:
        # Kiểm tra danh mục có tồn tại không
        category = await category_service.get_category_by_id(category_id)
        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID: {category_id}",
                code="category_not_found",
            )

        path = await category_service.get_category_path(category_id)
        return path
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy đường dẫn danh mục {category_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy đường dẫn danh mục")
