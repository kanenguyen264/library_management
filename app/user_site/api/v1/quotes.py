from typing import Optional, List, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
    Request,
    Body,
)
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_limiter.depends import RateLimiter

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_user,
    verify_subscription,
)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.quote import (
    QuoteResponse,
    QuoteCreate,
    QuoteUpdate,
    QuoteListResponse,
    QuotePublicResponse,
    QuoteSearchParams,
    QuoteStatsResponse,
    BulkQuoteOperation,
    QuoteShareResponse,
    QuoteExportFormat,
    QuoteReportCreate,
    QuoteCollectionCreate,
    QuoteCollectionResponse,
    QuoteCollectionListResponse,
)
from app.user_site.services.quote_service import QuoteService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    RateLimitException,
)
from app.security.input_validation.sanitizers import sanitize_text

router = APIRouter()
logger = get_logger("quotes_api")
audit_logger = AuditLogger()


@router.post("/", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_quote")
@throttle_requests(max_requests=10, per_seconds=60)
async def create_quote(
    data: QuoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một trích dẫn mới từ một cuốn sách.

    - Giới hạn tạo: Tối đa 10 trích dẫn mỗi phút
    - Validation: Kiểm tra dữ liệu đầu vào hợp lệ
    - Audit: Ghi lại hoạt động của người dùng
    """
    quote_service = QuoteService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo trích dẫn mới - User: {current_user.id}, Book: {data.book_id}, IP: {client_ip}"
    )

    try:
        # Validate book existence
        book_exists = await quote_service.is_book_exists(data.book_id)
        if not book_exists:
            raise BadRequestException(
                detail=f"Không tìm thấy sách với ID: {data.book_id}"
            )

        # Làm sạch dữ liệu đầu vào
        if data.content:
            data.content = sanitize_text(data.content)
        if data.note:
            data.note = sanitize_text(data.note)

        quote = await quote_service.create_quote(current_user.id, data.model_dump())

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "quote_create",
            f"Người dùng đã tạo trích dẫn mới từ sách {data.book_id}",
            metadata={"user_id": current_user.id, "book_id": data.book_id},
        )

        return quote
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo trích dẫn: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo trích dẫn",
        )


@router.get("/", response_model=QuoteListResponse)
@track_request_time(endpoint="list_quotes")
@cache_response(
    ttl=600,
    vary_by=[
        "book_id",
        "user_id",
        "is_public",
        "skip",
        "limit",
        "sort_by",
        "sort_desc",
    ],
)
async def list_quotes(
    book_id: Optional[int] = Query(None, gt=0, description="ID của sách"),
    user_id: Optional[int] = Query(None, gt=0, description="ID của người dùng"),
    is_public: Optional[bool] = Query(
        None, description="Lọc theo trạng thái công khai"
    ),
    chapter_id: Optional[int] = Query(None, gt=0, description="Lọc theo chương sách"),
    sort_by: str = Query("created_at", description="Sắp xếp theo trường"),
    sort_desc: bool = Query(True, description="Sắp xếp theo thứ tự giảm dần"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách trích dẫn với các bộ lọc.

    - Cache: Kết quả được cache để tối ưu hiệu suất
    - Phân trang: Hỗ trợ skip/limit
    - Sắp xếp: Hỗ trợ sắp xếp theo nhiều trường và hướng
    """
    quote_service = QuoteService(db)

    try:
        # Nếu đang lọc theo user_id là chính người dùng hiện tại hoặc không có user_id
        # thì người dùng có thể xem các trích dẫn riêng tư của họ
        include_private = False
        current_user_id = None

        if current_user:
            current_user_id = current_user.id
            if user_id is None or user_id == current_user.id:
                include_private = True

        quotes, total = await quote_service.list_quotes(
            book_id=book_id,
            user_id=user_id,
            is_public=is_public,
            chapter_id=chapter_id,
            skip=skip,
            limit=limit,
            include_private=include_private,
            current_user_id=current_user_id,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        return {"items": quotes, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách trích dẫn: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách trích dẫn",
        )


@router.post("/search", response_model=QuoteListResponse)
@track_request_time(endpoint="search_quotes")
@cache_response(ttl=300, vary_by=["query_hash"])
async def search_quotes(
    params: QuoteSearchParams = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Tìm kiếm trích dẫn với các tùy chọn nâng cao.

    - Tìm kiếm toàn văn bản trong nội dung trích dẫn
    - Lọc theo nhiều tiêu chí
    - Tìm kiếm theo từ khóa, thẻ, thời gian
    """
    quote_service = QuoteService(db)

    try:
        include_private = False
        current_user_id = None

        if current_user:
            current_user_id = current_user.id
            if params.user_id is None or params.user_id == current_user.id:
                include_private = True

        # Làm sạch chuỗi tìm kiếm
        if params.query:
            params.query = sanitize_text(params.query)

        quotes, total = await quote_service.search_quotes(
            params=params,
            include_private=include_private,
            current_user_id=current_user_id,
        )

        return {"items": quotes, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm trích dẫn: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tìm kiếm trích dẫn",
        )


@router.get("/stats", response_model=QuoteStatsResponse)
@track_request_time(endpoint="get_quote_stats")
@cache_response(ttl=3600, vary_by=["current_user.id"])
async def get_quote_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thống kê về trích dẫn của người dùng hiện tại.

    - Số lượng trích dẫn đã tạo
    - Số lượng lượt thích
    - Thống kê theo sách, theo thời gian
    """
    quote_service = QuoteService(db)

    try:
        stats = await quote_service.get_quote_stats(current_user.id)
        return stats
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thống kê trích dẫn cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thống kê trích dẫn",
        )


@router.post("/bulk", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="bulk_quote_operations")
@throttle_requests(max_requests=5, per_seconds=60)
async def bulk_quote_operations(
    operations: BulkQuoteOperation,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Thực hiện các thao tác hàng loạt với trích dẫn.

    - Xóa nhiều trích dẫn cùng lúc
    - Cập nhật trạng thái nhiều trích dẫn
    - Thêm thẻ cho nhiều trích dẫn
    """
    quote_service = QuoteService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Thao tác hàng loạt - User: {current_user.id}, Operation: {operations.operation}, IP: {client_ip}"
    )

    try:
        result = await quote_service.bulk_quote_operations(
            user_id=current_user.id,
            operation_type=operations.operation,
            quote_ids=operations.quote_ids,
            data=operations.data,
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            f"quote_bulk_{operations.operation}",
            f"Người dùng đã thực hiện thao tác hàng loạt {operations.operation} trên {len(operations.quote_ids)} trích dẫn",
            metadata={
                "user_id": current_user.id,
                "operation": operations.operation,
                "count": len(operations.quote_ids),
            },
        )

        return {"success": True, "processed": result}
    except Exception as e:
        logger.error(f"Lỗi khi thực hiện thao tác hàng loạt: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi thực hiện thao tác hàng loạt",
        )


@router.get("/my-quotes", response_model=QuoteListResponse)
@track_request_time(endpoint="list_my_quotes")
async def list_my_quotes(
    book_id: Optional[int] = Query(None, gt=0, description="ID của sách"),
    is_public: Optional[bool] = Query(
        None, description="Lọc theo trạng thái công khai"
    ),
    sort_by: str = Query("created_at", description="Sắp xếp theo trường"),
    sort_desc: bool = Query(True, description="Sắp xếp theo thứ tự giảm dần"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách trích dẫn của người dùng hiện tại.

    - Lọc theo sách, trạng thái công khai
    - Sắp xếp theo nhiều trường và hướng
    - Phân trang với skip/limit
    """
    quote_service = QuoteService(db)
    quotes, total = await quote_service.list_quotes(
        user_id=current_user.id,
        book_id=book_id,
        is_public=is_public,
        skip=skip,
        limit=limit,
        current_user_id=current_user.id,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    return {"items": quotes, "total": total}


@router.get("/{quote_id}", response_model=QuoteResponse)
@track_request_time(endpoint="get_quote")
@cache_response(ttl=3600, vary_by=["quote_id"])
async def get_quote(
    quote_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)
):
    """
    Lấy thông tin chi tiết về một trích dẫn.
    """
    quote_service = QuoteService(db)

    try:
        quote = await quote_service.get_quote(quote_id)

        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID: {quote_id}"
            )

        return quote
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin trích dẫn {quote_id}: {str(e)}")
        raise


@router.put("/{quote_id}", response_model=QuoteResponse)
@track_request_time(endpoint="update_quote")
async def update_quote(
    data: QuoteUpdate,
    quote_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin của một trích dẫn.
    """
    quote_service = QuoteService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật trích dẫn - ID: {quote_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra trích dẫn có tồn tại không
        quote = await quote_service.get_quote(quote_id)

        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID: {quote_id}"
            )

        # Kiểm tra quyền sở hữu
        if quote.user_id != current_user.id:
            raise ForbiddenException(detail="Bạn không có quyền cập nhật trích dẫn này")

        updated_quote = await quote_service.update_quote(
            current_user.id, quote_id, data.model_dump(exclude_unset=True)
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "quote_update",
            f"Người dùng đã cập nhật trích dẫn {quote_id}",
            metadata={"user_id": current_user.id, "quote_id": quote_id},
        )

        return updated_quote
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật trích dẫn {quote_id}: {str(e)}")
        raise


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_quote")
async def delete_quote(
    quote_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa một trích dẫn.
    """
    quote_service = QuoteService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa trích dẫn - ID: {quote_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra trích dẫn có tồn tại không
        quote = await quote_service.get_quote(quote_id)

        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID: {quote_id}"
            )

        # Kiểm tra quyền sở hữu
        if quote.user_id != current_user.id:
            raise ForbiddenException(detail="Bạn không có quyền xóa trích dẫn này")

        await quote_service.delete_quote(current_user.id, quote_id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "quote_delete",
            f"Người dùng đã xóa trích dẫn {quote_id}",
            metadata={"user_id": current_user.id, "quote_id": quote_id},
        )

        return None
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa trích dẫn {quote_id}: {str(e)}")
        raise


@router.post("/{quote_id}/like", response_model=QuoteResponse)
@track_request_time(endpoint="like_quote")
async def like_quote(
    quote_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Thích một trích dẫn.
    """
    quote_service = QuoteService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Thích trích dẫn - ID: {quote_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra trích dẫn có tồn tại không
        quote = await quote_service.get_quote(quote_id)

        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID: {quote_id}"
            )

        updated_quote = await quote_service.like_quote(current_user.id, quote_id)

        return updated_quote
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thích trích dẫn {quote_id}: {str(e)}")
        raise


@router.post("/{quote_id}/unlike", response_model=QuoteResponse)
@track_request_time(endpoint="unlike_quote")
async def unlike_quote(
    quote_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Bỏ thích một trích dẫn.
    """
    quote_service = QuoteService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Bỏ thích trích dẫn - ID: {quote_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra trích dẫn có tồn tại không
        quote = await quote_service.get_quote(quote_id)

        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID: {quote_id}"
            )

        updated_quote = await quote_service.unlike_quote(current_user.id, quote_id)

        return updated_quote
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi bỏ thích trích dẫn {quote_id}: {str(e)}")
        raise


@router.get("/random", response_model=QuotePublicResponse)
@track_request_time(endpoint="get_random_quote")
@cache_response(ttl=300)
async def get_random_quote(db: AsyncSession = Depends(get_db)):
    """
    Lấy một trích dẫn ngẫu nhiên.
    """
    quote_service = QuoteService(db)

    try:
        random_quote = await quote_service.get_random_quote()

        if not random_quote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không có trích dẫn nào trong hệ thống",
            )

        return random_quote
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy trích dẫn ngẫu nhiên: {str(e)}")
        raise


@router.get("/books/{book_id}/popular", response_model=List[QuotePublicResponse])
@track_request_time(endpoint="get_popular_quotes_by_book")
@cache_response(ttl=1800, vary_by=["book_id", "limit"])
async def get_popular_quotes_by_book(
    book_id: int = Path(..., gt=0),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách trích dẫn phổ biến từ một cuốn sách.
    """
    quote_service = QuoteService(db)

    try:
        popular_quotes = await quote_service.get_popular_quotes_by_book(book_id, limit)
        return popular_quotes
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách trích dẫn phổ biến của sách {book_id}: {str(e)}"
        )
        raise


@router.get("/users/{user_id}/liked", response_model=QuoteListResponse)
@track_request_time(endpoint="get_user_liked_quotes")
@cache_response(ttl=600, vary_by=["user_id", "skip", "limit"])
async def get_user_liked_quotes(
    user_id: int = Path(..., gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách trích dẫn mà người dùng đã thích.
    """
    quote_service = QuoteService(db)

    try:
        # Kiểm tra xem có phải người dùng hiện tại không để quyết định có hiển thị các trích dẫn riêng tư hay không
        include_private = current_user is not None and current_user.id == user_id

        quotes, total = await quote_service.get_user_liked_quotes(
            user_id=user_id, skip=skip, limit=limit, include_private=include_private
        )

        return {"items": quotes, "total": total}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách trích dẫn được thích bởi người dùng {user_id}: {str(e)}"
        )
        raise


@router.post("/{quote_id}/share", response_model=QuoteShareResponse)
@track_request_time(endpoint="share_quote")
async def share_quote(
    quote_id: int = Path(..., gt=0, description="ID của trích dẫn"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tạo liên kết chia sẻ cho một trích dẫn.

    - Tạo URL chia sẻ dành riêng
    - Hỗ trợ chia sẻ trên mạng xã hội
    """
    quote_service = QuoteService(db)

    try:
        # Kiểm tra trích dẫn có tồn tại không
        quote = await quote_service.get_quote(quote_id)

        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID: {quote_id}"
            )

        # Kiểm tra quyền sở hữu hoặc trạng thái công khai
        if quote.user_id != current_user.id and not quote.is_public:
            raise ForbiddenException(detail="Bạn không có quyền chia sẻ trích dẫn này")

        share_info = await quote_service.generate_share_links(quote_id)

        # Ghi nhật ký share
        audit_logger.log_activity(
            current_user.id,
            "quote_share",
            f"Người dùng đã chia sẻ trích dẫn {quote_id}",
            metadata={"user_id": current_user.id, "quote_id": quote_id},
        )

        return share_info
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo liên kết chia sẻ cho trích dẫn {quote_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo liên kết chia sẻ",
        )


@router.get("/trending", response_model=List[QuotePublicResponse])
@track_request_time(endpoint="get_trending_quotes")
@cache_response(ttl=1800)
async def get_trending_quotes(
    time_range: str = Query(
        "week",
        regex="^(day|week|month|year)$",
        description="Khoảng thời gian: day, week, month, year",
    ),
    limit: int = Query(10, ge=1, le=50, description="Số lượng trích dẫn trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách trích dẫn thịnh hành.

    - Dựa trên số lượt thích, chia sẻ
    - Lọc theo khoảng thời gian
    - Kết quả được cache để tối ưu hiệu suất
    """
    quote_service = QuoteService(db)

    try:
        trending_quotes = await quote_service.get_trending_quotes(time_range, limit)
        return trending_quotes
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách trích dẫn thịnh hành: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách trích dẫn thịnh hành",
        )


@router.get("/categories/{category_id}", response_model=QuoteListResponse)
@track_request_time(endpoint="get_quotes_by_category")
@cache_response(ttl=1800, vary_by=["category_id", "skip", "limit"])
async def get_quotes_by_category(
    category_id: int = Path(..., gt=0, description="ID của danh mục"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách trích dẫn theo danh mục sách.

    - Lọc theo danh mục sách
    - Phân trang với skip/limit
    - Kết quả được cache để tối ưu hiệu suất
    """
    quote_service = QuoteService(db)

    try:
        quotes, total = await quote_service.get_quotes_by_category(
            category_id=category_id, skip=skip, limit=limit
        )

        return {"items": quotes, "total": total}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách trích dẫn theo danh mục {category_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách trích dẫn theo danh mục",
        )
