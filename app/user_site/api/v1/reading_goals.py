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

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_user)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.reading_goal import (
    ReadingGoalResponse,
    ReadingGoalCreate,
    ReadingGoalUpdate,
    ReadingGoalListResponse,
    ReadingGoalProgressResponse,
    ReadingGoalStatsResponse,
    ReadingGoalSearchParams,
    ReadingGoalShareResponse,
)
from app.user_site.services.reading_goal_service import ReadingGoalService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    ServerException,
)

router = APIRouter()
logger = get_logger("reading_goal_api")
audit_logger = AuditLogger()


@router.post(
    "/", response_model=ReadingGoalResponse, status_code=status.HTTP_201_CREATED
)
@track_request_time(endpoint="create_reading_goal")
@invalidate_cache(namespace="reading_goals", tags=["user_goals"])
async def create_reading_goal(
    data: ReadingGoalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một mục tiêu đọc sách mới.

    Hỗ trợ nhiều loại mục tiêu như số sách đọc, số trang đọc, hoặc thời gian đọc
    trong một thời gian cụ thể (ngày, tuần, tháng, năm).
    """
    reading_goal_service = ReadingGoalService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo mục tiêu đọc sách mới - User: {current_user.id}, Goal type: {data.goal_type}, IP: {client_ip}"
    )

    try:
        # Giới hạn tốc độ tạo mục tiêu để tránh lạm dụng
        await throttle_requests(
            "create_reading_goal",
            limit=20,
            period=3600,
            current_user=current_user,
            request=request,
            db=db,
        )

        # Xác thực mục tiêu
        if data.target_value <= 0:
            raise BadRequestException(
                detail="Giá trị mục tiêu phải lớn hơn 0", code="invalid_target_value"
            )

        # Kiểm tra xem đã có mục tiêu tương tự chưa
        duplicate = await reading_goal_service.check_duplicate_goal(
            user_id=current_user.id,
            goal_type=data.goal_type,
            period_type=data.period_type,
        )

        if duplicate and data.period_type != "custom":
            raise BadRequestException(
                detail=f"Bạn đã có mục tiêu loại {data.goal_type} cho khoảng thời gian {data.period_type}",
                code="duplicate_goal",
            )

        goal = await reading_goal_service.create_reading_goal(
            current_user.id, data.model_dump()
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_goal_create",
            f"Người dùng đã tạo mục tiêu đọc sách mới - loại: {data.goal_type}",
            metadata={"user_id": current_user.id, "goal_type": data.goal_type},
        )

        return goal
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo mục tiêu đọc sách: {str(e)}")
        raise ServerException(detail="Lỗi khi tạo mục tiêu đọc sách")


@router.get("/", response_model=ReadingGoalListResponse)
@track_request_time(endpoint="list_reading_goals")
@cache_response(
    ttl=300,
    vary_by=[
        "current_user.id",
        "is_active",
        "goal_type",
        "period_type",
        "page",
        "limit",
    ],
)
async def list_reading_goals(
    is_active: Optional[bool] = Query(
        None, description="Lọc theo trạng thái hoạt động"
    ),
    goal_type: Optional[str] = Query(None, description="Lọc theo loại mục tiêu"),
    period_type: Optional[str] = Query(None, description="Lọc theo loại thời gian"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    sort_by: str = Query(
        "created_at",
        regex="^(created_at|target_date|progress)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách mục tiêu đọc sách của người dùng hiện tại với các tùy chọn lọc và sắp xếp.

    - **is_active**: Lọc theo trạng thái hoạt động (true) hoặc đã hoàn thành/hết hạn (false)
    - **goal_type**: Lọc theo loại mục tiêu (books, pages, time, categories)
    - **period_type**: Lọc theo loại thời gian (daily, weekly, monthly, yearly, custom)
    - **page**: Trang hiện tại
    - **limit**: Số lượng kết quả mỗi trang
    - **sort_by**: Sắp xếp theo trường (created_at, target_date, progress)
    - **sort_desc**: Sắp xếp giảm dần (true) hoặc tăng dần (false)
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        goals, total = await reading_goal_service.list_reading_goals(
            user_id=current_user.id,
            is_active=is_active,
            goal_type=goal_type,
            period_type=period_type,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": goals,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách mục tiêu đọc sách: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách mục tiêu đọc sách")


@router.post("/search", response_model=ReadingGoalListResponse)
@track_request_time(endpoint="search_reading_goals")
async def search_reading_goals(
    search_params: ReadingGoalSearchParams,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tìm kiếm nâng cao các mục tiêu đọc sách.

    Cho phép tìm kiếm và lọc mục tiêu theo nhiều tiêu chí như loại mục tiêu,
    thời gian, trạng thái tiến độ, và các thuộc tính khác.
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (search_params.page - 1) * search_params.limit

        # Tạo dict các tham số search
        search_dict = search_params.model_dump(exclude={"page", "limit"})
        search_dict["user_id"] = current_user.id
        search_dict["skip"] = skip
        search_dict["limit"] = search_params.limit

        goals, total = await reading_goal_service.search_reading_goals(**search_dict)

        # Tính toán tổng số trang
        total_pages = (
            (total + search_params.limit - 1) // search_params.limit if total > 0 else 0
        )

        return {
            "items": goals,
            "total": total,
            "page": search_params.page,
            "limit": search_params.limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm mục tiêu đọc sách: {str(e)}")
        raise ServerException(detail="Lỗi khi tìm kiếm mục tiêu đọc sách")


@router.get("/active", response_model=List[ReadingGoalResponse])
@track_request_time(endpoint="get_active_reading_goals")
@cache_response(ttl=300, vary_by=["current_user.id"])
async def get_active_reading_goals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách các mục tiêu đọc sách đang hoạt động.

    Chỉ trả về những mục tiêu chưa hoàn thành và chưa hết hạn.
    Được sử dụng để hiển thị nhanh mục tiêu đang theo đuổi trên dashboard.
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        active_goals = await reading_goal_service.get_active_reading_goals(
            current_user.id
        )
        return active_goals
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách mục tiêu đọc sách đang hoạt động: {str(e)}"
        )
        raise ServerException(
            detail="Lỗi khi lấy danh sách mục tiêu đọc sách đang hoạt động"
        )


@router.get("/summary", response_model=ReadingGoalStatsResponse)
@track_request_time(endpoint="get_reading_goals_summary")
@cache_response(ttl=300, vary_by=["current_user.id"])
async def get_reading_goals_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy tổng hợp thống kê về mục tiêu đọc sách của người dùng.

    Bao gồm tỷ lệ thành công, xu hướng hoàn thành theo thời gian,
    loại mục tiêu phổ biến, và các số liệu tổng hợp khác.
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        summary = await reading_goal_service.get_reading_goals_summary(current_user.id)
        return summary
    except Exception as e:
        logger.error(f"Lỗi khi lấy tổng hợp thống kê mục tiêu đọc sách: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy tổng hợp thống kê mục tiêu đọc sách")


@router.get("/recommendations", response_model=List[ReadingGoalResponse])
@track_request_time(endpoint="get_goal_recommendations")
@cache_response(ttl=3600, vary_by=["current_user.id"])
async def get_goal_recommendations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy các đề xuất mục tiêu đọc sách dựa trên thói quen đọc của người dùng.

    Hệ thống phân tích thói quen đọc và đề xuất các mục tiêu phù hợp
    để thúc đẩy người dùng đọc sách nhiều hơn.
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        recommendations = await reading_goal_service.get_goal_recommendations(
            current_user.id
        )
        return recommendations
    except Exception as e:
        logger.error(f"Lỗi khi lấy đề xuất mục tiêu đọc sách: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy đề xuất mục tiêu đọc sách")


@router.get("/{goal_id}", response_model=ReadingGoalResponse)
@track_request_time(endpoint="get_reading_goal")
@cache_response(ttl=300, vary_by=["goal_id", "current_user.id"])
async def get_reading_goal(
    goal_id: int = Path(..., gt=0, description="ID của mục tiêu đọc sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một mục tiêu đọc sách.

    Trả về thông tin đầy đủ về mục tiêu bao gồm loại, thời gian, giá trị mục tiêu,
    tiến độ hiện tại và trạng thái.
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        goal = await reading_goal_service.get_reading_goal_by_id(
            goal_id, current_user.id
        )

        if not goal:
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID: {goal_id}",
                code="goal_not_found",
            )

        return goal
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin mục tiêu đọc sách {goal_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin mục tiêu đọc sách")


@router.put("/{goal_id}", response_model=ReadingGoalResponse)
@track_request_time(endpoint="update_reading_goal")
@invalidate_cache(namespace="reading_goals", tags=["user_goals"])
async def update_reading_goal(
    data: ReadingGoalUpdate,
    goal_id: int = Path(..., gt=0, description="ID của mục tiêu đọc sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin mục tiêu đọc sách.

    Cho phép điều chỉnh các thông số của mục tiêu như giá trị mục tiêu,
    ngày bắt đầu/kết thúc, và các thuộc tính khác.
    """
    reading_goal_service = ReadingGoalService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật mục tiêu đọc sách - ID: {goal_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra mục tiêu đọc sách có tồn tại và thuộc về người dùng hiện tại không
        goal = await reading_goal_service.get_reading_goal_by_id(
            goal_id, current_user.id
        )

        if not goal:
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID: {goal_id}",
                code="goal_not_found",
            )

        # Kiểm tra xem mục tiêu đã hoàn thành chưa
        if goal.is_completed:
            raise BadRequestException(
                detail="Không thể cập nhật mục tiêu đã hoàn thành",
                code="goal_already_completed",
            )

        # Xác thực giá trị mục tiêu
        if (
            hasattr(data, "target_value")
            and data.target_value is not None
            and data.target_value <= 0
        ):
            raise BadRequestException(
                detail="Giá trị mục tiêu phải lớn hơn 0", code="invalid_target_value"
            )

        updated_goal = await reading_goal_service.update_reading_goal(
            goal_id, current_user.id, data.model_dump(exclude_unset=True)
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_goal_update",
            f"Người dùng đã cập nhật mục tiêu đọc sách {goal_id}",
            metadata={"user_id": current_user.id, "goal_id": goal_id},
        )

        return updated_goal
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật mục tiêu đọc sách {goal_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật mục tiêu đọc sách")


@router.post("/{goal_id}/progress", response_model=ReadingGoalProgressResponse)
@track_request_time(endpoint="update_reading_goal_progress")
@invalidate_cache(namespace="reading_goals", tags=["user_goals"])
async def update_reading_goal_progress(
    data: Dict[str, Any] = Body(...),
    goal_id: int = Path(..., gt=0, description="ID của mục tiêu đọc sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật tiến độ của mục tiêu đọc sách theo cách thủ công.

    Hữu ích khi người dùng muốn cập nhật tiến độ đọc sách ngoài
    hệ thống (sách giấy, ứng dụng khác, v.v.).
    """
    reading_goal_service = ReadingGoalService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật tiến độ mục tiêu đọc sách - ID: {goal_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra mục tiêu đọc sách có tồn tại và thuộc về người dùng hiện tại không
        goal = await reading_goal_service.get_reading_goal_by_id(
            goal_id, current_user.id
        )

        if not goal:
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID: {goal_id}",
                code="goal_not_found",
            )

        # Kiểm tra xem mục tiêu đã hoàn thành chưa
        if goal.is_completed:
            raise BadRequestException(
                detail="Không thể cập nhật tiến độ mục tiêu đã hoàn thành",
                code="goal_already_completed",
            )

        # Kiểm tra và xác thực giá trị tiến độ
        current_value = data.get("current_value")
        if current_value is None:
            raise BadRequestException(
                detail="Thiếu giá trị tiến độ hiện tại (current_value)",
                code="missing_current_value",
            )

        if not isinstance(current_value, (int, float)) or current_value < 0:
            raise BadRequestException(
                detail="Giá trị tiến độ phải là số không âm",
                code="invalid_current_value",
            )

        notes = data.get("notes")

        progress = await reading_goal_service.update_reading_goal_progress(
            goal_id=goal_id,
            user_id=current_user.id,
            current_value=current_value,
            notes=notes,
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_goal_progress_update",
            f"Người dùng đã cập nhật tiến độ mục tiêu đọc sách {goal_id}: {current_value}",
            metadata={
                "user_id": current_user.id,
                "goal_id": goal_id,
                "current_value": current_value,
            },
        )

        return progress
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật tiến độ mục tiêu đọc sách {goal_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật tiến độ mục tiêu đọc sách")


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_reading_goal")
@invalidate_cache(namespace="reading_goals", tags=["user_goals"])
async def delete_reading_goal(
    goal_id: int = Path(..., gt=0, description="ID của mục tiêu đọc sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa mục tiêu đọc sách.

    Xóa hoàn toàn mục tiêu và lịch sử tiến độ của nó. Thao tác này không thể hoàn tác.
    """
    reading_goal_service = ReadingGoalService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa mục tiêu đọc sách - ID: {goal_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra mục tiêu đọc sách có tồn tại và thuộc về người dùng hiện tại không
        goal = await reading_goal_service.get_reading_goal_by_id(
            goal_id, current_user.id
        )

        if not goal:
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID: {goal_id}",
                code="goal_not_found",
            )

        await reading_goal_service.delete_reading_goal(goal_id, current_user.id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_goal_delete",
            f"Người dùng đã xóa mục tiêu đọc sách {goal_id}",
            metadata={"user_id": current_user.id, "goal_id": goal_id},
        )

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa mục tiêu đọc sách {goal_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa mục tiêu đọc sách")


@router.get("/{goal_id}/progress", response_model=ReadingGoalProgressResponse)
@track_request_time(endpoint="get_reading_goal_progress")
@cache_response(ttl=300, vary_by=["goal_id", "current_user.id"])
async def get_reading_goal_progress(
    goal_id: int = Path(..., gt=0, description="ID của mục tiêu đọc sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy tiến độ của một mục tiêu đọc sách.

    Bao gồm thông tin về tiến độ hiện tại, tỷ lệ hoàn thành,
    và lịch sử tiến độ theo thời gian.
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        # Kiểm tra mục tiêu đọc sách có tồn tại và thuộc về người dùng hiện tại không
        goal = await reading_goal_service.get_reading_goal_by_id(
            goal_id, current_user.id
        )

        if not goal:
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID: {goal_id}",
                code="goal_not_found",
            )

        progress = await reading_goal_service.get_reading_goal_progress(
            goal_id, current_user.id
        )

        return progress
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy tiến độ mục tiêu đọc sách {goal_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy tiến độ mục tiêu đọc sách")


@router.post("/{goal_id}/share", response_model=ReadingGoalShareResponse)
@track_request_time(endpoint="share_reading_goal")
async def share_reading_goal(
    goal_id: int = Path(..., gt=0, description="ID của mục tiêu đọc sách"),
    privacy_level: Optional[str] = Query(
        "public", regex="^(public|followers|private)$", description="Mức độ riêng tư"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Chia sẻ mục tiêu đọc sách lên hồ sơ người dùng.

    Cho phép người dùng chia sẻ mục tiêu và tiến độ của họ với cộng đồng
    hoặc chỉ với những người theo dõi, hoặc giữ riêng tư.
    """
    reading_goal_service = ReadingGoalService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Chia sẻ mục tiêu đọc sách - ID: {goal_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra mục tiêu đọc sách có tồn tại và thuộc về người dùng hiện tại không
        goal = await reading_goal_service.get_reading_goal_by_id(
            goal_id, current_user.id
        )

        if not goal:
            raise NotFoundException(
                detail=f"Không tìm thấy mục tiêu đọc sách với ID: {goal_id}",
                code="goal_not_found",
            )

        # Xác thực mức độ riêng tư
        if privacy_level not in ["public", "followers", "private"]:
            privacy_level = "public"

        share_result = await reading_goal_service.share_reading_goal(
            goal_id=goal_id, user_id=current_user.id, privacy_level=privacy_level
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_goal_share",
            f"Người dùng đã chia sẻ mục tiêu đọc sách {goal_id} với mức độ riêng tư {privacy_level}",
            metadata={
                "user_id": current_user.id,
                "goal_id": goal_id,
                "privacy_level": privacy_level,
            },
        )

        return share_result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi chia sẻ mục tiêu đọc sách {goal_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi chia sẻ mục tiêu đọc sách")


@router.get("/public/{user_id}", response_model=List[ReadingGoalResponse])
@track_request_time(endpoint="get_public_reading_goals")
@cache_response(ttl=600, vary_by=["user_id", "current_user.id"])
async def get_public_reading_goals(
    user_id: int = Path(..., gt=0, description="ID của người dùng"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách mục tiêu đọc sách công khai của một người dùng.

    Hiển thị các mục tiêu đọc sách mà người dùng đã chia sẻ công khai
    hoặc với những người theo dõi họ.
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        # Kiểm tra người dùng có tồn tại không
        user_exists = await reading_goal_service.is_user_exists(user_id)

        if not user_exists:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID: {user_id}",
                code="user_not_found",
            )

        # Xác định mối quan hệ giữa người dùng hiện tại và người dùng được xem
        is_following = False
        viewer_id = None

        if current_user:
            viewer_id = current_user.id
            if viewer_id != user_id:
                is_following = await reading_goal_service.is_following(
                    viewer_id, user_id
                )

        public_goals = await reading_goal_service.get_public_reading_goals(
            user_id=user_id, viewer_id=viewer_id, is_following=is_following
        )

        return public_goals
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách mục tiêu đọc sách công khai của người dùng {user_id}: {str(e)}"
        )
        raise ServerException(
            detail="Lỗi khi lấy danh sách mục tiêu đọc sách công khai"
        )


@router.get("/trending", response_model=List[ReadingGoalResponse])
@track_request_time(endpoint="get_trending_goals")
@cache_response(ttl=3600, vary_by=["limit"])
async def get_trending_goals(
    limit: int = Query(10, ge=1, le=50, description="Số lượng mục tiêu trending"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách mục tiêu đọc sách đang trending.

    Hiển thị các mục tiêu đọc sách phổ biến trong cộng đồng,
    dựa trên số lượt chia sẻ, bình luận, và mức độ hoàn thành.
    """
    reading_goal_service = ReadingGoalService(db)

    try:
        trending_goals = await reading_goal_service.get_trending_goals(limit)
        return trending_goals
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách mục tiêu đọc sách trending: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách mục tiêu đọc sách trending")
