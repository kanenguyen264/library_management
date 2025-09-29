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
from app.admin_site.models import Admin, Role
from app.admin_site.schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleInDB,
    RoleInfo,
    RoleWithPermissions,
)
from app.admin_site.services.role_service import (
    create_role,
    update_role,
    delete_role,
    get_role_by_id,
    get_all_roles,
    set_role_permissions,
    assign_permissions_to_role,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/roles - Lấy danh sách role
# GET /api/v1/admin/roles/{id} - Lấy thông tin chi tiết role
# POST /api/v1/admin/roles - Tạo role mới
# PUT /api/v1/admin/roles/{id} - Cập nhật thông tin role
# DELETE /api/v1/admin/roles/{id} - Xóa role
# PUT /api/v1/admin/roles/{id}/permissions - Gán permissions cho role


@router.get("", response_model=List[RoleInfo])
@profile_endpoint(name="admin:roles:list")
@cached(ttl=300, namespace="admin:roles", key_prefix="role_list")
@log_admin_action(
    action="view", resource_type="role", description="Xem danh sách vai trò"
)
async def read_roles(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên"),
    current_admin: Admin = Depends(secure_admin_access(["role:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[RoleInfo]:
    """
    Lấy danh sách role.

    **Quyền yêu cầu**: `role:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Tìm kiếm với tham số search

    **Kết quả**:
    - Danh sách role
    """
    roles = get_all_roles(db, skip, limit, search)
    logger.info(f"Admin {current_admin.username} đã lấy danh sách {len(roles)} roles")
    return roles


@router.get("/{id}", response_model=RoleWithPermissions)
@profile_endpoint(name="admin:roles:detail")
@cached(ttl=300, namespace="admin:roles", key_prefix="role_detail")
@log_admin_action(action="view", resource_type="role", resource_id="{id}")
async def read_role(
    id: int = Path(..., ge=1, description="ID role"),
    current_admin: Admin = Depends(secure_admin_access(["role:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> RoleWithPermissions:
    """
    Lấy thông tin chi tiết role.

    **Quyền yêu cầu**: `role:read`

    **Cách sử dụng**:
    - Cung cấp ID role cần xem

    **Kết quả**:
    - Thông tin chi tiết role kèm permissions
    """
    role = get_role_by_id(db, id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role không tồn tại"
        )

    logger.info(f"Admin {current_admin.username} đã xem thông tin role {role.name}")
    return role


@router.post("", response_model=RoleInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:roles:create")
@invalidate_cache(namespace="admin:roles")
@log_admin_action(action="create", resource_type="role", description="Tạo vai trò mới")
async def create_new_role(
    role_data: RoleCreate,
    current_admin: Admin = Depends(secure_admin_access(["role:create"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> RoleInfo:
    """
    Tạo role mới.

    **Quyền yêu cầu**: `role:create`

    **Cách sử dụng**:
    - Cung cấp thông tin role trong body

    **Kết quả**:
    - Thông tin role đã tạo
    """
    # Tạo role mới
    try:
        new_role = create_role(db, role_data)
        logger.info(f"Admin {current_admin.username} đã tạo role mới: {new_role.name}")
        return new_role
    except ValueError as e:
        logger.error(f"Lỗi khi tạo role mới: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=RoleInfo)
@profile_endpoint(name="admin:roles:update")
@invalidate_cache(namespace="admin:roles")
@log_admin_action(action="update", resource_type="role", resource_id="{id}")
async def update_role_info(
    id: int = Path(..., ge=1, description="ID role"),
    role_data: RoleUpdate = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["role:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> RoleInfo:
    """
    Cập nhật thông tin role.

    **Quyền yêu cầu**: `role:update`

    **Cách sử dụng**:
    - Cung cấp ID role cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin role đã cập nhật
    """
    # Kiểm tra role tồn tại
    role = get_role_by_id(db, id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role không tồn tại"
        )

    # Cập nhật role
    try:
        updated_role = update_role(db, id, role_data)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật thông tin role {updated_role.name}"
        )
        return updated_role
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật role ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:roles:delete")
@invalidate_cache(namespace="admin:roles")
@log_admin_action(action="delete", resource_type="role", resource_id="{id}")
async def delete_role_item(
    id: int = Path(..., ge=1, description="ID role"),
    current_admin: Admin = Depends(secure_admin_access(["role:delete"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> None:
    """
    Xóa role.

    **Quyền yêu cầu**: `role:delete`

    **Cách sử dụng**:
    - Cung cấp ID role cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra role tồn tại
    role = get_role_by_id(db, id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role không tồn tại"
        )

    # Xóa role
    try:
        deleted = delete_role(db, id)

        if not deleted:
            logger.error(f"Không thể xóa role ID={id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể xóa role",
            )

        logger.info(f"Admin {current_admin.username} đã xóa role {role.name}")
    except ValueError as e:
        logger.error(f"Lỗi khi xóa role ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}/permissions", response_model=RoleWithPermissions)
@profile_endpoint(name="admin:roles:assign_permissions")
@invalidate_cache(namespace="admin:roles")
@invalidate_cache(namespace="admin:permissions")
@log_admin_action(action="update", resource_type="role_permissions", resource_id="{id}")
async def assign_permissions(
    id: int = Path(..., ge=1, description="ID role"),
    permission_ids: List[int] = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["role:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> RoleWithPermissions:
    """
    Gán permissions cho role.

    **Quyền yêu cầu**: `role:update`

    **Cách sử dụng**:
    - Cung cấp ID role cần gán permissions
    - Cung cấp danh sách ID permissions trong body

    **Kết quả**:
    - Thông tin role với permissions đã gán
    """
    # Kiểm tra role tồn tại
    role = get_role_by_id(db, id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role không tồn tại"
        )

    # Gán permissions
    try:
        updated_role = assign_permissions_to_role(db, id, permission_ids)
        logger.info(
            f"Admin {current_admin.username} đã gán permissions cho role {role.name}"
        )
        return updated_role
    except ValueError as e:
        logger.error(f"Lỗi khi gán permissions cho role ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
