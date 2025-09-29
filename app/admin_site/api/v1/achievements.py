from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Path,
    Body,
    Request,
)
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    secure_admin_access,
)
from app.admin_site.models import Admin, Achievement
from app.admin_site.schemas.achievement import (
    AchievementCreate,
    AchievementUpdate,
    AchievementInfo,
)
from app.admin_site.services.achievement_service import (
    get_all_achievements,
    count_achievements,
    get_achievement_by_id,
    create_achievement,
    update_achievement,
    delete_achievement,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/achievements - Lấy danh sách thành tựu
# GET /api/v1/admin/achievements/{id} - Lấy thông tin chi tiết thành tựu
# POST /api/v1/admin/achievements - Tạo thành tựu mới
# PUT /api/v1/admin/achievements/{id} - Cập nhật thông tin thành tựu
# DELETE /api/v1/admin/achievements/{id} - Xóa thành tựu


@router.get("", response_model=List[AchievementInfo])
@profile_endpoint(name="admin:achievements:list")
@cached(ttl=300, namespace="admin:achievements", key_prefix="achievement_list")
@log_admin_action(
    action="view", resource_type="achievement", description="Xem danh sách thành tựu"
)
async def read_achievements(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên"),
    difficulty_level: Optional[str] = Query(None, description="Lọc theo độ khó"),
    is_active: Optional[bool] = Query(
        None, description="Lọc theo trạng thái kích hoạt"
    ),
    current_admin: Admin = Depends(secure_admin_access(["achievement:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[AchievementInfo]:
    """
    Lấy danh sách thành tựu.

    **Quyền yêu cầu**: `achievement:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Tìm kiếm với tham số search
    - Lọc theo độ khó với tham số difficulty_level
    - Lọc theo trạng thái kích hoạt với tham số is_active

    **Kết quả**:
    - Danh sách thành tựu
    """
    achievements = get_all_achievements(
        db, skip, limit, search, difficulty_level, is_active
    )

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(achievements)} thành tựu"
    )

    return achievements


@router.get("/{id}", response_model=AchievementInfo)
@profile_endpoint(name="admin:achievements:detail")
@cached(ttl=300, namespace="admin:achievements", key_prefix="achievement_detail")
@log_admin_action(action="view", resource_type="achievement", resource_id="{id}")
async def read_achievement(
    id: int = Path(..., ge=1, description="ID thành tựu"),
    current_admin: Admin = Depends(secure_admin_access(["achievement:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> AchievementInfo:
    """
    Lấy thông tin chi tiết thành tựu.

    **Quyền yêu cầu**: `achievement:read`

    **Cách sử dụng**:
    - Cung cấp ID thành tựu cần xem

    **Kết quả**:
    - Thông tin chi tiết thành tựu
    """
    achievement = get_achievement_by_id(db, id)

    if not achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thành tựu không tồn tại"
        )

    logger.info(f"Admin {current_admin.username} đã xem thông tin thành tựu ID={id}")

    return achievement


@router.post("", response_model=AchievementInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:achievements:create")
@invalidate_cache(namespace="admin:achievements")
@log_admin_action(
    action="create", resource_type="achievement", description="Tạo thành tựu mới"
)
async def create_new_achievement(
    achievement_data: AchievementCreate,
    current_admin: Admin = Depends(secure_admin_access(["achievement:create"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> AchievementInfo:
    """
    Tạo thành tựu mới.

    **Quyền yêu cầu**: `achievement:create`

    **Cách sử dụng**:
    - Cung cấp thông tin thành tựu trong body

    **Kết quả**:
    - Thông tin thành tựu đã tạo
    """
    # Tạo thành tựu mới
    try:
        new_achievement = create_achievement(db, achievement_data)
        logger.info(
            f"Admin {current_admin.username} đã tạo thành tựu mới: {new_achievement.name}"
        )
        return new_achievement
    except ValueError as e:
        logger.error(f"Lỗi khi tạo thành tựu mới: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=AchievementInfo)
@profile_endpoint(name="admin:achievements:update")
@invalidate_cache(namespace="admin:achievements")
@log_admin_action(action="update", resource_type="achievement", resource_id="{id}")
async def update_achievement_info(
    id: int = Path(..., ge=1, description="ID thành tựu"),
    achievement_data: AchievementUpdate = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["achievement:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> AchievementInfo:
    """
    Cập nhật thông tin thành tựu.

    **Quyền yêu cầu**: `achievement:update`

    **Cách sử dụng**:
    - Cung cấp ID thành tựu cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin thành tựu đã cập nhật
    """
    # Kiểm tra thành tựu tồn tại
    achievement = get_achievement_by_id(db, id)

    if not achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thành tựu không tồn tại"
        )

    # Cập nhật thành tựu
    try:
        updated_achievement = update_achievement(db, id, achievement_data)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật thông tin thành tựu ID={id}"
        )
        return updated_achievement
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật thành tựu ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:achievements:delete")
@invalidate_cache(namespace="admin:achievements")
@log_admin_action(action="delete", resource_type="achievement", resource_id="{id}")
async def delete_achievement_item(
    id: int = Path(..., ge=1, description="ID thành tựu"),
    current_admin: Admin = Depends(secure_admin_access(["achievement:delete"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> None:
    """
    Xóa thành tựu.

    **Quyền yêu cầu**: `achievement:delete`

    **Cách sử dụng**:
    - Cung cấp ID thành tựu cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra thành tựu tồn tại
    achievement = get_achievement_by_id(db, id)

    if not achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thành tựu không tồn tại"
        )

    # Xóa thành tựu
    deleted = delete_achievement(db, id)

    if not deleted:
        logger.error(f"Không thể xóa thành tựu ID={id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể xóa thành tựu",
        )

    logger.info(f"Admin {current_admin.username} đã xóa thành tựu {achievement.name}")
