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
from app.admin_site.models import Admin, FeaturedContent
from app.admin_site.schemas.featured_content import (
    FeaturedContentCreate,
    FeaturedContentUpdate,
    FeaturedContentInfo,
)
from app.admin_site.services.featured_content_service import (
    get_all_featured_contents,
    count_featured_contents,
    get_featured_content_by_id,
    create_featured_content,
    update_featured_content,
    delete_featured_content,
    toggle_featured_content_status,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/featured-content - Lấy danh sách nội dung nổi bật
# GET /api/v1/admin/featured-content/{id} - Lấy thông tin chi tiết nội dung nổi bật
# POST /api/v1/admin/featured-content - Tạo nội dung nổi bật mới
# PUT /api/v1/admin/featured-content/{id} - Cập nhật thông tin nội dung nổi bật
# DELETE /api/v1/admin/featured-content/{id} - Xóa nội dung nổi bật


@router.get("", response_model=List[FeaturedContentInfo])
@profile_endpoint(name="admin:featured_content:list")
@cached(ttl=300, namespace="admin:featured_content", key_prefix="content_list")
@log_admin_action(
    action="view",
    resource_type="featured_content",
    description="Xem danh sách nội dung nổi bật",
)
async def read_featured_content_list(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    content_type: Optional[str] = Query(None, description="Lọc theo loại nội dung"),
    active_only: bool = Query(
        False, description="Chỉ hiển thị nội dung đang hoạt động"
    ),
    current_admin: Admin = Depends(secure_admin_access(["featured_content:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[FeaturedContentInfo]:
    """
    Lấy danh sách nội dung nổi bật.

    **Quyền yêu cầu**: `featured_content:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Lọc theo loại nội dung với tham số content_type
    - Lọc theo trạng thái hoạt động với tham số active_only

    **Kết quả**:
    - Danh sách nội dung nổi bật
    """
    featured_contents = get_all_featured_contents(
        db, skip, limit, content_type, active_only
    )

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(featured_contents)} nội dung nổi bật"
    )

    return featured_contents


@router.get("/{id}", response_model=FeaturedContentInfo)
@profile_endpoint(name="admin:featured_content:detail")
@cached(ttl=300, namespace="admin:featured_content", key_prefix="content_detail")
@log_admin_action(action="view", resource_type="featured_content", resource_id="{id}")
async def read_featured_content(
    id: int = Path(..., ge=1, description="ID nội dung nổi bật"),
    current_admin: Admin = Depends(secure_admin_access(["featured_content:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> FeaturedContentInfo:
    """
    Lấy thông tin chi tiết nội dung nổi bật.

    **Quyền yêu cầu**: `featured_content:read`

    **Cách sử dụng**:
    - Cung cấp ID nội dung nổi bật cần xem

    **Kết quả**:
    - Thông tin chi tiết nội dung nổi bật
    """
    featured_content = get_featured_content_by_id(db, id)

    if not featured_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nội dung nổi bật không tồn tại",
        )

    logger.info(
        f"Admin {current_admin.username} đã xem thông tin nội dung nổi bật ID={id}"
    )

    return featured_content


@router.post(
    "", response_model=FeaturedContentInfo, status_code=status.HTTP_201_CREATED
)
@profile_endpoint(name="admin:featured_content:create")
@invalidate_cache(namespace="admin:featured_content")
@log_admin_action(
    action="create",
    resource_type="featured_content",
    description="Tạo nội dung nổi bật mới",
)
async def create_new_featured_content(
    featured_data: FeaturedContentCreate,
    current_admin: Admin = Depends(secure_admin_access(["featured_content:create"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> FeaturedContentInfo:
    """
    Tạo nội dung nổi bật mới.

    **Quyền yêu cầu**: `featured_content:create`

    **Cách sử dụng**:
    - Cung cấp thông tin nội dung nổi bật trong body

    **Kết quả**:
    - Thông tin nội dung nổi bật đã tạo
    """
    # Tạo nội dung nổi bật mới
    try:
        new_featured = create_featured_content(db, featured_data)
        logger.info(
            f"Admin {current_admin.username} đã tạo nội dung nổi bật mới cho {new_featured.content_type} ID={new_featured.content_id}"
        )
        return new_featured
    except ValueError as e:
        logger.error(f"Lỗi khi tạo nội dung nổi bật mới: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=FeaturedContentInfo)
@profile_endpoint(name="admin:featured_content:update")
@invalidate_cache(namespace="admin:featured_content")
@log_admin_action(action="update", resource_type="featured_content", resource_id="{id}")
async def update_featured_content_info(
    id: int = Path(..., ge=1, description="ID nội dung nổi bật"),
    featured_data: FeaturedContentUpdate = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["featured_content:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> FeaturedContentInfo:
    """
    Cập nhật thông tin nội dung nổi bật.

    **Quyền yêu cầu**: `featured_content:update`

    **Cách sử dụng**:
    - Cung cấp ID nội dung nổi bật cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin nội dung nổi bật đã cập nhật
    """
    # Kiểm tra nội dung nổi bật tồn tại
    featured = get_featured_content_by_id(db, id)

    if not featured:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nội dung nổi bật không tồn tại",
        )

    # Cập nhật nội dung nổi bật
    try:
        updated_featured = update_featured_content(db, id, featured_data)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật thông tin nội dung nổi bật ID={id}"
        )
        return updated_featured
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật nội dung nổi bật ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}/toggle-status", response_model=FeaturedContentInfo)
@profile_endpoint(name="admin:featured_content:toggle_status")
@invalidate_cache(namespace="admin:featured_content")
@log_admin_action(
    action="update",
    resource_type="featured_content",
    resource_id="{id}",
    description="Đổi trạng thái nội dung nổi bật",
)
async def toggle_featured_content_active_status(
    id: int = Path(..., ge=1, description="ID nội dung nổi bật"),
    current_admin: Admin = Depends(secure_admin_access(["featured_content:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> FeaturedContentInfo:
    """
    Đổi trạng thái kích hoạt của nội dung nổi bật.

    **Quyền yêu cầu**: `featured_content:update`

    **Cách sử dụng**:
    - Cung cấp ID nội dung nổi bật cần đổi trạng thái

    **Kết quả**:
    - Thông tin nội dung nổi bật đã cập nhật
    """
    # Kiểm tra nội dung nổi bật tồn tại
    featured_content = get_featured_content_by_id(db, id)

    if not featured_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nội dung nổi bật không tồn tại",
        )

    # Đổi trạng thái
    try:
        updated_featured = toggle_featured_content_status(db, id)
        new_status = "kích hoạt" if updated_featured.is_active else "vô hiệu hóa"
        logger.info(
            f"Admin {current_admin.username} đã đổi trạng thái nội dung nổi bật ID={id} thành {new_status}"
        )
        return updated_featured
    except ValueError as e:
        logger.error(f"Lỗi khi đổi trạng thái nội dung nổi bật ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:featured_content:delete")
@invalidate_cache(namespace="admin:featured_content")
@log_admin_action(action="delete", resource_type="featured_content", resource_id="{id}")
async def delete_featured_content_item(
    id: int = Path(..., ge=1, description="ID nội dung nổi bật"),
    current_admin: Admin = Depends(secure_admin_access(["featured_content:delete"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> None:
    """
    Xóa nội dung nổi bật.

    **Quyền yêu cầu**: `featured_content:delete`

    **Cách sử dụng**:
    - Cung cấp ID nội dung nổi bật cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra nội dung nổi bật tồn tại
    featured_content = get_featured_content_by_id(db, id)

    if not featured_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nội dung nổi bật không tồn tại",
        )

    # Xóa nội dung nổi bật
    try:
        deleted = delete_featured_content(db, id)

        if not deleted:
            logger.error(f"Không thể xóa nội dung nổi bật ID={id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể xóa nội dung nổi bật",
            )

        logger.info(
            f"Admin {current_admin.username} đã xóa nội dung nổi bật cho {featured_content.content_type} ID={featured_content.content_id}"
        )
    except ValueError as e:
        logger.error(f"Lỗi khi xóa nội dung nổi bật ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


#
