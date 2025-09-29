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

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    get_super_admin,
    secure_admin_access,
)
from app.admin_site.models import Admin
from app.admin_site.schemas.admin import (
    AdminCreate,
    AdminUpdate,
    AdminInfo,
    AdminWithRoles,
    AdminListResponse,
    AdminResponse,
)
from app.admin_site.services.admin_service import (
    get_all_admins,
    count_admins,
    get_admin_by_id,
    create_new_admin,
    update_admin,
    delete_admin,
    assign_roles_to_admin,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint
from app.core.db import get_session

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/admins - Lấy danh sách admin
# GET /api/v1/admin/admins/{id} - Lấy thông tin chi tiết admin
# POST /api/v1/admin/admins - Tạo admin mới
# PUT /api/v1/admin/admins/{id} - Cập nhật thông tin admin
# DELETE /api/v1/admin/admins/{id} - Xóa admin
# PUT /api/v1/admin/admins/{id}/roles - Gán role cho admin


@router.get("/", response_model=AdminListResponse)
@profile_endpoint(name="admin:admins:list")
@cached(ttl=300, namespace="admin:admins", key_prefix="admin_list")
@log_admin_action(
    action="view", resource_type="admin", description="Xem danh sách admin"
)
async def list_admins(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
):
    """
    Get all admins with pagination
    """
    admins = get_all_admins(db, skip, limit, search)
    total = len(admins)  # In production, you'd have a dedicated count function

    return {
        "items": admins,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{admin_id}", response_model=AdminResponse)
@profile_endpoint(name="admin:admins:detail")
@cached(ttl=300, namespace="admin:admins", key_prefix="admin_detail")
@log_admin_action(action="view", resource_type="admin", resource_id="{admin_id}")
async def get_admin(
    admin_id: int = Path(...),
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
):
    """
    Get admin by ID
    """
    admin = get_admin_by_id(db, admin_id)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
        )
    return admin


@router.post("/", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:admins:create")
@invalidate_cache(namespace="admin:admins")
@log_admin_action(action="create", resource_type="admin", description="Tạo admin mới")
async def create_new_admin(
    admin_data: AdminCreate = Body(...),
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
):
    """
    Create a new admin
    """
    # Check if superadmin permission is needed and enforce it
    if admin_data.is_super_admin and not current_admin.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can create other super admins",
        )

    new_admin = create_new_admin(db, admin_data)
    return new_admin


@router.put("/{admin_id}", response_model=AdminResponse)
@profile_endpoint(name="admin:admins:update")
@invalidate_cache(namespace="admin:admins")
@log_admin_action(action="update", resource_type="admin", resource_id="{admin_id}")
async def update_admin_info(
    admin_id: int = Path(...),
    admin_data: AdminUpdate = Body(...),
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
):
    """
    Update an admin
    """
    # Get existing admin
    existing_admin = get_admin_by_id(db, admin_id)
    if not existing_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
        )

    # Check permissions for super admin updates
    if (
        admin_data.is_super_admin is not None
        and admin_data.is_super_admin != existing_admin.is_super_admin
        and not current_admin.is_super_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can update super admin status",
        )

    # Don't allow non-super admins to update super admins
    if existing_admin.is_super_admin and not current_admin.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can update super admins",
        )

    updated_admin = update_admin(db, admin_id, admin_data)
    return updated_admin


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:admins:delete")
@invalidate_cache(namespace="admin:admins")
@log_admin_action(action="delete", resource_type="admin", resource_id="{admin_id}")
async def delete_admin_account(
    admin_id: int = Path(...),
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
):
    """
    Delete an admin
    """
    # Get existing admin
    existing_admin = get_admin_by_id(db, admin_id)
    if not existing_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
        )

    # Don't allow deletion of super admins except by other super admins
    if existing_admin.is_super_admin and not current_admin.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can delete super admins",
        )

    # Don't allow self-deletion
    if existing_admin.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot delete their own accounts",
        )

    delete_admin(db, admin_id)
    return None


@router.put("/{id}/roles", response_model=AdminWithRoles)
@profile_endpoint(name="admin:admins:assign_roles")
@invalidate_cache(namespace="admin:admins")
@log_admin_action(action="update", resource_type="admin_roles", resource_id="{id}")
async def assign_roles(
    id: int = Path(..., ge=1, description="ID admin"),
    role_ids: List[int] = Body(...),
    current_admin: Admin = Depends(get_super_admin),
    db: Session = Depends(get_db),
    request: Request = None,
) -> AdminWithRoles:
    """
    Gán vai trò cho admin.

    **Quyền yêu cầu**: Super Admin

    **Cách sử dụng**:
    - Cung cấp ID admin cần gán vai trò
    - Cung cấp danh sách ID vai trò trong body

    **Kết quả**:
    - Thông tin admin kèm danh sách vai trò đã gán
    """
    # Kiểm tra admin tồn tại
    admin = get_admin_by_id(db, id)

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin không tồn tại"
        )

    # Ngăn thay đổi vai trò của super admin
    if admin.is_super_admin and id != current_admin.id:
        logger.warning(
            f"Admin {current_admin.username} đang cố thay đổi vai trò của Super Admin khác"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể thay đổi vai trò của Super Admin khác",
        )

    # Gán vai trò cho admin
    try:
        updated_admin = assign_roles_to_admin(db, id, role_ids)
        logger.info(f"Admin {current_admin.username} đã gán vai trò cho admin ID={id}")
        return updated_admin
    except ValueError as e:
        logger.error(f"Lỗi khi gán vai trò cho admin ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
