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
    get_super_admin,
    check_admin_permissions,
    secure_admin_access,
)
from app.admin_site.models import Admin, SystemSetting
from app.admin_site.schemas.system_setting import (
    SystemSettingCreate,
    SystemSettingUpdate,
    SystemSettingInfo,
)
from app.admin_site.services.system_setting_service import (
    get_all_system_settings,
    count_system_settings,
    get_system_setting_by_id,
    get_system_setting_by_key,
    get_setting_groups,
    get_settings_by_group,
    create_system_setting,
    update_system_setting,
    update_setting_by_key,
    delete_system_setting,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/system-settings - Lấy danh sách cài đặt
# GET /api/v1/admin/system-settings/{id} - Lấy thông tin chi tiết cài đặt
# GET /api/v1/admin/system-settings/key/{key} - Lấy cài đặt theo key
# POST /api/v1/admin/system-settings - Tạo cài đặt mới
# PUT /api/v1/admin/system-settings/{id} - Cập nhật thông tin cài đặt
# DELETE /api/v1/admin/system-settings/{id} - Xóa cài đặt


@router.get("", response_model=List[SystemSettingInfo])
@profile_endpoint(name="admin:system_settings:list")
@cached(ttl=300, namespace="admin:system_settings", key_prefix="settings_list")
@log_admin_action(
    action="view",
    resource_type="system_setting",
    description="Xem danh sách cài đặt hệ thống",
)
async def read_system_settings(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo key"),
    group: Optional[str] = Query(None, description="Lọc theo nhóm"),
    is_public: Optional[bool] = Query(None, description="Lọc theo trạng thái public"),
    current_admin: Admin = Depends(secure_admin_access(["system_setting:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[SystemSettingInfo]:
    """
    Lấy danh sách cài đặt hệ thống.

    **Quyền yêu cầu**: `system_setting:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Tìm kiếm với tham số search
    - Lọc theo nhóm với tham số group
    - Lọc theo trạng thái public với tham số is_public

    **Kết quả**:
    - Danh sách cài đặt hệ thống
    """
    settings = get_all_system_settings(db, skip, limit, search, group, is_public)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(settings)} cài đặt hệ thống"
    )

    return settings


@router.get("/groups", response_model=List[str])
@profile_endpoint(name="admin:system_settings:groups")
@cached(ttl=3600, namespace="admin:system_settings", key_prefix="setting_groups")
@log_admin_action(
    action="view",
    resource_type="system_setting_groups",
    description="Xem danh sách nhóm cài đặt",
)
async def read_setting_groups(
    current_admin: Admin = Depends(secure_admin_access(["system_setting:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[str]:
    """
    Lấy danh sách các nhóm cài đặt.

    **Quyền yêu cầu**: `system_setting:read`

    **Kết quả**:
    - Danh sách các nhóm cài đặt
    """
    groups = get_setting_groups(db)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(groups)} nhóm cài đặt"
    )

    return groups


@router.get("/group/{group}", response_model=List[SystemSettingInfo])
@profile_endpoint(name="admin:system_settings:by_group")
@cached(ttl=300, namespace="admin:system_settings", key_prefix="settings_by_group")
@log_admin_action(
    action="view", resource_type="system_setting_group", resource_id="{group}"
)
async def read_settings_by_group(
    group: str = Path(..., description="Tên nhóm"),
    current_admin: Admin = Depends(secure_admin_access(["system_setting:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[SystemSettingInfo]:
    """
    Lấy danh sách cài đặt theo nhóm.

    **Quyền yêu cầu**: `system_setting:read`

    **Cách sử dụng**:
    - Cung cấp tên nhóm

    **Kết quả**:
    - Danh sách cài đặt hệ thống thuộc nhóm
    """
    settings = get_settings_by_group(db, group)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(settings)} cài đặt trong nhóm {group}"
    )

    return settings


@router.get("/{id}", response_model=SystemSettingInfo)
@profile_endpoint(name="admin:system_settings:detail")
@cached(ttl=300, namespace="admin:system_settings", key_prefix="setting_detail")
@log_admin_action(action="view", resource_type="system_setting", resource_id="{id}")
async def read_system_setting(
    id: int = Path(..., ge=1, description="ID cài đặt"),
    current_admin: Admin = Depends(secure_admin_access(["system_setting:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemSettingInfo:
    """
    Lấy thông tin chi tiết cài đặt hệ thống.

    **Quyền yêu cầu**: `system_setting:read`

    **Cách sử dụng**:
    - Cung cấp ID cài đặt cần xem

    **Kết quả**:
    - Thông tin chi tiết cài đặt hệ thống
    """
    setting = get_system_setting_by_id(db, id)

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cài đặt hệ thống không tồn tại",
        )

    logger.info(
        f"Admin {current_admin.username} đã xem thông tin cài đặt hệ thống ID={id}"
    )

    return setting


@router.get("/key/{key}", response_model=SystemSettingInfo)
@profile_endpoint(name="admin:system_settings:by_key")
@cached(ttl=300, namespace="admin:system_settings", key_prefix="setting_by_key")
@log_admin_action(
    action="view", resource_type="system_setting_key", resource_id="{key}"
)
async def read_system_setting_by_key(
    key: str = Path(..., description="Key cài đặt"),
    current_admin: Admin = Depends(secure_admin_access(["system_setting:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemSettingInfo:
    """
    Lấy thông tin chi tiết cài đặt hệ thống theo key.

    **Quyền yêu cầu**: `system_setting:read`

    **Cách sử dụng**:
    - Cung cấp key cài đặt cần xem

    **Kết quả**:
    - Thông tin chi tiết cài đặt hệ thống
    """
    setting = get_system_setting_by_key(db, key)

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cài đặt hệ thống với key={key} không tồn tại",
        )

    logger.info(
        f"Admin {current_admin.username} đã xem thông tin cài đặt hệ thống key={key}"
    )

    return setting


@router.post("", response_model=SystemSettingInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:system_settings:create")
@invalidate_cache(namespace="admin:system_settings")
@log_admin_action(
    action="create",
    resource_type="system_setting",
    description="Tạo cài đặt hệ thống mới",
)
async def create_new_system_setting(
    setting_data: SystemSettingCreate,
    current_admin: Admin = Depends(secure_admin_access(["system_setting:create"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemSettingInfo:
    """
    Tạo cài đặt hệ thống mới.

    **Quyền yêu cầu**: `system_setting:create`

    **Cách sử dụng**:
    - Cung cấp thông tin cài đặt hệ thống trong body

    **Kết quả**:
    - Thông tin cài đặt hệ thống đã tạo
    """
    # Tạo cài đặt hệ thống mới
    try:
        new_setting = create_system_setting(db, setting_data)
        logger.info(
            f"Admin {current_admin.username} đã tạo cài đặt hệ thống mới: {new_setting.key}"
        )
        return new_setting
    except ValueError as e:
        logger.error(f"Lỗi khi tạo cài đặt hệ thống mới: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=SystemSettingInfo)
@profile_endpoint(name="admin:system_settings:update")
@invalidate_cache(namespace="admin:system_settings")
@log_admin_action(action="update", resource_type="system_setting", resource_id="{id}")
async def update_system_setting_info(
    id: int = Path(..., ge=1, description="ID cài đặt"),
    setting_data: SystemSettingUpdate = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["system_setting:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemSettingInfo:
    """
    Cập nhật thông tin cài đặt hệ thống.

    **Quyền yêu cầu**: `system_setting:update`

    **Cách sử dụng**:
    - Cung cấp ID cài đặt cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin cài đặt hệ thống đã cập nhật
    """
    # Kiểm tra cài đặt tồn tại
    setting = get_system_setting_by_id(db, id)

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cài đặt hệ thống không tồn tại",
        )

    # Cập nhật cài đặt
    try:
        updated_setting = update_system_setting(db, id, setting_data)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật cài đặt hệ thống key={updated_setting.key}"
        )
        return updated_setting
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật cài đặt hệ thống ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/key/{key}", response_model=SystemSettingInfo)
@profile_endpoint(name="admin:system_settings:update_by_key")
@invalidate_cache(namespace="admin:system_settings")
@log_admin_action(
    action="update", resource_type="system_setting_key", resource_id="{key}"
)
async def update_system_setting_by_key(
    key: str = Path(..., description="Key cài đặt"),
    value: str = Query(..., description="Giá trị mới"),
    current_admin: Admin = Depends(secure_admin_access(["system_setting:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemSettingInfo:
    """
    Cập nhật giá trị cài đặt hệ thống theo key.

    **Quyền yêu cầu**: `system_setting:update`

    **Cách sử dụng**:
    - Cung cấp key cài đặt cần cập nhật
    - Cung cấp giá trị mới trong query

    **Kết quả**:
    - Thông tin cài đặt hệ thống đã cập nhật
    """
    # Kiểm tra cài đặt tồn tại
    setting = get_system_setting_by_key(db, key)

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cài đặt hệ thống với key={key} không tồn tại",
        )

    # Cập nhật cài đặt
    try:
        updated_setting = update_setting_by_key(db, key, value)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật giá trị cài đặt hệ thống key={key} thành '{value}'"
        )
        return updated_setting
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật cài đặt hệ thống key={key}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:system_settings:delete")
@invalidate_cache(namespace="admin:system_settings")
@log_admin_action(action="delete", resource_type="system_setting", resource_id="{id}")
async def delete_system_setting_item(
    id: int = Path(..., ge=1, description="ID cài đặt"),
    current_admin: Admin = Depends(secure_admin_access(["system_setting:delete"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> None:
    """
    Xóa cài đặt hệ thống.

    **Quyền yêu cầu**: `system_setting:delete`

    **Cách sử dụng**:
    - Cung cấp ID cài đặt cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra cài đặt tồn tại
    setting = get_system_setting_by_id(db, id)

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cài đặt hệ thống không tồn tại",
        )

    # Xóa cài đặt
    try:
        deleted = delete_system_setting(db, id)

        if not deleted:
            logger.error(f"Không thể xóa cài đặt hệ thống ID={id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể xóa cài đặt hệ thống",
            )

        logger.info(
            f"Admin {current_admin.username} đã xóa cài đặt hệ thống key={setting.key}"
        )
    except ValueError as e:
        logger.error(f"Lỗi khi xóa cài đặt hệ thống ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
