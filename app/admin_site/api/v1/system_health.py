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
from datetime import date

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    secure_admin_access,
)
from app.admin_site.models import Admin
from app.admin_site.schemas.system_health import (
    SystemHealthCreate,
    SystemHealthUpdate,
    SystemHealthInfo,
)
from app.admin_site.services.system_health_service import (
    get_all_system_health,
    count_system_health,
    get_system_health_by_id,
    create_system_health,
    update_system_health,
    delete_system_health,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/system-health - Lấy danh sách trạng thái sức khỏe hệ thống
# GET /api/v1/admin/system-health/{id} - Lấy thông tin chi tiết trạng thái
# POST /api/v1/admin/system-health - Tạo trạng thái mới
# PUT /api/v1/admin/system-health/{id} - Cập nhật thông tin trạng thái
# DELETE /api/v1/admin/system-health/{id} - Xóa trạng thái


@router.get("", response_model=List[SystemHealthInfo])
@profile_endpoint(name="admin:system_health:list")
@cached(ttl=300, namespace="admin:system_health", key_prefix="health_list")
@log_admin_action(
    action="view",
    resource_type="system_health",
    description="Xem danh sách trạng thái hệ thống",
)
async def read_system_health_list(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    component: Optional[str] = Query(None, description="Lọc theo thành phần"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái"),
    start_date: Optional[date] = Query(None, description="Ngày bắt đầu"),
    end_date: Optional[date] = Query(None, description="Ngày kết thúc"),
    current_admin: Admin = Depends(secure_admin_access(["system_health:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[SystemHealthInfo]:
    """
    Lấy danh sách trạng thái hệ thống.

    **Quyền yêu cầu**: `system_health:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Lọc theo thành phần với tham số component
    - Lọc theo trạng thái với tham số status
    - Lọc theo khoảng thời gian với start_date và end_date

    **Kết quả**:
    - Danh sách trạng thái hệ thống
    """
    if start_date and end_date and start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng truy vấn với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    health_statuses = get_all_system_health(
        db, skip, limit, component, status, start_date, end_date
    )

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(health_statuses)} trạng thái hệ thống"
    )

    return health_statuses


@router.get("/{id}", response_model=SystemHealthInfo)
@profile_endpoint(name="admin:system_health:detail")
@cached(ttl=300, namespace="admin:system_health", key_prefix="health_detail")
@log_admin_action(action="view", resource_type="system_health", resource_id="{id}")
async def read_system_health(
    id: int = Path(..., ge=1, description="ID trạng thái"),
    current_admin: Admin = Depends(secure_admin_access(["system_health:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemHealthInfo:
    """
    Lấy thông tin chi tiết trạng thái hệ thống.

    **Quyền yêu cầu**: `system_health:read`

    **Cách sử dụng**:
    - Cung cấp ID trạng thái cần xem

    **Kết quả**:
    - Thông tin chi tiết trạng thái hệ thống
    """
    health_status = get_system_health_by_id(db, id)

    if not health_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trạng thái hệ thống không tồn tại",
        )

    logger.info(
        f"Admin {current_admin.username} đã xem thông tin trạng thái hệ thống ID={id}"
    )

    return health_status


@router.post("", response_model=SystemHealthInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:system_health:create")
@invalidate_cache(namespace="admin:system_health")
@log_admin_action(
    action="create",
    resource_type="system_health",
    description="Tạo trạng thái hệ thống mới",
)
async def create_new_system_health(
    health_data: SystemHealthCreate,
    current_admin: Admin = Depends(secure_admin_access(["system_health:create"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemHealthInfo:
    """
    Tạo trạng thái hệ thống mới.

    **Quyền yêu cầu**: `system_health:create`

    **Cách sử dụng**:
    - Cung cấp thông tin trạng thái hệ thống trong body

    **Kết quả**:
    - Thông tin trạng thái hệ thống đã tạo
    """
    # Tạo trạng thái hệ thống mới
    try:
        new_health = create_system_health(db, health_data)
        logger.info(
            f"Admin {current_admin.username} đã tạo trạng thái hệ thống mới cho thành phần {new_health.component}"
        )
        return new_health
    except ValueError as e:
        logger.error(f"Lỗi khi tạo trạng thái hệ thống mới: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=SystemHealthInfo)
@profile_endpoint(name="admin:system_health:update")
@invalidate_cache(namespace="admin:system_health")
@log_admin_action(action="update", resource_type="system_health", resource_id="{id}")
async def update_system_health_info(
    id: int = Path(..., ge=1, description="ID trạng thái"),
    health_data: SystemHealthUpdate = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["system_health:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemHealthInfo:
    """
    Cập nhật thông tin trạng thái hệ thống.

    **Quyền yêu cầu**: `system_health:update`

    **Cách sử dụng**:
    - Cung cấp ID trạng thái cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin trạng thái hệ thống đã cập nhật
    """
    # Kiểm tra trạng thái tồn tại
    health_status = get_system_health_by_id(db, id)

    if not health_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trạng thái hệ thống không tồn tại",
        )

    # Cập nhật trạng thái
    try:
        updated_health = update_system_health(db, id, health_data)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật trạng thái hệ thống ID={id}, component={updated_health.component}"
        )
        return updated_health
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật trạng thái hệ thống ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:system_health:delete")
@invalidate_cache(namespace="admin:system_health")
@log_admin_action(action="delete", resource_type="system_health", resource_id="{id}")
async def delete_system_health_item(
    id: int = Path(..., ge=1, description="ID trạng thái"),
    current_admin: Admin = Depends(secure_admin_access(["system_health:delete"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> None:
    """
    Xóa trạng thái hệ thống.

    **Quyền yêu cầu**: `system_health:delete`

    **Cách sử dụng**:
    - Cung cấp ID trạng thái cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra trạng thái tồn tại
    health_status = get_system_health_by_id(db, id)

    if not health_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trạng thái hệ thống không tồn tại",
        )

    # Xóa trạng thái
    try:
        deleted = delete_system_health(db, id)

        if not deleted:
            logger.error(f"Không thể xóa trạng thái hệ thống ID={id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể xóa trạng thái hệ thống",
            )

        logger.info(
            f"Admin {current_admin.username} đã xóa trạng thái hệ thống ID={id}, component={health_status.component}"
        )
    except ValueError as e:
        logger.error(f"Lỗi khi xóa trạng thái hệ thống ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
