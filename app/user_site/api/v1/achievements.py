from typing import List, Optional, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    status,
    HTTPException,
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
from app.user_site.schemas.achievement import (
    AchievementResponse,
    AchievementListResponse,
    AchievementProgressResponse,
    AchievementCategoryResponse,
    AchievementTrackRequest,
)
from app.user_site.services.achievement_service import AchievementService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.core.exceptions import NotFoundException, ForbiddenException, ServerException
from app.security.audit.audit_trails import AuditLogger

router = APIRouter()
logger = get_logger("achievement_api")
audit_logger = AuditLogger()


@router.get("/", response_model=AchievementListResponse)
@track_request_time(endpoint="list_achievements")
@cache_response(
    ttl=300,
    vary_by=["current_user.id", "category", "status", "page", "limit", "sort_by"],
)
async def list_achievements(
    category: Optional[str] = Query(None, description="Lọc theo danh mục thành tựu"),
    status: Optional[str] = Query(
        None,
        regex="^(completed|in_progress|locked)$",
        description="Lọc theo trạng thái thành tựu",
    ),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    sort_by: str = Query(
        "updated_at",
        regex="^(updated_at|created_at|progress|rarity)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách thành tựu của người dùng hiện tại với các tùy chọn lọc và sắp xếp.

    - **category**: Lọc theo danh mục (reading, social, collection, etc.)
    - **status**: Lọc theo trạng thái (completed, in_progress, locked)
    - **page**: Số trang
    - **limit**: Số lượng kết quả mỗi trang
    - **sort_by**: Sắp xếp theo trường (updated_at, created_at, progress, rarity)
    - **sort_desc**: Sắp xếp giảm dần
    """
    achievement_service = AchievementService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        achievements, total = await achievement_service.list_achievements(
            user_id=current_user.id,
            category=category,
            status=status,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": achievements,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thành tựu: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách thành tựu")


@router.get("/{achievement_id}", response_model=AchievementResponse)
@track_request_time(endpoint="get_achievement")
@cache_response(ttl=300, vary_by=["achievement_id", "current_user.id"])
async def get_achievement(
    achievement_id: int = Path(..., gt=0, description="ID của thành tựu"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một thành tựu, bao gồm tiến độ và trạng thái.

    Cung cấp thông tin chi tiết về các điều kiện để đạt được thành tựu và tiến độ hiện tại của người dùng.
    """
    achievement_service = AchievementService(db)

    try:
        achievement = await achievement_service.get_achievement_by_id(
            achievement_id=achievement_id, user_id=current_user.id
        )

        if not achievement:
            raise NotFoundException(
                detail=f"Không tìm thấy thành tựu với ID: {achievement_id}",
                code="achievement_not_found",
            )

        return achievement
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin thành tựu {achievement_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin thành tựu")


@router.get("/categories", response_model=List[AchievementCategoryResponse])
@track_request_time(endpoint="get_achievement_categories")
@cache_response(ttl=86400)  # Cache 24 giờ vì danh mục ít thay đổi
async def get_achievement_categories(db: AsyncSession = Depends(get_db)):
    """
    Lấy danh sách các danh mục thành tựu có sẵn trong hệ thống.

    Bao gồm thông tin chi tiết về mỗi danh mục và tổng số thành tựu trong danh mục đó.
    """
    achievement_service = AchievementService(db)

    try:
        categories = await achievement_service.get_achievement_categories()
        return categories
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh mục thành tựu: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh mục thành tựu")


@router.get("/progress", response_model=AchievementProgressResponse)
@track_request_time(endpoint="get_achievement_progress")
@cache_response(ttl=300, vary_by=["current_user.id"])
async def get_achievement_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin tổng quan về tiến độ thành tựu của người dùng.

    Bao gồm tổng số thành tựu đã đạt được, đang tiến hành và còn khóa,
    cùng với % hoàn thành và chi tiết theo từng danh mục.
    """
    achievement_service = AchievementService(db)

    try:
        progress = await achievement_service.get_achievement_progress(current_user.id)
        return progress
    except Exception as e:
        logger.error(f"Lỗi khi lấy tiến độ thành tựu: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy tiến độ thành tựu")


@router.post("/track", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="track_achievement_progress")
@invalidate_cache(namespace="achievements", tags=["user_achievements"])
async def track_achievement_progress(
    data: AchievementTrackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật tiến độ thành tựu khi người dùng thực hiện các hành động.

    Client có thể gửi các sự kiện như 'book_read', 'chapter_completed', 'days_streak' để cập nhật tiến độ.
    Hệ thống sẽ kiểm tra và cập nhật tất cả các thành tựu liên quan, trả về thông tin thành tựu mới đạt được (nếu có).
    """
    achievement_service = AchievementService(db)

    try:
        # Giới hạn tốc độ gửi sự kiện thành tựu
        await throttle_requests(
            "track_achievement",
            limit=50,
            period=60,
            current_user=current_user,
            request=request,
            db=db,
        )

        result = await achievement_service.track_achievement_progress(
            user_id=current_user.id,
            action_type=data.action_type,
            action_value=data.action_value,
            metadata=data.metadata,
        )

        # Ghi nhật ký
        client_ip = request.client.host if request and request.client else "unknown"
        logger.info(
            f"Cập nhật tiến độ thành tựu - User: {current_user.id}, Action: {data.action_type}, IP: {client_ip}"
        )

        # Ghi audit log nếu đạt được thành tựu mới
        if result.get("new_achievements"):
            for achievement in result["new_achievements"]:
                audit_logger.log_activity(
                    current_user.id,
                    "achievement_unlocked",
                    f"Người dùng đã đạt được thành tựu: {achievement['title']}",
                    metadata={
                        "user_id": current_user.id,
                        "achievement_id": achievement["id"],
                        "achievement_title": achievement["title"],
                    },
                )

        return result
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật tiến độ thành tựu: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật tiến độ thành tựu")


@router.get("/popular", response_model=List[AchievementResponse])
@track_request_time(endpoint="get_popular_achievements")
@cache_response(ttl=3600)  # Cache 1 giờ
async def get_popular_achievements(
    limit: int = Query(10, ge=1, le=50, description="Số lượng thành tựu trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các thành tựu phổ biến nhất (được đạt được nhiều nhất).

    Hữu ích cho việc hiển thị thống kê và tạo động lực cho người dùng.
    """
    achievement_service = AchievementService(db)

    try:
        achievements = await achievement_service.get_popular_achievements(limit)
        return achievements
    except Exception as e:
        logger.error(f"Lỗi khi lấy thành tựu phổ biến: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thành tựu phổ biến")


@router.get("/rare", response_model=List[AchievementResponse])
@track_request_time(endpoint="get_rare_achievements")
@cache_response(ttl=3600)  # Cache 1 giờ
async def get_rare_achievements(
    limit: int = Query(10, ge=1, le=50, description="Số lượng thành tựu trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các thành tựu hiếm nhất (được đạt được ít nhất).

    Hữu ích cho việc giới thiệu các thử thách khó cho người dùng.
    """
    achievement_service = AchievementService(db)

    try:
        achievements = await achievement_service.get_rare_achievements(limit)
        return achievements
    except Exception as e:
        logger.error(f"Lỗi khi lấy thành tựu hiếm: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thành tựu hiếm")


@router.get("/recent", response_model=List[Dict[str, Any]])
@track_request_time(endpoint="get_recent_unlocked_achievements")
@cache_response(ttl=300, vary_by=["limit"])
async def get_recent_unlocked_achievements(
    limit: int = Query(10, ge=1, le=50, description="Số lượng kết quả trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các thành tựu gần đây được mở khóa bởi người dùng trên hệ thống.

    Hữu ích cho feed hoạt động và tạo tính cộng đồng.
    """
    achievement_service = AchievementService(db)

    try:
        recent_achievements = (
            await achievement_service.get_recent_unlocked_achievements(limit)
        )
        return recent_achievements
    except Exception as e:
        logger.error(f"Lỗi khi lấy thành tựu gần đây: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thành tựu gần đây")


@router.get("/user/{user_id}", response_model=AchievementListResponse)
@track_request_time(endpoint="get_user_achievements")
@cache_response(ttl=600, vary_by=["user_id", "page", "limit"])
async def get_user_achievements(
    user_id: int = Path(..., gt=0, description="ID của người dùng"),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách thành tựu đã đạt được của một người dùng cụ thể.

    Thông tin này là công khai và có thể xem bởi bất kỳ người dùng nào.
    Chỉ hiển thị các thành tựu đã hoàn thành, không hiển thị tiến độ.
    """
    achievement_service = AchievementService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        # Kiểm tra người dùng có tồn tại không
        if not await achievement_service.user_exists(user_id):
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID: {user_id}",
                code="user_not_found",
            )

        achievements, total = await achievement_service.get_user_completed_achievements(
            user_id=user_id, skip=skip, limit=limit
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": achievements,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thành tựu của người dùng {user_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thành tựu của người dùng")
