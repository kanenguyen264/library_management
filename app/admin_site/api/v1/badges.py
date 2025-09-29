from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.common.db.session import get_db
from app.admin_site.api.deps import get_current_admin, check_admin_permissions
from app.admin_site.models import Admin, Badge
from app.admin_site.schemas.badge import BadgeCreate, BadgeUpdate, BadgeInfo
from app.admin_site.services.badge_service import (
    get_all_badges,
    count_badges,
    get_badge_by_id,
    create_badge,
    update_badge,
    delete_badge,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/badges - Lấy danh sách huy hiệu
# GET /api/v1/admin/badges/{id} - Lấy thông tin chi tiết huy hiệu
# POST /api/v1/admin/badges - Tạo huy hiệu mới
# PUT /api/v1/admin/badges/{id} - Cập nhật thông tin huy hiệu
# DELETE /api/v1/admin/badges/{id} - Xóa huy hiệu


@router.get("", response_model=List[BadgeInfo])
@cached(ttl=300, namespace="admin:badges", key_prefix="badge_list")
async def read_badges(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên"),
    badge_type: Optional[str] = Query(None, description="Lọc theo loại huy hiệu"),
    is_active: Optional[bool] = Query(
        None, description="Lọc theo trạng thái kích hoạt"
    ),
    current_admin: Admin = Depends(check_admin_permissions(["badge:read"])),
    db: Session = Depends(get_db),
) -> List[BadgeInfo]:
    """
    Lấy danh sách huy hiệu.

    **Quyền yêu cầu**: `badge:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Tìm kiếm với tham số search
    - Lọc theo loại huy hiệu với tham số badge_type
    - Lọc theo trạng thái kích hoạt với tham số is_active

    **Kết quả**:
    - Danh sách huy hiệu
    """
    badges = get_all_badges(db, skip, limit, search, badge_type, is_active)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(badges)} huy hiệu"
    )

    return badges


@router.get("/{id}", response_model=BadgeInfo)
@cached(ttl=300, namespace="admin:badges", key_prefix="badge_detail")
async def read_badge(
    id: int = Path(..., ge=1, description="ID huy hiệu"),
    current_admin: Admin = Depends(check_admin_permissions(["badge:read"])),
    db: Session = Depends(get_db),
) -> BadgeInfo:
    """
    Lấy thông tin chi tiết huy hiệu.

    **Quyền yêu cầu**: `badge:read`

    **Cách sử dụng**:
    - Cung cấp ID huy hiệu cần xem

    **Kết quả**:
    - Thông tin chi tiết huy hiệu
    """
    badge = get_badge_by_id(db, id)

    if not badge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Huy hiệu không tồn tại"
        )

    logger.info(f"Admin {current_admin.username} đã xem thông tin huy hiệu ID={id}")

    return badge


@router.post("", response_model=BadgeInfo, status_code=status.HTTP_201_CREATED)
@invalidate_cache(patterns=["badge_list*"])
async def create_new_badge(
    badge_data: BadgeCreate,
    current_admin: Admin = Depends(check_admin_permissions(["badge:create"])),
    db: Session = Depends(get_db),
) -> BadgeInfo:
    """
    Tạo huy hiệu mới.

    **Quyền yêu cầu**: `badge:create`

    **Cách sử dụng**:
    - Cung cấp thông tin huy hiệu trong body

    **Kết quả**:
    - Thông tin huy hiệu đã tạo
    """
    # Tạo huy hiệu mới
    try:
        new_badge = create_badge(db, badge_data)

        # Ghi log hành động
        await log_admin_action(
            admin_id=current_admin.id,
            activity_type="create_badge",
            description=f"Tạo huy hiệu mới: {new_badge.name}",
            affected_resource="badge",
            resource_id=new_badge.id,
        )

        logger.info(
            f"Admin {current_admin.username} đã tạo huy hiệu mới: {new_badge.name}"
        )

        return new_badge
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=BadgeInfo)
@invalidate_cache(patterns=["badge_list*"])
@invalidate_cache(patterns=["badge_detail*"])
async def update_badge_item(
    id: int = Path(..., ge=1, description="ID huy hiệu"),
    badge_data: BadgeUpdate = Body(...),
    current_admin: Admin = Depends(check_admin_permissions(["badge:update"])),
    db: Session = Depends(get_db),
) -> BadgeInfo:
    """
    Cập nhật thông tin huy hiệu.

    **Quyền yêu cầu**: `badge:update`

    **Cách sử dụng**:
    - Cung cấp ID huy hiệu cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin huy hiệu đã cập nhật
    """
    # Kiểm tra huy hiệu tồn tại
    badge = get_badge_by_id(db, id)

    if not badge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Huy hiệu không tồn tại"
        )

    # Cập nhật huy hiệu
    try:
        updated_badge = update_badge(db, id, badge_data)

        # Ghi log hành động
        await log_admin_action(
            admin_id=current_admin.id,
            activity_type="update_badge",
            description=f"Cập nhật thông tin huy hiệu: {updated_badge.name}",
            affected_resource="badge",
            resource_id=updated_badge.id,
            changes_json=badge_data.model_dump(exclude_unset=True),
        )

        logger.info(
            f"Admin {current_admin.username} đã cập nhật thông tin huy hiệu ID={id}"
        )

        return updated_badge
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@invalidate_cache(patterns=["badge_list*"])
@invalidate_cache(patterns=["badge_detail*"])
async def delete_badge_item(
    id: int = Path(..., ge=1, description="ID huy hiệu"),
    current_admin: Admin = Depends(check_admin_permissions(["badge:delete"])),
    db: Session = Depends(get_db),
) -> None:
    """
    Xóa huy hiệu.

    **Quyền yêu cầu**: `badge:delete`

    **Cách sử dụng**:
    - Cung cấp ID huy hiệu cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra huy hiệu tồn tại
    badge = get_badge_by_id(db, id)

    if not badge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Huy hiệu không tồn tại"
        )

    # Xóa huy hiệu
    deleted = delete_badge(db, id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể xóa huy hiệu",
        )

    # Ghi log hành động
    await log_admin_action(
        admin_id=current_admin.id,
        activity_type="delete_badge",
        description=f"Xóa huy hiệu: {badge.name}",
        affected_resource="badge",
        resource_id=id,
    )

    logger.info(f"Admin {current_admin.username} đã xóa huy hiệu {badge.name}")
