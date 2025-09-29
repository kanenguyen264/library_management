from typing import Optional, List, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    Query,
    Path,
    status,
    HTTPException,
    Request,
    Body,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_user,
    get_current_active_user)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.publisher import (
    PublisherResponse,
    PublisherDetailResponse,
    PublisherListResponse,
    PublisherStatsResponse,
    PublisherSearchParams,
)
from app.user_site.services.publisher_service import PublisherService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.core.exceptions import NotFoundException, ServerException, BadRequestException

router = APIRouter()
logger = get_logger("publisher_api")


@router.get("/", response_model=PublisherListResponse)
@track_request_time(endpoint="list_publishers")
@cache_response(ttl=3600, vary_by=["name", "page", "limit", "sort_by", "sort_desc"])
async def list_publishers(
    name: Optional[str] = Query(None, description="Tìm kiếm theo tên"),
    country: Optional[str] = Query(None, description="Lọc theo quốc gia"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    sort_by: str = Query(
        "name",
        regex="^(name|founded_year|book_count)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(False, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách nhà xuất bản với các tùy chọn lọc và sắp xếp.

    - **name**: Tìm kiếm theo tên nhà xuất bản (tìm kiếm mờ)
    - **country**: Lọc theo quốc gia của nhà xuất bản
    - **page**: Trang hiện tại
    - **limit**: Số lượng kết quả mỗi trang
    - **sort_by**: Sắp xếp theo trường (name, founded_year, book_count)
    - **sort_desc**: Sắp xếp giảm dần (true) hoặc tăng dần (false)
    """
    publisher_service = PublisherService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        publishers, total = await publisher_service.list_publishers(
            name=name,
            country=country,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": publishers,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách nhà xuất bản: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách nhà xuất bản")


@router.post("/search", response_model=PublisherListResponse)
@track_request_time(endpoint="search_publishers")
async def search_publishers(
    search_params: PublisherSearchParams, db: AsyncSession = Depends(get_db)
):
    """
    Tìm kiếm nâng cao các nhà xuất bản với nhiều tiêu chí.

    Cho phép tìm kiếm theo nhiều tiêu chí như tên, quốc gia,
    năm thành lập, thể loại sách, và các thuộc tính khác.
    """
    publisher_service = PublisherService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (search_params.page - 1) * search_params.limit

        # Tạo dict tham số tìm kiếm
        search_dict = search_params.model_dump(exclude={"page", "limit"})
        search_dict["skip"] = skip
        search_dict["limit"] = search_params.limit

        publishers, total = await publisher_service.search_publishers(**search_dict)

        # Tính toán tổng số trang
        total_pages = (
            (total + search_params.limit - 1) // search_params.limit if total > 0 else 0
        )

        return {
            "items": publishers,
            "total": total,
            "page": search_params.page,
            "limit": search_params.limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm nhà xuất bản: {str(e)}")
        raise ServerException(detail="Lỗi khi tìm kiếm nhà xuất bản")


@router.get("/{publisher_id}", response_model=PublisherDetailResponse)
@track_request_time(endpoint="get_publisher")
@cache_response(ttl=3600, vary_by=["publisher_id"])
async def get_publisher(
    publisher_id: int = Path(..., gt=0, description="ID của nhà xuất bản"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin chi tiết về nhà xuất bản.

    Trả về thông tin đầy đủ về nhà xuất bản bao gồm mô tả, địa chỉ,
    thông tin liên hệ, năm thành lập, và các thống kê về sách.
    """
    publisher_service = PublisherService(db)

    try:
        publisher = await publisher_service.get_publisher_by_id(publisher_id)

        if not publisher:
            raise NotFoundException(
                detail=f"Không tìm thấy nhà xuất bản với ID: {publisher_id}",
                code="publisher_not_found",
            )

        return publisher
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin nhà xuất bản {publisher_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin nhà xuất bản")


@router.get("/popular", response_model=List[PublisherResponse])
@track_request_time(endpoint="get_popular_publishers")
@cache_response(ttl=3600, vary_by=["limit", "country"])
async def get_popular_publishers(
    limit: int = Query(10, ge=1, le=50, description="Số lượng nhà xuất bản lấy"),
    country: Optional[str] = Query(None, description="Lọc theo quốc gia"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách nhà xuất bản phổ biến.

    Danh sách được sắp xếp theo lượng sách xuất bản, đánh giá trung bình,
    và mức độ phổ biến gần đây.

    - **limit**: Số lượng nhà xuất bản trả về
    - **country**: Lọc theo quốc gia (tùy chọn)
    """
    publisher_service = PublisherService(db)

    try:
        publishers = await publisher_service.get_popular_publishers(
            limit=limit, country=country
        )
        return publishers
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách nhà xuất bản phổ biến: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách nhà xuất bản phổ biến")


@router.get("/{publisher_id}/stats", response_model=PublisherStatsResponse)
@track_request_time(endpoint="get_publisher_stats")
@cache_response(ttl=3600, vary_by=["publisher_id"])
async def get_publisher_stats(
    publisher_id: int = Path(..., gt=0, description="ID của nhà xuất bản"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thống kê chi tiết về nhà xuất bản.

    Bao gồm thống kê về số lượng sách xuất bản theo thể loại, năm,
    đánh giá trung bình, tổng lượt đọc, và các số liệu khác.
    """
    publisher_service = PublisherService(db)

    try:
        publisher = await publisher_service.get_publisher_by_id(publisher_id)

        if not publisher:
            raise NotFoundException(
                detail=f"Không tìm thấy nhà xuất bản với ID: {publisher_id}",
                code="publisher_not_found",
            )

        stats = await publisher_service.get_publisher_stats(publisher_id)
        return stats
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê nhà xuất bản {publisher_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thống kê nhà xuất bản")


@router.get("/{publisher_id}/books", response_model=PublisherListResponse)
@track_request_time(endpoint="get_publisher_books")
@cache_response(
    ttl=1800,
    vary_by=["publisher_id", "page", "limit", "category_id", "sort_by", "sort_desc"],
)
async def get_publisher_books(
    publisher_id: int = Path(..., gt=0, description="ID của nhà xuất bản"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    category_id: Optional[int] = Query(
        None, gt=0, description="Lọc theo thể loại sách"
    ),
    publication_year: Optional[int] = Query(
        None, gt=0, description="Lọc theo năm xuất bản"
    ),
    sort_by: str = Query(
        "publication_date",
        regex="^(publication_date|title|rating|popularity)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách sách của nhà xuất bản với các tùy chọn lọc và sắp xếp.

    - **publisher_id**: ID của nhà xuất bản
    - **page**: Trang hiện tại
    - **limit**: Số lượng kết quả mỗi trang
    - **category_id**: Lọc theo thể loại sách
    - **publication_year**: Lọc theo năm xuất bản
    - **sort_by**: Sắp xếp theo trường (publication_date, title, rating, popularity)
    - **sort_desc**: Sắp xếp giảm dần (true) hoặc tăng dần (false)
    """
    publisher_service = PublisherService(db)

    try:
        publisher = await publisher_service.get_publisher_by_id(publisher_id)

        if not publisher:
            raise NotFoundException(
                detail=f"Không tìm thấy nhà xuất bản với ID: {publisher_id}",
                code="publisher_not_found",
            )

        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        books, total = await publisher_service.get_publisher_books(
            publisher_id=publisher_id,
            skip=skip,
            limit=limit,
            category_id=category_id,
            publication_year=publication_year,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": books,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách sách của nhà xuất bản {publisher_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách sách của nhà xuất bản")


@router.get("/similar/{publisher_id}", response_model=List[PublisherResponse])
@track_request_time(endpoint="get_similar_publishers")
@cache_response(ttl=3600, vary_by=["publisher_id", "limit"])
async def get_similar_publishers(
    publisher_id: int = Path(..., gt=0, description="ID của nhà xuất bản"),
    limit: int = Query(5, ge=1, le=20, description="Số lượng nhà xuất bản tương tự"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách nhà xuất bản tương tự.

    Tương tự được xác định dựa trên các yếu tố như thể loại sách chính,
    quốc gia, và lượng độc giả trùng lặp.
    """
    publisher_service = PublisherService(db)

    try:
        publisher = await publisher_service.get_publisher_by_id(publisher_id)

        if not publisher:
            raise NotFoundException(
                detail=f"Không tìm thấy nhà xuất bản với ID: {publisher_id}",
                code="publisher_not_found",
            )

        similar_publishers = await publisher_service.get_similar_publishers(
            publisher_id, limit
        )
        return similar_publishers
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách nhà xuất bản tương tự với {publisher_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách nhà xuất bản tương tự")


@router.get("/by-category/{category_id}", response_model=List[PublisherResponse])
@track_request_time(endpoint="get_publishers_by_category")
@cache_response(ttl=3600, vary_by=["category_id", "limit"])
async def get_publishers_by_category(
    category_id: int = Path(..., gt=0, description="ID của thể loại"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng nhà xuất bản lấy"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách nhà xuất bản nổi bật cho một thể loại sách cụ thể.

    Hữu ích khi muốn tìm những nhà xuất bản chuyên về một thể loại sách cụ thể.
    """
    publisher_service = PublisherService(db)

    try:
        publishers = await publisher_service.get_publishers_by_category(
            category_id, limit
        )
        return publishers
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách nhà xuất bản theo thể loại {category_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách nhà xuất bản theo thể loại")


@router.get("/featured", response_model=List[PublisherDetailResponse])
@track_request_time(endpoint="get_featured_publishers")
@cache_response(ttl=3600, vary_by=["limit"])
async def get_featured_publishers(
    limit: int = Query(5, ge=1, le=10, description="Số lượng nhà xuất bản nổi bật"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách nhà xuất bản được giới thiệu (featured).

    Danh sách các nhà xuất bản nổi bật, thường được đội ngũ biên tập chọn lọc
    hoặc dựa trên các chiến dịch quảng bá hiện tại.
    """
    publisher_service = PublisherService(db)

    try:
        featured_publishers = await publisher_service.get_featured_publishers(limit)
        return featured_publishers
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách nhà xuất bản nổi bật: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách nhà xuất bản nổi bật")
