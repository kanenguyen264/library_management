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
from app.user_site.api.deps import get_current_active_user, get_current_user
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.badge import (
    BadgeResponse,
    BadgeListResponse,
    BadgeCollectionResponse,
    BadgeLeaderboardResponse,
    BadgeDisplayUpdate,
    BadgeSearchParams,
)
from app.user_site.services.badge_service import BadgeService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.core.exceptions import NotFoundException, BadRequestException, ServerException
from app.security.audit.audit_trails import AuditLogger

router = APIRouter()
logger = get_logger("badge_api")
audit_logger = AuditLogger()


@router.get("/", response_model=BadgeListResponse)
@track_request_time(endpoint="list_badges")
@cache_response(
    ttl=600,
    vary_by=["current_user.id", "category", "rarity", "page", "limit", "sort_by"],
)
async def list_badges(
    category: Optional[str] = Query(None, description="Lọc theo danh mục huy hiệu"),
    rarity: Optional[str] = Query(
        None,
        regex="^(common|uncommon|rare|epic|legendary)$",
        description="Lọc theo độ hiếm",
    ),
    earned: Optional[bool] = Query(None, description="Lọc theo trạng thái đạt được"),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    sort_by: str = Query(
        "earned_at",
        regex="^(name|earned_at|rarity|category)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách huy hiệu của người dùng hiện tại với các tùy chọn lọc và sắp xếp.

    - **category**: Lọc theo danh mục (reading, social, collection, etc.)
    - **rarity**: Lọc theo độ hiếm (common, uncommon, rare, epic, legendary)
    - **earned**: Lọc các huy hiệu đã đạt được (true) hoặc chưa đạt được (false)
    - **page**: Số trang
    - **limit**: Số lượng kết quả mỗi trang
    - **sort_by**: Sắp xếp theo trường (name, earned_at, rarity, category)
    - **sort_desc**: Sắp xếp giảm dần
    """
    badge_service = BadgeService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        badges, total = await badge_service.list_badges(
            user_id=current_user.id,
            category=category,
            rarity=rarity,
            earned=earned,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": badges,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách huy hiệu: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách huy hiệu")


@router.get("/{badge_id}", response_model=BadgeResponse)
@track_request_time(endpoint="get_badge")
@cache_response(ttl=600, vary_by=["badge_id", "current_user.id"])
async def get_badge(
    badge_id: int = Path(..., gt=0, description="ID của huy hiệu"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một huy hiệu.

    Trả về thông tin chi tiết về huy hiệu và trạng thái đạt được của người dùng hiện tại.
    """
    badge_service = BadgeService(db)

    try:
        badge = await badge_service.get_badge_by_id(
            badge_id=badge_id, user_id=current_user.id
        )

        if not badge:
            raise NotFoundException(
                detail=f"Không tìm thấy huy hiệu với ID: {badge_id}",
                code="badge_not_found",
            )

        return badge
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin huy hiệu {badge_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin huy hiệu")


@router.get("/collection/stats", response_model=dict)
@track_request_time(endpoint="get_badge_collection_stats")
@cache_response(ttl=300, vary_by=["current_user.id"])
async def get_badge_collection_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thống kê về bộ sưu tập huy hiệu của người dùng.

    Bao gồm thông tin về tổng số huy hiệu đã thu thập, phân loại theo danh mục và độ hiếm.
    """
    badge_service = BadgeService(db)

    try:
        stats = await badge_service.get_collection_stats(user_id=current_user.id)
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê bộ sưu tập huy hiệu: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thống kê bộ sưu tập huy hiệu")


@router.get("/categories", response_model=List[Dict[str, Any]])
@track_request_time(endpoint="get_badge_categories")
@cache_response(ttl=86400)  # Cache 24 giờ vì danh mục ít thay đổi
async def get_badge_categories(db: AsyncSession = Depends(get_db)):
    """
    Lấy danh sách các danh mục huy hiệu có sẵn trong hệ thống.

    Trả về thông tin chi tiết về mỗi danh mục và số lượng huy hiệu trong danh mục đó.
    """
    badge_service = BadgeService(db)

    try:
        categories = await badge_service.get_badge_categories()
        return categories
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh mục huy hiệu: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh mục huy hiệu")


@router.get("/collection", response_model=BadgeCollectionResponse)
@track_request_time(endpoint="get_badge_collection")
@cache_response(ttl=600, vary_by=["current_user.id"])
async def get_badge_collection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin tổng quan về bộ sưu tập huy hiệu của người dùng.

    Bao gồm các huy hiệu đã đạt được được tổ chức theo danh mục, huy hiệu gần nhất đạt được,
    tiến độ tổng thể và thông tin khác về bộ sưu tập.
    """
    badge_service = BadgeService(db)

    try:
        collection = await badge_service.get_badge_collection(current_user.id)
        return collection
    except Exception as e:
        logger.error(f"Lỗi khi lấy bộ sưu tập huy hiệu: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy bộ sưu tập huy hiệu")


@router.get("/leaderboard", response_model=BadgeLeaderboardResponse)
@track_request_time(endpoint="get_badge_leaderboard")
@cache_response(ttl=1800, vary_by=["category", "page", "limit"])
async def get_badge_leaderboard(
    category: Optional[str] = Query(None, description="Lọc theo danh mục huy hiệu"),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy bảng xếp hạng người dùng dựa trên số lượng và độ hiếm của huy hiệu đã thu thập.

    Nếu không chỉ định danh mục, sẽ trả về bảng xếp hạng dựa trên tất cả các huy hiệu.
    Người dùng hiện tại sẽ được đánh dấu trong kết quả nếu đã đăng nhập.
    """
    badge_service = BadgeService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        leaderboard, total, current_user_rank = (
            await badge_service.get_badge_leaderboard(
                category=category,
                skip=skip,
                limit=limit,
                current_user_id=current_user.id if current_user else None,
            )
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "users": leaderboard,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "current_user_rank": current_user_rank,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy bảng xếp hạng huy hiệu: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy bảng xếp hạng huy hiệu")


@router.put("/display", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="update_badge_display")
@invalidate_cache(namespace="badges", tags=["user_badges"])
async def update_badge_display(
    data: BadgeDisplayUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật cài đặt hiển thị huy hiệu trên hồ sơ người dùng.

    Cho phép người dùng chọn tối đa 5 huy hiệu để hiển thị trên hồ sơ công khai.
    """
    badge_service = BadgeService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật hiển thị huy hiệu - User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra số lượng huy hiệu
        if len(data.badge_ids) > 5:
            raise BadRequestException(
                detail="Chỉ có thể hiển thị tối đa 5 huy hiệu trên hồ sơ",
                code="too_many_badges",
            )

        # Kiểm tra người dùng đã đạt được các huy hiệu này chưa
        valid_badges = await badge_service.validate_user_badges(
            current_user.id, data.badge_ids
        )

        if not valid_badges:
            raise BadRequestException(
                detail="Một hoặc nhiều huy hiệu không hợp lệ hoặc chưa được đạt được",
                code="invalid_badges",
            )

        await badge_service.update_badge_display(current_user.id, data.badge_ids)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "badge_display_update",
            f"Người dùng đã cập nhật huy hiệu hiển thị",
            metadata={"user_id": current_user.id, "badge_ids": data.badge_ids},
        )

        return {
            "message": "Cập nhật hiển thị huy hiệu thành công",
            "displayed_badges": data.badge_ids,
        }
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật hiển thị huy hiệu: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật hiển thị huy hiệu")


@router.get("/rare", response_model=List[BadgeResponse])
@track_request_time(endpoint="get_rare_badges")
@cache_response(ttl=3600)  # Cache 1 giờ
async def get_rare_badges(
    limit: int = Query(10, ge=1, le=50, description="Số lượng huy hiệu trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách các huy hiệu hiếm nhất trong hệ thống.

    Sắp xếp theo tỷ lệ người dùng đạt được (thấp nhất trước). Nếu người dùng đã đăng nhập,
    kết quả sẽ bao gồm thông tin về việc họ đã đạt được huy hiệu chưa.
    """
    badge_service = BadgeService(db)

    try:
        rare_badges = await badge_service.get_rare_badges(
            limit=limit, user_id=current_user.id if current_user else None
        )
        return rare_badges
    except Exception as e:
        logger.error(f"Lỗi khi lấy huy hiệu hiếm: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy huy hiệu hiếm")


@router.get("/popular", response_model=List[BadgeResponse])
@track_request_time(endpoint="get_popular_badges")
@cache_response(ttl=3600)  # Cache 1 giờ
async def get_popular_badges(
    limit: int = Query(10, ge=1, le=50, description="Số lượng huy hiệu trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách các huy hiệu phổ biến nhất trong hệ thống.

    Sắp xếp theo tỷ lệ người dùng đạt được (cao nhất trước). Nếu người dùng đã đăng nhập,
    kết quả sẽ bao gồm thông tin về việc họ đã đạt được huy hiệu chưa.
    """
    badge_service = BadgeService(db)

    try:
        popular_badges = await badge_service.get_popular_badges(
            limit=limit, user_id=current_user.id if current_user else None
        )
        return popular_badges
    except Exception as e:
        logger.error(f"Lỗi khi lấy huy hiệu phổ biến: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy huy hiệu phổ biến")


@router.post("/search", response_model=BadgeListResponse)
@track_request_time(endpoint="search_badges")
async def search_badges(
    search_params: BadgeSearchParams,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tìm kiếm nâng cao các huy hiệu với nhiều điều kiện lọc.

    Cho phép tìm kiếm theo tên, mô tả, danh mục, độ hiếm, và các thuộc tính khác.
    """
    badge_service = BadgeService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (search_params.page - 1) * search_params.limit

        badges, total = await badge_service.search_badges(
            user_id=current_user.id,
            search_params=search_params.model_dump(exclude={"page", "limit"}),
            skip=skip,
            limit=search_params.limit,
        )

        # Tính toán tổng số trang
        total_pages = (
            (total + search_params.limit - 1) // search_params.limit if total > 0 else 0
        )

        return {
            "items": badges,
            "total": total,
            "page": search_params.page,
            "limit": search_params.limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm huy hiệu: {str(e)}")
        raise ServerException(detail="Lỗi khi tìm kiếm huy hiệu")


@router.get("/recent", response_model=List[Dict[str, Any]])
@track_request_time(endpoint="get_recent_earned_badges")
@cache_response(ttl=600, vary_by=["limit"])
async def get_recent_earned_badges(
    limit: int = Query(10, ge=1, le=50, description="Số lượng kết quả trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các huy hiệu gần đây được đạt được bởi người dùng trên hệ thống.

    Hữu ích cho feed hoạt động và tạo tính cộng đồng.
    """
    badge_service = BadgeService(db)

    try:
        recent_badges = await badge_service.get_recent_earned_badges(limit)
        return recent_badges
    except Exception as e:
        logger.error(f"Lỗi khi lấy huy hiệu gần đây: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy huy hiệu gần đây")


@router.get("/user/{user_id}", response_model=BadgeListResponse)
@track_request_time(endpoint="get_user_badges")
@cache_response(ttl=600, vary_by=["user_id", "page", "limit"])
async def get_user_badges(
    user_id: int = Path(..., gt=0, description="ID của người dùng"),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách huy hiệu đã đạt được của một người dùng cụ thể.

    Thông tin này là công khai và có thể xem bởi bất kỳ người dùng nào.
    """
    badge_service = BadgeService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        # Kiểm tra người dùng có tồn tại không
        if not await badge_service.user_exists(user_id):
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID: {user_id}",
                code="user_not_found",
            )

        badges, total = await badge_service.get_user_earned_badges(
            user_id=user_id, skip=skip, limit=limit
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": badges,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy huy hiệu của người dùng {user_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy huy hiệu của người dùng")
