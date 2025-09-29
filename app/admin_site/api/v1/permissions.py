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
from app.admin_site.models import Admin, Permission
from app.admin_site.schemas.permission import (
    PermissionCreate,
    PermissionUpdate,
    PermissionInDB,
    PermissionInfo,
)
from app.admin_site.services.permission_service import (
    create_permission,
    update_permission,
    delete_permission,
    get_permission_by_id,
    get_all_permissions,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/permissions - Lấy danh sách permission
# GET /api/v1/admin/permissions/{id} - Lấy thông tin chi tiết permission
# POST /api/v1/admin/permissions - Tạo permission mới
# PUT /api/v1/admin/permissions/{id} - Cập nhật thông tin permission
# DELETE /api/v1/admin/permissions/{id} - Xóa permission


@router.get("", response_model=List[PermissionInfo])
@profile_endpoint(name="admin:permissions:list")
@cached(ttl=300, namespace="admin:permissions", key_prefix="permission_list")
@log_admin_action(
    action="view", resource_type="permission", description="Xem danh sách quyền"
)
async def read_permissions(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên"),
    resource: Optional[str] = Query(None, description="Lọc theo resource"),
    action: Optional[str] = Query(None, description="Lọc theo action"),
    current_admin: Admin = Depends(secure_admin_access(["permission:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[PermissionInfo]:
    """
    Lấy danh sách permission.

    **Quyền yêu cầu**: `permission:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Tìm kiếm với tham số search
    - Lọc theo resource và action

    **Kết quả**:
    - Danh sách permission
    """
    permissions = get_all_permissions(db, skip, limit, search, resource, action)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(permissions)} permissions"
    )

    return permissions


@router.get("/{id}", response_model=PermissionInfo)
@profile_endpoint(name="admin:permissions:detail")
@cached(ttl=300, namespace="admin:permissions", key_prefix="permission_detail")
@log_admin_action(action="view", resource_type="permission", resource_id="{id}")
async def read_permission(
    id: int = Path(..., ge=1, description="ID permission"),
    current_admin: Admin = Depends(secure_admin_access(["permission:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> PermissionInfo:
    """
    Lấy thông tin chi tiết permission.

    **Quyền yêu cầu**: `permission:read`

    **Cách sử dụng**:
    - Cung cấp ID permission cần xem

    **Kết quả**:
    - Thông tin chi tiết permission
    """
    permission = get_permission_by_id(db, id)

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Permission không tồn tại"
        )

    logger.info(
        f"Admin {current_admin.username} đã xem thông tin permission {permission.name}"
    )

    return permission


@router.post("", response_model=PermissionInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:permissions:create")
@invalidate_cache(namespace="admin:permissions")
@log_admin_action(
    action="create", resource_type="permission", description="Tạo quyền mới"
)
async def create_new_permission(
    permission_data: PermissionCreate,
    current_admin: Admin = Depends(get_super_admin),
    db: Session = Depends(get_db),
    request: Request = None,
) -> PermissionInfo:
    """
    Tạo quyền mới.

    **Quyền yêu cầu**: Super Admin

    **Cách sử dụng**:
    - Cung cấp thông tin quyền trong body

    **Kết quả**:
    - Thông tin quyền đã tạo
    """
    # Tạo quyền mới
    try:
        new_permission = create_permission(db, permission_data)
        logger.info(
            f"Admin {current_admin.username} đã tạo quyền mới: {new_permission.name}"
        )
        return new_permission
    except ValueError as e:
        logger.error(f"Lỗi khi tạo quyền mới: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=PermissionInfo)
@profile_endpoint(name="admin:permissions:update")
@invalidate_cache(namespace="admin:permissions")
@log_admin_action(action="update", resource_type="permission", resource_id="{id}")
async def update_permission_info(
    id: int = Path(..., ge=1, description="ID permission"),
    permission_data: PermissionUpdate = Body(...),
    current_admin: Admin = Depends(get_super_admin),
    db: Session = Depends(get_db),
    request: Request = None,
) -> PermissionInfo:
    """
    Cập nhật thông tin quyền.

    **Quyền yêu cầu**: Super Admin

    **Cách sử dụng**:
    - Cung cấp ID quyền cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin quyền đã cập nhật
    """
    # Kiểm tra quyền tồn tại
    permission = get_permission_by_id(db, id)

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Quyền không tồn tại"
        )

    # Cập nhật quyền
    try:
        updated_permission = update_permission(db, id, permission_data)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật thông tin quyền ID={id}"
        )
        return updated_permission
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật quyền ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:permissions:delete")
@invalidate_cache(namespace="admin:permissions")
@log_admin_action(action="delete", resource_type="permission", resource_id="{id}")
async def delete_permission_item(
    id: int = Path(..., ge=1, description="ID permission"),
    current_admin: Admin = Depends(get_super_admin),
    db: Session = Depends(get_db),
    request: Request = None,
) -> None:
    """
    Xóa quyền.

    **Quyền yêu cầu**: Super Admin

    **Cách sử dụng**:
    - Cung cấp ID quyền cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra quyền tồn tại
    permission = get_permission_by_id(db, id)

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Quyền không tồn tại"
        )

    # Xóa quyền
    try:
        deleted = delete_permission(db, id)

        if not deleted:
            logger.error(f"Không thể xóa quyền ID={id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể xóa quyền",
            )

        logger.info(f"Admin {current_admin.username} đã xóa quyền {permission.name}")
    except ValueError as e:
        logger.error(f"Lỗi khi xóa quyền ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
