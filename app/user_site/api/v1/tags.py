from typing import Dict, Any, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    HTTPException,
    status,
    Request,
    Body,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_admin_user,
    get_current_user,
)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.tag import (
    TagCreate,
    TagUpdate,
    TagResponse,
    TagWithBooks,
    TagListResponse,
    TagBulkResponse,
    TagStatsResponse,
    TagTrendingResponse,
    TagSearchParams,
)
from app.user_site.services.tag_service import TagService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time, increment_counter
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    RateLimitExceededException,
)
from app.performance.performance import query_performance_tracker

router = APIRouter()
logger = get_logger("tags_api")


@router.get("/", response_model=TagListResponse)
@track_request_time(endpoint="list_tags")
@cache_response(ttl=3600, vary_by=["name", "skip", "limit", "sort_by", "sort_desc"])
async def list_tags(
    name: Optional[str] = Query(None, description="Tìm kiếm theo tên"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    sort_by: str = Query(
        "book_count", description="Sắp xếp theo (name, book_count, created_at)"
    ),
    sort_desc: bool = Query(True, description="Sắp xếp theo thứ tự giảm dần"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách thẻ.

    - Filtering: Hỗ trợ tìm kiếm theo tên
    - Pagination: Phân trang với skip/limit
    - Sorting: Sắp xếp theo nhiều trường và hướng
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    tag_service = TagService(db)

    try:
        with query_performance_tracker("list_tags", {"name": name, "sort_by": sort_by}):
            tags, total = await tag_service.list_tags(
                name=name, skip=skip, limit=limit, sort_by=sort_by, sort_desc=sort_desc
            )

        return {"items": tags, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thẻ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách thẻ",
        )


@router.post("/search", response_model=TagListResponse)
@track_request_time(endpoint="search_tags")
@throttle_requests(max_requests=15, per_seconds=60)
async def search_tags(
    params: TagSearchParams = Body(...), db: AsyncSession = Depends(get_db)
):
    """
    Tìm kiếm thẻ với các tùy chọn nâng cao.

    - Advanced search: Tìm kiếm nâng cao với nhiều tiêu chí
    - Rate limiting: Giới hạn 15 request/phút
    """
    tag_service = TagService(db)

    try:
        tags, total = await tag_service.search_tags(params)

        return {"items": tags, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm thẻ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tìm kiếm thẻ",
        )


@router.get("/popular", response_model=List[TagResponse])
@track_request_time(endpoint="get_popular_tags")
@cache_response(ttl=3600, vary_by=["limit", "category_id"])
async def get_popular_tags(
    limit: int = Query(10, ge=1, le=50, description="Số lượng thẻ lấy"),
    category_id: Optional[int] = Query(None, gt=0, description="Lọc theo danh mục"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách thẻ phổ biến.

    - Filtering: Tùy chọn lọc theo danh mục
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    tag_service = TagService(db)
    increment_counter("popular_tags_requested")

    try:
        tags = await tag_service.get_popular_tags(limit, category_id)
        return tags
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thẻ phổ biến: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách thẻ phổ biến",
        )


@router.get("/trending", response_model=List[TagTrendingResponse])
@track_request_time(endpoint="get_trending_tags")
@cache_response(ttl=1800, vary_by=["limit", "time_range"])
async def get_trending_tags(
    limit: int = Query(10, ge=1, le=50, description="Số lượng thẻ lấy"),
    time_range: str = Query(
        "week",
        regex="^(day|week|month)$",
        description="Khoảng thời gian: day, week, month",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách thẻ đang thịnh hành.

    - Trending: Dựa trên lượt sử dụng gần đây
    - Time filtering: Lọc theo khoảng thời gian
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    tag_service = TagService(db)

    try:
        trending_tags = await tag_service.get_trending_tags(limit, time_range)
        return trending_tags
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thẻ đang thịnh hành: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách thẻ đang thịnh hành",
        )


@router.get("/stats", response_model=TagStatsResponse)
@track_request_time(endpoint="get_tag_stats")
@cache_response(ttl=86400)  # Cache 24h
async def get_tag_stats(db: AsyncSession = Depends(get_db)):
    """
    Lấy thống kê tổng quan về thẻ.

    - Statistics: Tổng số thẻ, phân phối thẻ theo danh mục...
    - Caching: Cache kết quả 24h vì thay đổi chậm
    """
    tag_service = TagService(db)

    try:
        stats = await tag_service.get_tag_stats()
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê thẻ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thống kê thẻ",
        )


@router.get("/{tag_id}", response_model=TagResponse)
@track_request_time(endpoint="get_tag")
@cache_response(ttl=3600, vary_by=["tag_id"])
async def get_tag(
    tag_id: int = Path(..., gt=0, description="ID của thẻ"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin chi tiết của một thẻ.

    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    tag_service = TagService(db)

    try:
        tag = await tag_service.get_tag_by_id(tag_id)

        if not tag:
            raise NotFoundException(detail=f"Không tìm thấy thẻ với ID: {tag_id}")

        return tag
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin thẻ {tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin thẻ",
        )


@router.post("/", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_tag")
@throttle_requests(max_requests=10, per_seconds=60)
async def create_tag(
    data: TagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    request: Request = None,
):
    """
    Tạo một thẻ mới (Chỉ dành cho admin).

    - Admin only: Chỉ admin mới có thể tạo thẻ mới
    - Rate limiting: Giới hạn 10 request/phút
    - Validation: Kiểm tra dữ liệu đầu vào hợp lệ
    """
    tag_service = TagService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo thẻ mới - Admin: {current_user.id}, Tag: {data.name}, IP: {client_ip}"
    )

    try:
        # Kiểm tra thẻ đã tồn tại chưa
        existing_tag = await tag_service.get_tag_by_name(data.name)

        if existing_tag:
            raise BadRequestException(detail=f"Thẻ '{data.name}' đã tồn tại")

        tag = await tag_service.create_tag(data.model_dump())

        # Vô hiệu hóa cache liên quan
        await invalidate_cache("tags:list")
        await invalidate_cache("tags:popular")

        return tag
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo thẻ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo thẻ",
        )


@router.put("/{tag_id}", response_model=TagResponse)
@track_request_time(endpoint="update_tag")
async def update_tag(
    data: TagUpdate,
    tag_id: int = Path(..., gt=0, description="ID của thẻ"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    request: Request = None,
):
    """
    Cập nhật thông tin thẻ (Chỉ dành cho admin).

    - Admin only: Chỉ admin mới có thể cập nhật thẻ
    - Validation: Kiểm tra dữ liệu đầu vào hợp lệ
    - Cache invalidation: Vô hiệu hóa cache sau khi cập nhật
    """
    tag_service = TagService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật thẻ - Admin: {current_user.id}, Tag ID: {tag_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra thẻ có tồn tại không
        tag = await tag_service.get_tag_by_id(tag_id)

        if not tag:
            raise NotFoundException(detail=f"Không tìm thấy thẻ với ID: {tag_id}")

        # Nếu đổi tên, kiểm tra tên mới đã tồn tại chưa
        if data.name and data.name != tag.name:
            existing_tag = await tag_service.get_tag_by_name(data.name)

            if existing_tag:
                raise BadRequestException(detail=f"Thẻ '{data.name}' đã tồn tại")

        updated_tag = await tag_service.update_tag(
            tag_id, data.model_dump(exclude_unset=True)
        )

        # Vô hiệu hóa cache liên quan
        await invalidate_cache(f"tags:id:{tag_id}")
        await invalidate_cache("tags:list")

        return updated_tag
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thẻ {tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật thẻ",
        )


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_tag")
async def delete_tag(
    tag_id: int = Path(..., gt=0, description="ID của thẻ"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    request: Request = None,
):
    """
    Xóa một thẻ (Chỉ dành cho admin).

    - Admin only: Chỉ admin mới có thể xóa thẻ
    - Validation: Kiểm tra thẻ có tồn tại không
    - Cache invalidation: Vô hiệu hóa cache sau khi xóa
    """
    tag_service = TagService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa thẻ - Admin: {current_user.id}, Tag ID: {tag_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra thẻ có tồn tại không
        tag = await tag_service.get_tag_by_id(tag_id)

        if not tag:
            raise NotFoundException(detail=f"Không tìm thấy thẻ với ID: {tag_id}")

        await tag_service.delete_tag(tag_id)

        # Vô hiệu hóa cache liên quan
        await invalidate_cache(f"tags:id:{tag_id}")
        await invalidate_cache("tags:list")
        await invalidate_cache("tags:popular")

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa thẻ {tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa thẻ",
        )


@router.get("/{tag_id}/books", response_model=TagListResponse)
@track_request_time(endpoint="get_tag_books")
@cache_response(ttl=1800, vary_by=["tag_id", "skip", "limit", "sort_by", "sort_desc"])
async def get_tag_books(
    tag_id: int = Path(..., gt=0, description="ID của thẻ"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    sort_by: str = Query(
        "popularity",
        description="Sắp xếp theo (title, published_date, popularity, rating)",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp theo thứ tự giảm dần"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách sách có thẻ này.

    - Pagination: Phân trang với skip/limit
    - Sorting: Sắp xếp theo nhiều trường và hướng
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    tag_service = TagService(db)

    try:
        tag = await tag_service.get_tag_by_id(tag_id)

        if not tag:
            raise NotFoundException(detail=f"Không tìm thấy thẻ với ID: {tag_id}")

        books, total = await tag_service.get_tag_books(
            tag_id=tag_id, skip=skip, limit=limit, sort_by=sort_by, sort_desc=sort_desc
        )

        return {"items": books, "total": total}
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách của thẻ {tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách sách của thẻ",
        )


@router.get("/related/{tag_id}", response_model=List[TagResponse])
@track_request_time(endpoint="get_related_tags")
@cache_response(ttl=3600, vary_by=["tag_id", "limit"])
async def get_related_tags(
    tag_id: int = Path(..., gt=0, description="ID của thẻ"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng thẻ lấy"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các thẻ liên quan đến thẻ này.

    - Related: Dựa trên các thẻ thường xuất hiện cùng với thẻ này
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    tag_service = TagService(db)

    try:
        tag = await tag_service.get_tag_by_id(tag_id)

        if not tag:
            raise NotFoundException(detail=f"Không tìm thấy thẻ với ID: {tag_id}")

        related_tags = await tag_service.get_related_tags(tag_id, limit)
        return related_tags
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thẻ liên quan đến thẻ {tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách thẻ liên quan",
        )


@router.post("/bulk", response_model=TagBulkResponse, status_code=status.HTTP_200_OK)
@track_request_time(endpoint="process_tags_bulk")
@throttle_requests(max_requests=5, per_seconds=60)
async def process_tags_bulk(
    tags: List[str] = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    request: Request = None,
):
    """
    Xử lý hàng loạt thẻ (tạo nếu chưa tồn tại).

    - Bulk operation: Xử lý nhiều thẻ cùng lúc
    - Admin only: Chỉ admin mới có thể thực hiện
    - Rate limiting: Giới hạn 5 request/phút
    """
    tag_service = TagService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xử lý hàng loạt thẻ - Admin: {current_user.id}, Count: {len(tags)}, IP: {client_ip}"
    )

    try:
        result = await tag_service.process_tags_bulk(tags)

        # Vô hiệu hóa cache liên quan nếu có thẻ mới
        if result["created"] > 0:
            await invalidate_cache("tags:list")
            await invalidate_cache("tags:popular")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi xử lý hàng loạt thẻ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xử lý hàng loạt thẻ",
        )


@router.get("/suggest/{prefix}", response_model=List[TagResponse])
@track_request_time(endpoint="suggest_tags")
@cache_response(ttl=1800, vary_by=["prefix", "limit"])
async def suggest_tags(
    prefix: str = Path(
        ..., min_length=1, max_length=50, description="Tiền tố để gợi ý"
    ),
    limit: int = Query(10, ge=1, le=50, description="Số lượng gợi ý tối đa trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gợi ý thẻ dựa trên tiền tố.

    - Autocomplete: Hỗ trợ tính năng gợi ý khi gõ
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    tag_service = TagService(db)

    try:
        suggestions = await tag_service.suggest_tags(prefix, limit)
        return suggestions
    except Exception as e:
        logger.error(f"Lỗi khi gợi ý thẻ với tiền tố '{prefix}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi gợi ý thẻ",
        )
