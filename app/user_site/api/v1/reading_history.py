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
from app.user_site.api.v1 import throttle_requests
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_active_user
from app.user_site.models.user import User
from app.user_site.schemas.reading_history import (
    ReadingHistoryCreate,
    ReadingHistoryUpdate,
    ReadingHistoryResponse,
    ReadingHistoryListResponse,
    ReadingHistoryStats,
    ReadingHistorySearchParams,
    ReadingHistorySyncRequest,
    ReadingProgressReport,
)
from app.user_site.services.reading_history_service import ReadingHistoryService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time, increment_counter
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    RateLimitExceededException,
)
from app.performance.performance import query_performance_tracker

router = APIRouter()
logger = get_logger("reading_history_api")
audit_logger = AuditLogger()


@router.post(
    "/", response_model=ReadingHistoryResponse, status_code=status.HTTP_201_CREATED
)
@track_request_time(endpoint="record_reading_history")
@throttle_requests(max_requests=30, per_seconds=60)
async def record_reading_history(
    data: ReadingHistoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Ghi lại hoặc cập nhật lịch sử đọc.

    - Rate limiting: Giới hạn 30 request/phút để tránh quá tải
    - Validation: Kiểm tra sách và chương có tồn tại
    - Audit: Ghi lại hoạt động người dùng
    """
    reading_history_service = ReadingHistoryService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Ghi lại lịch sử đọc - User: {current_user.id}, Book: {data.book_id}, Chapter: {data.chapter_id if hasattr(data, 'chapter_id') else 'None'}, IP: {client_ip}"
    )
    increment_counter("reading_history_recorded")

    try:
        # Kiểm tra sách có tồn tại không
        book_exists = await reading_history_service.is_book_exists(data.book_id)

        if not book_exists:
            raise BadRequestException(
                detail=f"Không tìm thấy sách với ID: {data.book_id}"
            )

        # Kiểm tra chapter có tồn tại không (nếu có)
        if hasattr(data, "chapter_id") and data.chapter_id:
            chapter_exists = await reading_history_service.is_chapter_exists(
                data.chapter_id, data.book_id
            )

            if not chapter_exists:
                raise BadRequestException(
                    detail=f"Không tìm thấy chương với ID: {data.chapter_id} trong sách ID: {data.book_id}"
                )

        # Hiệu suất: Sử dụng with để tracking
        with query_performance_tracker(
            "record_reading_history",
            {"user_id": current_user.id, "book_id": data.book_id},
        ):
            history = await reading_history_service.record_reading_history(
                current_user.id, data.model_dump()
            )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_history_record",
            f"Người dùng đã ghi lại lịch sử đọc sách {data.book_id}",
            metadata={"user_id": current_user.id, "book_id": data.book_id},
        )

        # Hủy cache cho list_reading_history và get_recent_reading
        await invalidate_cache(f"reading_history:list:{current_user.id}")
        await invalidate_cache(f"reading_history:recent:{current_user.id}")

        return history
    except BadRequestException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi ghi lại lịch sử đọc: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi ghi lại lịch sử đọc",
        )


@router.get("/", response_model=ReadingHistoryListResponse)
@track_request_time(endpoint="list_reading_history")
@cache_response(
    ttl=300,
    key_prefix="reading_history:list:{current_user.id}",
    vary_by=[
        "skip",
        "limit",
        "book_id",
        "from_date",
        "to_date",
        "sort_by",
        "sort_desc",
    ],
)
async def list_reading_history(
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    book_id: Optional[int] = Query(None, gt=0, description="Lọc theo ID sách"),
    from_date: Optional[datetime] = Query(None, description="Lọc từ ngày"),
    to_date: Optional[datetime] = Query(None, description="Lọc đến ngày"),
    sort_by: str = Query(
        "last_read", description="Sắp xếp theo (last_read, created_at, progress)"
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách lịch sử đọc của người dùng hiện tại.

    - Caching: Lưu cache để tối ưu hiệu suất
    - Filtering: Hỗ trợ lọc theo sách, khoảng thời gian
    - Sorting: Hỗ trợ sắp xếp theo nhiều trường và hướng
    """
    reading_history_service = ReadingHistoryService(db)

    try:
        histories, total = await reading_history_service.list_reading_history(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            book_id=book_id,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        return {"items": histories, "total": total}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách lịch sử đọc cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách lịch sử đọc",
        )


@router.post("/search", response_model=ReadingHistoryListResponse)
@track_request_time(endpoint="search_reading_history")
@throttle_requests(max_requests=15, per_seconds=60)
async def search_reading_history(
    params: ReadingHistorySearchParams = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tìm kiếm trong lịch sử đọc với nhiều tiêu chí.

    - Tìm kiếm nâng cao: Theo sách, chương, thời gian
    - Rate limiting: Giới hạn 15 request/phút vì đây là truy vấn phức tạp
    """
    reading_history_service = ReadingHistoryService(db)

    try:
        histories, total = await reading_history_service.search_reading_history(
            user_id=current_user.id, params=params
        )

        return {"items": histories, "total": total}
    except Exception as e:
        logger.error(
            f"Lỗi khi tìm kiếm lịch sử đọc cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tìm kiếm lịch sử đọc",
        )


@router.get("/recent", response_model=Optional[ReadingHistoryResponse])
@track_request_time(endpoint="get_recent_reading")
@cache_response(ttl=60, key_prefix="reading_history:recent:{current_user.id}")
async def get_recent_reading(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy lịch sử đọc gần đây nhất.

    - Cache thời gian ngắn (60s) vì dữ liệu hay thay đổi
    - Tracking hiệu suất để tối ưu
    """
    reading_history_service = ReadingHistoryService(db)

    try:
        recent_history = await reading_history_service.get_recent_reading(
            current_user.id
        )
        return recent_history
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy lịch sử đọc gần đây nhất cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy lịch sử đọc gần đây nhất",
        )


@router.get("/stats", response_model=ReadingHistoryStats)
@track_request_time(endpoint="get_reading_statistics")
@cache_response(
    ttl=3600,
    key_prefix="reading_history:stats:{current_user.id}",
    vary_by=["period", "from_date", "to_date"],
)
async def get_reading_statistics(
    period: str = Query(
        "all", description="Khoảng thời gian: day, week, month, year, all"
    ),
    from_date: Optional[datetime] = Query(None, description="Thống kê từ ngày"),
    to_date: Optional[datetime] = Query(None, description="Thống kê đến ngày"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thống kê về hoạt động đọc sách.

    - Tổng số phút đọc
    - Số sách đã đọc, đang đọc, đã hoàn thành
    - Số chương đã đọc
    - Thời gian đọc trung bình
    """
    reading_history_service = ReadingHistoryService(db)

    try:
        stats = await reading_history_service.get_reading_statistics(
            user_id=current_user.id, period=period, from_date=from_date, to_date=to_date
        )

        return stats
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thống kê đọc sách cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thống kê đọc sách",
        )


@router.get("/books/{book_id}", response_model=Optional[ReadingHistoryResponse])
@track_request_time(endpoint="get_book_reading_history")
@cache_response(ttl=300, vary_by=["book_id", "current_user.id"])
async def get_book_reading_history(
    book_id: int = Path(..., gt=0, description="ID của sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy lịch sử đọc của một cuốn sách cụ thể.

    - Cache kết quả để tối ưu hiệu suất
    - Tracking hiệu suất
    """
    reading_history_service = ReadingHistoryService(db)

    try:
        # Kiểm tra sách có tồn tại không
        book_exists = await reading_history_service.is_book_exists(book_id)

        if not book_exists:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID: {book_id}")

        book_history = await reading_history_service.get_book_reading_history(
            user_id=current_user.id, book_id=book_id
        )

        return book_history
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy lịch sử đọc sách {book_id} cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy lịch sử đọc sách",
        )


@router.get("/{history_id}", response_model=ReadingHistoryResponse)
@track_request_time(endpoint="get_reading_history")
@cache_response(ttl=300, vary_by=["history_id", "current_user.id"])
async def get_reading_history(
    history_id: int = Path(..., gt=0, description="ID của lịch sử đọc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một lịch sử đọc.

    - Cache kết quả để tối ưu hiệu suất
    - Validation: Kiểm tra quyền truy cập
    """
    reading_history_service = ReadingHistoryService(db)

    try:
        history = await reading_history_service.get_reading_history_by_id(
            history_id, current_user.id
        )

        if not history:
            raise NotFoundException(
                detail=f"Không tìm thấy lịch sử đọc với ID: {history_id} hoặc bạn không có quyền xem"
            )

        return history
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thông tin lịch sử đọc {history_id} cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin lịch sử đọc",
        )


@router.delete("/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_reading_history")
@throttle_requests(max_requests=20, per_seconds=60)
async def delete_reading_history(
    history_id: int = Path(..., gt=0, description="ID của lịch sử đọc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa lịch sử đọc.

    - Validation: Kiểm tra quyền xóa
    - Rate limiting: Giới hạn 20 request/phút
    - Audit: Ghi lại hoạt động xóa
    """
    reading_history_service = ReadingHistoryService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa lịch sử đọc - ID: {history_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra lịch sử đọc có tồn tại và thuộc người dùng hiện tại
        history = await reading_history_service.get_reading_history_by_id(
            history_id, current_user.id
        )

        if not history:
            raise NotFoundException(
                detail=f"Không tìm thấy lịch sử đọc với ID: {history_id} hoặc bạn không có quyền xóa"
            )

        await reading_history_service.delete_reading_history(
            history_id, current_user.id
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_history_delete",
            f"Người dùng đã xóa lịch sử đọc {history_id}",
            metadata={"user_id": current_user.id, "history_id": history_id},
        )

        # Hủy cache cho list_reading_history
        await invalidate_cache(f"reading_history:list:{current_user.id}")

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi xóa lịch sử đọc {history_id} cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa lịch sử đọc",
        )


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="clear_reading_history")
@throttle_requests(max_requests=5, per_seconds=60)
async def clear_reading_history(
    book_id: Optional[int] = Query(
        None, gt=0, description="ID sách để xóa lịch sử (nếu không có sẽ xóa tất cả)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa tất cả lịch sử đọc của người dùng hiện tại.

    - Rate limiting: Giới hạn 5 request/phút vì đây là thao tác nặng
    - Hỗ trợ xóa theo sách hoặc xóa tất cả
    - Audit: Ghi lại hoạt động xóa
    """
    reading_history_service = ReadingHistoryService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa tất cả lịch sử đọc - User: {current_user.id}, Book: {book_id}, IP: {client_ip}"
    )

    try:
        if book_id:
            # Kiểm tra sách có tồn tại không
            book_exists = await reading_history_service.is_book_exists(book_id)

            if not book_exists:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID: {book_id}")

            await reading_history_service.clear_book_reading_history(
                current_user.id, book_id
            )

            # Ghi nhật ký audit
            audit_logger.log_activity(
                current_user.id,
                "reading_history_clear_book",
                f"Người dùng đã xóa tất cả lịch sử đọc của sách {book_id}",
                metadata={"user_id": current_user.id, "book_id": book_id},
            )
        else:
            await reading_history_service.clear_reading_history(current_user.id)

            # Ghi nhật ký audit
            audit_logger.log_activity(
                current_user.id,
                "reading_history_clear_all",
                f"Người dùng đã xóa tất cả lịch sử đọc",
                metadata={"user_id": current_user.id},
            )

        # Hủy tất cả cache liên quan
        await invalidate_cache(f"reading_history:list:{current_user.id}")
        await invalidate_cache(f"reading_history:recent:{current_user.id}")
        await invalidate_cache(f"reading_history:stats:{current_user.id}")

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi xóa tất cả lịch sử đọc cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa tất cả lịch sử đọc",
        )


@router.put("/{history_id}", response_model=ReadingHistoryResponse)
@track_request_time(endpoint="update_reading_history")
@throttle_requests(max_requests=20, per_seconds=60)
async def update_reading_history(
    data: ReadingHistoryUpdate,
    history_id: int = Path(..., gt=0, description="ID của lịch sử đọc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin lịch sử đọc.

    - Validation: Kiểm tra quyền cập nhật
    - Rate limiting: Giới hạn 20 request/phút
    - Audit: Ghi lại hoạt động cập nhật
    """
    reading_history_service = ReadingHistoryService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật lịch sử đọc - ID: {history_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra lịch sử đọc có tồn tại và thuộc người dùng hiện tại
        history = await reading_history_service.get_reading_history_by_id(
            history_id, current_user.id
        )

        if not history:
            raise NotFoundException(
                detail=f"Không tìm thấy lịch sử đọc với ID: {history_id} hoặc bạn không có quyền cập nhật"
            )

        updated_history = await reading_history_service.update_reading_history(
            history_id, current_user.id, data.model_dump(exclude_unset=True)
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_history_update",
            f"Người dùng đã cập nhật lịch sử đọc {history_id}",
            metadata={"user_id": current_user.id, "history_id": history_id},
        )

        # Hủy cache cho list_reading_history và recent_reading
        await invalidate_cache(f"reading_history:list:{current_user.id}")
        await invalidate_cache(f"reading_history:recent:{current_user.id}")

        return updated_history
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật lịch sử đọc {history_id} cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật lịch sử đọc",
        )


@router.post("/sync", response_model=List[ReadingHistoryResponse])
@track_request_time(endpoint="sync_reading_history")
@throttle_requests(max_requests=5, per_seconds=60)
async def sync_reading_history(
    data: ReadingHistorySyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Đồng bộ lịch sử đọc từ thiết bị offline.

    - Dành cho ứng dụng di động và đọc offline
    - Rate limiting: Giới hạn 5 request/phút vì đây là thao tác nặng
    """
    reading_history_service = ReadingHistoryService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Đồng bộ lịch sử đọc - User: {current_user.id}, Records: {len(data.records)}, IP: {client_ip}"
    )

    try:
        synced_records = await reading_history_service.sync_reading_history(
            user_id=current_user.id, records=data.records
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_history_sync",
            f"Người dùng đã đồng bộ {len(data.records)} bản ghi lịch sử đọc",
            metadata={"user_id": current_user.id, "record_count": len(data.records)},
        )

        # Hủy cache cho list_reading_history và recent_reading
        await invalidate_cache(f"reading_history:list:{current_user.id}")
        await invalidate_cache(f"reading_history:recent:{current_user.id}")

        return synced_records
    except Exception as e:
        logger.error(
            f"Lỗi khi đồng bộ lịch sử đọc cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi đồng bộ lịch sử đọc",
        )


@router.get("/progress/report", response_model=ReadingProgressReport)
@track_request_time(endpoint="get_reading_progress_report")
@cache_response(
    ttl=3600,
    key_prefix="reading_history:progress:{current_user.id}",
    vary_by=["period"],
)
async def get_reading_progress_report(
    period: str = Query(
        "month", description="Khoảng thời gian: week, month, year, all"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy báo cáo tiến độ đọc sách theo thời gian.

    - Thống kê số phút đọc theo ngày
    - Tính toán mục tiêu đọc và hoàn thành mục tiêu
    - So sánh với thời kỳ trước đó
    """
    reading_history_service = ReadingHistoryService(db)

    try:
        report = await reading_history_service.get_reading_progress_report(
            user_id=current_user.id, period=period
        )

        return report
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy báo cáo tiến độ đọc cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy báo cáo tiến độ đọc",
        )
