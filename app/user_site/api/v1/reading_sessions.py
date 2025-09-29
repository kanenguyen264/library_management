from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
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
from app.user_site.api.v1 import throttle_requests
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_active_user
from app.user_site.models.user import User
from app.user_site.schemas.reading_session import (
    ReadingSessionCreate,
    ReadingSessionUpdate,
    ReadingSessionResponse,
    ReadingSessionListResponse,
    ReadingStatsResponse,
    ReadingGoalCreate,
    ReadingGoalResponse,
    ReadingGoalUpdate,
    ReadingSessionSearchParams,
    ReadingSessionBatchUpdate,
    ReadingDeviceStats,
)
from app.user_site.services.reading_session_service import ReadingSessionService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time, increment_counter
from app.security.audit.audit_trails import AuditLogger
from app.cache.decorators import cache_response, invalidate_cache
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    RateLimitExceededException,
)
from app.performance.performance import query_performance_tracker

router = APIRouter()
logger = get_logger("reading_session_api")
audit_logger = AuditLogger()


@router.post(
    "/", response_model=ReadingSessionResponse, status_code=status.HTTP_201_CREATED
)
@track_request_time(endpoint="create_reading_session")
@throttle_requests(max_requests=20, per_seconds=60)
async def create_reading_session(
    data: ReadingSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một phiên đọc mới.

    - Rate limiting: Giới hạn 20 request/phút để tránh quá tải
    - Validation: Kiểm tra dữ liệu đầu vào hợp lệ
    - Audit: Ghi lại hoạt động người dùng
    """
    reading_session_service = ReadingSessionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo phiên đọc mới - User: {current_user.id}, Book: {data.book_id}, IP: {client_ip}"
    )
    increment_counter("reading_sessions_created")

    try:
        # Kiểm tra sách có tồn tại không
        book_exists = await reading_session_service.is_book_exists(data.book_id)

        if not book_exists:
            raise BadRequestException(
                detail=f"Không tìm thấy sách với ID: {data.book_id}"
            )

        # Kiểm tra thời gian đọc hợp lệ
        if data.duration_minutes and data.duration_minutes > 1440:  # 24 giờ
            raise BadRequestException(
                detail="Thời gian đọc không hợp lệ. Tối đa 24 giờ (1440 phút)"
            )

        with query_performance_tracker(
            "create_reading_session",
            {"user_id": current_user.id, "book_id": data.book_id},
        ):
            session = await reading_session_service.create_reading_session(
                user_id=current_user.id, data=data.model_dump()
            )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_session_create",
            f"Người dùng đã tạo phiên đọc mới cho sách {data.book_id}",
            metadata={"user_id": current_user.id, "book_id": data.book_id},
        )

        # Hủy cache liên quan
        await invalidate_cache(f"reading_sessions:list:{current_user.id}")
        await invalidate_cache(f"reading_sessions:stats:{current_user.id}")

        return session
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo phiên đọc: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo phiên đọc",
        )


@router.get("/", response_model=ReadingSessionListResponse)
@track_request_time(endpoint="list_reading_sessions")
@cache_response(
    ttl=300,
    key_prefix="reading_sessions:list:{current_user.id}",
    vary_by=[
        "book_id",
        "date_from",
        "date_to",
        "skip",
        "limit",
        "sort_by",
        "sort_desc",
    ],
)
async def list_reading_sessions(
    book_id: Optional[int] = Query(None, gt=0, description="ID của sách"),
    date_from: Optional[datetime] = Query(None, description="Từ ngày"),
    date_to: Optional[datetime] = Query(None, description="Đến ngày"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    sort_by: str = Query(
        "created_at",
        description="Sắp xếp theo trường (created_at, duration_minutes, book_id)",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp theo thứ tự giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách phiên đọc của người dùng hiện tại.

    - Filtering: Hỗ trợ lọc theo sách, khoảng thời gian
    - Pagination: Hỗ trợ phân trang
    - Sorting: Sắp xếp kết quả theo nhiều tiêu chí khác nhau
    """
    reading_session_service = ReadingSessionService(db)

    try:
        sessions, total = await reading_session_service.list_reading_sessions(
            user_id=current_user.id,
            book_id=book_id,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        return {"items": sessions, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách phiên đọc: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách phiên đọc",
        )


@router.post("/search", response_model=ReadingSessionListResponse)
@track_request_time(endpoint="search_reading_sessions")
@throttle_requests(max_requests=15, per_seconds=60)
async def search_reading_sessions(
    params: ReadingSessionSearchParams = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tìm kiếm nâng cao trong phiên đọc.

    - Tìm kiếm theo nhiều tiêu chí: sách, thời gian, thiết bị...
    - Rate limiting: Giới hạn 15 request/phút vì đây là truy vấn phức tạp
    """
    reading_session_service = ReadingSessionService(db)

    try:
        sessions, total = await reading_session_service.search_reading_sessions(
            user_id=current_user.id, params=params
        )

        return {"items": sessions, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm phiên đọc: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tìm kiếm phiên đọc",
        )


@router.get("/stats", response_model=ReadingStatsResponse)
@track_request_time(endpoint="get_reading_stats")
@cache_response(
    ttl=3600,
    key_prefix="reading_sessions:stats:{current_user.id}",
    vary_by=["period", "date_from", "date_to"],
)
async def get_reading_stats(
    period: str = Query(
        "weekly",
        regex="^(daily|weekly|monthly|yearly|all)$",
        description="Khoảng thời gian thống kê",
    ),
    date_from: Optional[datetime] = Query(None, description="Thống kê từ ngày"),
    date_to: Optional[datetime] = Query(None, description="Thống kê đến ngày"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thống kê về hoạt động đọc sách của người dùng.

    - Thống kê theo nhiều khoảng thời gian khác nhau
    - Cache kết quả để tối ưu hiệu suất
    - Thống kê chi tiết về thời gian đọc, số sách, v.v.
    """
    reading_session_service = ReadingSessionService(db)

    try:
        if date_from and date_to and date_from > date_to:
            raise BadRequestException(detail="Ngày bắt đầu không thể sau ngày kết thúc")

        stats = await reading_session_service.get_reading_stats(
            user_id=current_user.id, period=period, date_from=date_from, date_to=date_to
        )

        return stats
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê đọc sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thống kê đọc sách",
        )


@router.get("/device-stats", response_model=ReadingDeviceStats)
@track_request_time(endpoint="get_reading_device_stats")
@cache_response(
    ttl=3600,
    key_prefix="reading_sessions:device_stats:{current_user.id}",
    vary_by=["days"],
)
async def get_reading_device_stats(
    days: int = Query(30, ge=1, le=365, description="Số ngày gần đây để thống kê"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thống kê về thiết bị đọc sách của người dùng.

    - Thời gian đọc theo từng loại thiết bị
    - Phân tích xu hướng sử dụng thiết bị
    - Thiết bị được sử dụng nhiều nhất
    """
    reading_session_service = ReadingSessionService(db)

    try:
        stats = await reading_session_service.get_reading_device_stats(
            user_id=current_user.id, days=days
        )

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê thiết bị đọc: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thống kê thiết bị đọc",
        )


@router.get("/recent", response_model=Optional[ReadingSessionResponse])
@track_request_time(endpoint="get_recent_session")
@cache_response(ttl=300, key_prefix="reading_sessions:recent:{current_user.id}")
async def get_recent_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy phiên đọc gần đây nhất của người dùng.

    - Hữu ích cho việc tiếp tục đọc
    - Cache thời gian ngắn vì dữ liệu thay đổi thường xuyên
    """
    reading_session_service = ReadingSessionService(db)

    try:
        session = await reading_session_service.get_recent_session(current_user.id)
        return session
    except Exception as e:
        logger.error(f"Lỗi khi lấy phiên đọc gần đây: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy phiên đọc gần đây",
        )


@router.get("/{session_id}", response_model=ReadingSessionResponse)
@track_request_time(endpoint="get_reading_session")
@cache_response(ttl=300, vary_by=["session_id", "current_user.id"])
async def get_reading_session(
    session_id: int = Path(..., gt=0, description="ID của phiên đọc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một phiên đọc.

    - Caching: Cache kết quả cho hiệu suất tốt hơn
    - Validation: Kiểm tra quyền truy cập
    """
    reading_session_service = ReadingSessionService(db)

    try:
        session = await reading_session_service.get_reading_session_by_id(
            session_id=session_id, user_id=current_user.id
        )

        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc với ID: {session_id}"
            )

        return session
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin phiên đọc {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin phiên đọc",
        )


@router.put("/{session_id}", response_model=ReadingSessionResponse)
@track_request_time(endpoint="update_reading_session")
@throttle_requests(max_requests=20, per_seconds=60)
async def update_reading_session(
    data: ReadingSessionUpdate,
    session_id: int = Path(..., gt=0, description="ID của phiên đọc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin phiên đọc.

    - Validation: Kiểm tra quyền cập nhật
    - Rate limiting: Giới hạn 20 request/phút
    - Audit: Ghi lại hoạt động cập nhật
    """
    reading_session_service = ReadingSessionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật phiên đọc - ID: {session_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra phiên đọc có tồn tại và thuộc về người dùng hiện tại không
        session = await reading_session_service.get_reading_session_by_id(
            session_id=session_id, user_id=current_user.id
        )

        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc với ID: {session_id}"
            )

        # Kiểm tra thời gian đọc hợp lệ
        if data.duration_minutes and data.duration_minutes > 1440:  # 24 giờ
            raise BadRequestException(
                detail="Thời gian đọc không hợp lệ. Tối đa 24 giờ (1440 phút)"
            )

        updated_session = await reading_session_service.update_reading_session(
            session_id=session_id,
            user_id=current_user.id,
            data=data.model_dump(exclude_unset=True),
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_session_update",
            f"Người dùng đã cập nhật phiên đọc {session_id}",
            metadata={"user_id": current_user.id, "session_id": session_id},
        )

        # Hủy cache liên quan
        await invalidate_cache(f"reading_sessions:list:{current_user.id}")
        await invalidate_cache(f"reading_sessions:stats:{current_user.id}")

        return updated_session
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật phiên đọc {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật phiên đọc",
        )


@router.post("/batch-update", response_model=Dict[str, Any])
@track_request_time(endpoint="batch_update_sessions")
@throttle_requests(max_requests=5, per_seconds=60)
async def batch_update_sessions(
    data: ReadingSessionBatchUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật hàng loạt các phiên đọc.

    - Hữu ích cho đồng bộ từ thiết bị offline
    - Rate limiting: Giới hạn 5 request/phút vì đây là thao tác nặng
    - Validation: Kiểm tra quyền cập nhật cho từng session
    """
    reading_session_service = ReadingSessionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật hàng loạt phiên đọc - User: {current_user.id}, Count: {len(data.sessions)}, IP: {client_ip}"
    )

    try:
        result = await reading_session_service.batch_update_sessions(
            user_id=current_user.id, sessions=data.sessions
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_session_batch_update",
            f"Người dùng đã cập nhật hàng loạt {len(data.sessions)} phiên đọc",
            metadata={"user_id": current_user.id, "count": len(data.sessions)},
        )

        # Hủy cache liên quan
        await invalidate_cache(f"reading_sessions:list:{current_user.id}")
        await invalidate_cache(f"reading_sessions:stats:{current_user.id}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật hàng loạt phiên đọc: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật hàng loạt phiên đọc",
        )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_reading_session")
async def delete_reading_session(
    session_id: int = Path(..., gt=0, description="ID của phiên đọc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa phiên đọc.

    - Validation: Kiểm tra quyền xóa
    - Audit: Ghi lại hoạt động xóa
    """
    reading_session_service = ReadingSessionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa phiên đọc - ID: {session_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra phiên đọc có tồn tại và thuộc về người dùng hiện tại không
        session = await reading_session_service.get_reading_session_by_id(
            session_id=session_id, user_id=current_user.id
        )

        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc với ID: {session_id}"
            )

        await reading_session_service.delete_reading_session(
            session_id=session_id, user_id=current_user.id
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_session_delete",
            f"Người dùng đã xóa phiên đọc {session_id}",
            metadata={"user_id": current_user.id, "session_id": session_id},
        )

        # Hủy cache liên quan
        await invalidate_cache(f"reading_sessions:list:{current_user.id}")
        await invalidate_cache(f"reading_sessions:stats:{current_user.id}")

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa phiên đọc {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa phiên đọc",
        )


@router.post(
    "/goals", response_model=ReadingGoalResponse, status_code=status.HTTP_201_CREATED
)
@track_request_time(endpoint="create_reading_goal")
async def create_reading_goal(
    data: ReadingGoalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo mục tiêu đọc sách mới.

    - Hỗ trợ mục tiêu đọc theo thời gian hoặc số sách
    - Ghi lại để theo dõi tiến độ
    """
    reading_session_service = ReadingSessionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo mục tiêu đọc sách - User: {current_user.id}, Type: {data.goal_type}, IP: {client_ip}"
    )

    try:
        # Kiểm tra mục tiêu hợp lệ
        if data.target_value <= 0:
            raise BadRequestException(detail="Giá trị mục tiêu phải lớn hơn 0")

        # Kiểm tra người dùng đã có mục tiêu cùng loại đang hoạt động chưa
        active_goal = await reading_session_service.get_active_goal(
            user_id=current_user.id, goal_type=data.goal_type
        )

        if active_goal:
            raise BadRequestException(
                detail=f"Bạn đã có mục tiêu {data.goal_type} đang hoạt động"
            )

        goal = await reading_session_service.create_reading_goal(
            user_id=current_user.id, data=data.model_dump()
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_goal_create",
            f"Người dùng đã tạo mục tiêu đọc sách loại {data.goal_type}",
            metadata={"user_id": current_user.id, "goal_type": data.goal_type},
        )

        return goal
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo mục tiêu đọc sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo mục tiêu đọc sách",
        )


@router.get("/goals", response_model=List[ReadingGoalResponse])
@track_request_time(endpoint="list_reading_goals")
@cache_response(ttl=300, key_prefix="reading_sessions:goals:{current_user.id}")
async def list_reading_goals(
    active_only: bool = Query(
        False, description="Chỉ hiển thị mục tiêu đang hoạt động"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách mục tiêu đọc sách của người dùng.

    - Hỗ trợ lọc mục tiêu đang hoạt động
    - Caching để tối ưu hiệu suất
    """
    reading_session_service = ReadingSessionService(db)

    try:
        goals = await reading_session_service.list_reading_goals(
            user_id=current_user.id, active_only=active_only
        )

        return goals
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách mục tiêu đọc sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách mục tiêu đọc sách",
        )


@router.put("/goals/{goal_id}", response_model=ReadingGoalResponse)
@track_request_time(endpoint="update_reading_goal")
async def update_reading_goal(
    data: ReadingGoalUpdate,
    goal_id: int = Path(..., gt=0, description="ID của mục tiêu đọc sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật mục tiêu đọc sách.

    - Cập nhật tiến độ, thay đổi mục tiêu
    - Validation: Kiểm tra quyền cập nhật
    """
    reading_session_service = ReadingSessionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật mục tiêu đọc sách - ID: {goal_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra mục tiêu có tồn tại và thuộc về người dùng hiện tại không
        goal = await reading_session_service.get_reading_goal_by_id(
            goal_id=goal_id, user_id=current_user.id
        )

        if not goal:
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID: {goal_id}"
            )

        # Kiểm tra mục tiêu mới hợp lệ
        if data.target_value is not None and data.target_value <= 0:
            raise BadRequestException(detail="Giá trị mục tiêu phải lớn hơn 0")

        updated_goal = await reading_session_service.update_reading_goal(
            goal_id=goal_id,
            user_id=current_user.id,
            data=data.model_dump(exclude_unset=True),
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_goal_update",
            f"Người dùng đã cập nhật mục tiêu đọc sách {goal_id}",
            metadata={"user_id": current_user.id, "goal_id": goal_id},
        )

        # Hủy cache
        await invalidate_cache(f"reading_sessions:goals:{current_user.id}")

        return updated_goal
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật mục tiêu đọc sách {goal_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật mục tiêu đọc sách",
        )


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_reading_goal")
async def delete_reading_goal(
    goal_id: int = Path(..., gt=0, description="ID của mục tiêu đọc sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa mục tiêu đọc sách.

    - Validation: Kiểm tra quyền xóa
    - Audit: Ghi lại hoạt động xóa
    """
    reading_session_service = ReadingSessionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa mục tiêu đọc sách - ID: {goal_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra mục tiêu có tồn tại và thuộc về người dùng hiện tại không
        goal = await reading_session_service.get_reading_goal_by_id(
            goal_id=goal_id, user_id=current_user.id
        )

        if not goal:
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID: {goal_id}"
            )

        await reading_session_service.delete_reading_goal(
            goal_id=goal_id, user_id=current_user.id
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_goal_delete",
            f"Người dùng đã xóa mục tiêu đọc sách {goal_id}",
            metadata={"user_id": current_user.id, "goal_id": goal_id},
        )

        # Hủy cache
        await invalidate_cache(f"reading_sessions:goals:{current_user.id}")

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa mục tiêu đọc sách {goal_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa mục tiêu đọc sách",
        )
