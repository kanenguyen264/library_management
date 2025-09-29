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
from datetime import datetime, date

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    secure_admin_access,
)
from app.admin_site.models import Admin, Promotion
from app.admin_site.schemas.promotion import (
    PromotionCreate,
    PromotionUpdate,
    PromotionInfo,
)
from app.admin_site.services.promotion_service import (
    create_promotion,
    update_promotion,
    delete_promotion,
    get_promotion_by_id,
    get_all_promotions,
    toggle_promotion_status,
    increment_promotion_usage,
    count_promotions,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/promotions - Lấy danh sách khuyến mãi
# GET /api/v1/admin/promotions/{id} - Lấy thông tin chi tiết khuyến mãi
# POST /api/v1/admin/promotions - Tạo khuyến mãi mới
# PUT /api/v1/admin/promotions/{id} - Cập nhật thông tin khuyến mãi
# DELETE /api/v1/admin/promotions/{id} - Xóa khuyến mãi


@router.get("", response_model=List[PromotionInfo])
@cached(ttl=300, namespace="admin:promotions", key_prefix="promotion_list")
async def read_promotions(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    search: Optional[str] = Query(
        None, description="Tìm kiếm theo tên hoặc mã khuyến mãi"
    ),
    active_only: bool = Query(
        False, description="Chỉ hiển thị khuyến mãi đang hoạt động"
    ),
    current_admin: Admin = Depends(check_admin_permissions(["promotion:read"])),
    db: Session = Depends(get_db),
) -> List[PromotionInfo]:
    """
    Lấy danh sách khuyến mãi.

    **Quyền yêu cầu**: `promotion:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Tìm kiếm với tham số search
    - Lọc theo trạng thái hoạt động với tham số active_only

    **Kết quả**:
    - Danh sách khuyến mãi
    """
    promotions = get_all_promotions(db, skip, limit, search, active_only)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(promotions)} khuyến mãi"
    )

    return promotions


@router.get("/{id}", response_model=PromotionInfo)
@cached(ttl=300, namespace="admin:promotions", key_prefix="promotion_detail")
async def read_promotion(
    id: int = Path(..., ge=1, description="ID khuyến mãi"),
    current_admin: Admin = Depends(check_admin_permissions(["promotion:read"])),
    db: Session = Depends(get_db),
) -> PromotionInfo:
    """
    Lấy thông tin chi tiết khuyến mãi.

    **Quyền yêu cầu**: `promotion:read`

    **Cách sử dụng**:
    - Cung cấp ID khuyến mãi cần xem

    **Kết quả**:
    - Thông tin chi tiết khuyến mãi
    """
    promotion = get_promotion_by_id(db, id)

    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khuyến mãi không tồn tại"
        )

    logger.info(f"Admin {current_admin.username} đã xem thông tin khuyến mãi ID={id}")

    return promotion


@router.post("", response_model=PromotionInfo, status_code=status.HTTP_201_CREATED)
@invalidate_cache(patterns=["promotion_list*"])
async def create_new_promotion(
    promotion_data: PromotionCreate,
    current_admin: Admin = Depends(check_admin_permissions(["promotion:create"])),
    db: Session = Depends(get_db),
) -> PromotionInfo:
    """
    Tạo khuyến mãi mới.

    **Quyền yêu cầu**: `promotion:create`

    **Cách sử dụng**:
    - Cung cấp thông tin khuyến mãi trong body

    **Kết quả**:
    - Thông tin khuyến mãi đã tạo
    """
    # Tạo khuyến mãi mới
    try:
        new_promotion = create_promotion(db, promotion_data)

        # Ghi log hành động
        await log_admin_action(
            admin_id=current_admin.id,
            activity_type="create_promotion",
            description=f"Tạo khuyến mãi mới: {new_promotion.name}",
            affected_resource="promotion",
            resource_id=new_promotion.id,
        )

        logger.info(
            f"Admin {current_admin.username} đã tạo khuyến mãi mới: {new_promotion.name}"
        )

        return new_promotion
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=PromotionInfo)
@invalidate_cache(patterns=["promotion_list*"])
@invalidate_cache(patterns=["promotion_detail*"])
async def update_promotion_info(
    id: int = Path(..., ge=1, description="ID khuyến mãi"),
    promotion_data: PromotionUpdate = Body(...),
    current_admin: Admin = Depends(check_admin_permissions(["promotion:update"])),
    db: Session = Depends(get_db),
) -> PromotionInfo:
    """
    Cập nhật thông tin khuyến mãi.

    **Quyền yêu cầu**: `promotion:update`

    **Cách sử dụng**:
    - Cung cấp ID khuyến mãi cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin khuyến mãi đã cập nhật
    """
    # Kiểm tra khuyến mãi tồn tại
    promotion = get_promotion_by_id(db, id)

    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khuyến mãi không tồn tại"
        )

    # Cập nhật khuyến mãi
    try:
        updated_promotion = update_promotion(db, id, promotion_data)

        # Ghi log hành động
        await log_admin_action(
            admin_id=current_admin.id,
            activity_type="update_promotion",
            description=f"Cập nhật thông tin khuyến mãi: {updated_promotion.name}",
            affected_resource="promotion",
            resource_id=updated_promotion.id,
            changes_json=promotion_data.model_dump(exclude_unset=True),
        )

        logger.info(
            f"Admin {current_admin.username} đã cập nhật thông tin khuyến mãi ID={id}"
        )

        return updated_promotion
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}/toggle-status", response_model=PromotionInfo)
@invalidate_cache(patterns=["promotion_list*"])
@invalidate_cache(patterns=["promotion_detail*"])
async def toggle_promotion_active_status(
    id: int = Path(..., ge=1, description="ID khuyến mãi"),
    current_admin: Admin = Depends(check_admin_permissions(["promotion:update"])),
    db: Session = Depends(get_db),
) -> PromotionInfo:
    """
    Đổi trạng thái kích hoạt của khuyến mãi.

    **Quyền yêu cầu**: `promotion:update`

    **Cách sử dụng**:
    - Cung cấp ID khuyến mãi cần đổi trạng thái

    **Kết quả**:
    - Thông tin khuyến mãi đã cập nhật
    """
    # Kiểm tra khuyến mãi tồn tại
    promotion = get_promotion_by_id(db, id)

    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khuyến mãi không tồn tại"
        )

    # Đổi trạng thái
    try:
        updated_promotion = toggle_promotion_status(db, id)

        new_status = "kích hoạt" if updated_promotion.is_active else "vô hiệu hóa"

        # Ghi log hành động
        await log_admin_action(
            admin_id=current_admin.id,
            activity_type="toggle_promotion",
            description=f"Đổi trạng thái khuyến mãi ID={id} thành {new_status}",
            affected_resource="promotion",
            resource_id=updated_promotion.id,
            changes_json={"is_active": updated_promotion.is_active},
        )

        logger.info(
            f"Admin {current_admin.username} đã đổi trạng thái khuyến mãi ID={id} thành {new_status}"
        )

        return updated_promotion
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{id}/increment-usage", response_model=PromotionInfo)
@invalidate_cache(patterns=["promotion_detail*"])
async def increment_usage(
    id: int = Path(..., ge=1, description="ID khuyến mãi"),
    increment_by: int = Query(1, ge=1, description="Số lượng tăng"),
    current_admin: Admin = Depends(check_admin_permissions(["promotion:update"])),
    db: Session = Depends(get_db),
) -> PromotionInfo:
    """
    Tăng số lần sử dụng của khuyến mãi.

    **Quyền yêu cầu**: `promotion:update`

    **Cách sử dụng**:
    - Cung cấp ID khuyến mãi cần tăng số lần sử dụng
    - Cung cấp số lượng tăng với tham số increment_by

    **Kết quả**:
    - Thông tin khuyến mãi đã cập nhật
    """
    # Kiểm tra khuyến mãi tồn tại
    promotion = get_promotion_by_id(db, id)

    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khuyến mãi không tồn tại"
        )

    # Tăng số lần sử dụng
    try:
        updated_promotion = increment_promotion_usage(db, id, increment_by)

        # Ghi log hành động
        await log_admin_action(
            admin_id=current_admin.id,
            activity_type="increment_promotion_usage",
            description=f"Tăng số lần sử dụng khuyến mãi ID={id} thêm {increment_by}",
            affected_resource="promotion",
            resource_id=updated_promotion.id,
            changes_json={"usage_count": updated_promotion.usage_count},
        )

        logger.info(
            f"Admin {current_admin.username} đã tăng số lần sử dụng khuyến mãi ID={id} thêm {increment_by}"
        )

        return updated_promotion
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@invalidate_cache(patterns=["promotion_list*"])
@invalidate_cache(patterns=["promotion_detail*"])
async def delete_promotion_item(
    id: int = Path(..., ge=1, description="ID khuyến mãi"),
    current_admin: Admin = Depends(check_admin_permissions(["promotion:delete"])),
    db: Session = Depends(get_db),
) -> None:
    """
    Xóa khuyến mãi.

    **Quyền yêu cầu**: `promotion:delete`

    **Cách sử dụng**:
    - Cung cấp ID khuyến mãi cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra khuyến mãi tồn tại
    promotion = get_promotion_by_id(db, id)

    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Khuyến mãi không tồn tại"
        )

    # Xóa khuyến mãi
    try:
        deleted = delete_promotion(db, id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể xóa khuyến mãi",
            )

        # Ghi log hành động
        await log_admin_action(
            admin_id=current_admin.id,
            activity_type="delete_promotion",
            description=f"Xóa khuyến mãi: {promotion.name}",
            affected_resource="promotion",
            resource_id=id,
        )

        logger.info(
            f"Admin {current_admin.username} đã xóa khuyến mãi {promotion.name}"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
