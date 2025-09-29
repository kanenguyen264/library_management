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
from app.admin_site.models import Admin, ContentApprovalQueue
from app.admin_site.schemas.content_approval import (
    ContentApprovalCreate,
    ContentApprovalUpdate,
    ContentApprovalInfo,
    ContentApprovalAction,
)
from app.admin_site.services.content_approval_service import (
    create_content_approval,
    update_content_approval,
    get_content_approval_by_id,
    get_all_content_approvals,
    approve_content,
    reject_content,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/content-approval - Lấy danh sách nội dung chờ phê duyệt
# GET /api/v1/admin/content-approval/{id} - Lấy thông tin chi tiết nội dung chờ phê duyệt
# POST /api/v1/admin/content-approval - Tạo yêu cầu phê duyệt mới
# PUT /api/v1/admin/content-approval/{id} - Cập nhật thông tin yêu cầu phê duyệt
# POST /api/v1/admin/content-approval/{id}/approve - Phê duyệt nội dung
# POST /api/v1/admin/content-approval/{id}/reject - Từ chối nội dung


@router.get("", response_model=List[ContentApprovalInfo])
@profile_endpoint(name="admin:content_approval:list")
@cached(ttl=60, namespace="admin:content_approval", key_prefix="approval_list")
@log_admin_action(
    action="view",
    resource_type="content_approval",
    description="Xem danh sách nội dung chờ phê duyệt",
)
async def read_content_approvals(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    content_type: Optional[str] = Query(None, description="Lọc theo loại nội dung"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái"),
    current_admin: Admin = Depends(secure_admin_access(["content_approval:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[ContentApprovalInfo]:
    """
    Lấy danh sách nội dung chờ phê duyệt.

    **Quyền yêu cầu**: `content_approval:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Lọc theo loại nội dung với tham số content_type
    - Lọc theo trạng thái với tham số status

    **Kết quả**:
    - Danh sách nội dung chờ phê duyệt
    """
    approvals = get_all_content_approvals(db, skip, limit, content_type, status)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(approvals)} nội dung chờ phê duyệt"
    )

    return approvals


@router.get("/{id}", response_model=ContentApprovalInfo)
@profile_endpoint(name="admin:content_approval:detail")
@cached(ttl=60, namespace="admin:content_approval", key_prefix="approval_detail")
@log_admin_action(action="view", resource_type="content_approval", resource_id="{id}")
async def read_content_approval(
    id: int = Path(..., ge=1, description="ID nội dung chờ phê duyệt"),
    current_admin: Admin = Depends(secure_admin_access(["content_approval:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> ContentApprovalInfo:
    """
    Lấy thông tin chi tiết nội dung chờ phê duyệt.

    **Quyền yêu cầu**: `content_approval:read`

    **Cách sử dụng**:
    - Cung cấp ID nội dung chờ phê duyệt cần xem

    **Kết quả**:
    - Thông tin chi tiết nội dung chờ phê duyệt
    """
    approval = get_content_approval_by_id(db, id)

    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nội dung chờ phê duyệt không tồn tại",
        )

    logger.info(
        f"Admin {current_admin.username} đã xem thông tin nội dung chờ phê duyệt ID={id}"
    )

    return approval


@router.post(
    "", response_model=ContentApprovalInfo, status_code=status.HTTP_201_CREATED
)
@profile_endpoint(name="admin:content_approval:create")
@invalidate_cache(namespace="admin:content_approval")
@log_admin_action(
    action="create",
    resource_type="content_approval",
    description="Tạo yêu cầu phê duyệt nội dung mới",
)
async def create_new_content_approval(
    approval_data: ContentApprovalCreate,
    current_admin: Admin = Depends(secure_admin_access(["content_approval:create"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> ContentApprovalInfo:
    """
    Tạo yêu cầu phê duyệt nội dung mới.

    **Quyền yêu cầu**: `content_approval:create`

    **Cách sử dụng**:
    - Cung cấp thông tin yêu cầu phê duyệt trong body

    **Kết quả**:
    - Thông tin yêu cầu phê duyệt đã tạo
    """
    # Tạo yêu cầu phê duyệt mới
    try:
        new_approval = create_content_approval(db, approval_data)
        logger.info(
            f"Admin {current_admin.username} đã tạo yêu cầu phê duyệt nội dung mới cho {new_approval.content_type} ID={new_approval.content_id}"
        )
        return new_approval
    except ValueError as e:
        logger.error(f"Lỗi khi tạo yêu cầu phê duyệt nội dung mới: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=ContentApprovalInfo)
@profile_endpoint(name="admin:content_approval:update")
@invalidate_cache(namespace="admin:content_approval")
@log_admin_action(action="update", resource_type="content_approval", resource_id="{id}")
async def update_content_approval_info(
    id: int = Path(..., ge=1, description="ID nội dung chờ phê duyệt"),
    approval_data: ContentApprovalUpdate = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["content_approval:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> ContentApprovalInfo:
    """
    Cập nhật thông tin yêu cầu phê duyệt nội dung.

    **Quyền yêu cầu**: `content_approval:update`

    **Cách sử dụng**:
    - Cung cấp ID yêu cầu phê duyệt cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin yêu cầu phê duyệt đã cập nhật
    """
    # Kiểm tra yêu cầu phê duyệt tồn tại
    approval = get_content_approval_by_id(db, id)

    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nội dung chờ phê duyệt không tồn tại",
        )

    # Cập nhật yêu cầu phê duyệt
    try:
        updated_approval = update_content_approval(db, id, approval_data)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật thông tin yêu cầu phê duyệt nội dung ID={id}"
        )
        return updated_approval
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật yêu cầu phê duyệt nội dung ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{id}/approve", response_model=ContentApprovalInfo)
@profile_endpoint(name="admin:content_approval:approve")
@invalidate_cache(namespace="admin:content_approval")
@log_admin_action(
    action="approve", resource_type="content_approval", resource_id="{id}"
)
async def approve_content_item(
    id: int = Path(..., ge=1, description="ID nội dung chờ phê duyệt"),
    action_data: ContentApprovalAction = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["content_approval:approve"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> ContentApprovalInfo:
    """
    Phê duyệt nội dung.

    **Quyền yêu cầu**: `content_approval:approve`

    **Cách sử dụng**:
    - Cung cấp ID nội dung cần phê duyệt
    - Cung cấp ghi chú phê duyệt trong body

    **Kết quả**:
    - Thông tin yêu cầu phê duyệt đã cập nhật
    """
    # Kiểm tra yêu cầu phê duyệt tồn tại
    approval = get_content_approval_by_id(db, id)

    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nội dung chờ phê duyệt không tồn tại",
        )

    # Phê duyệt nội dung
    try:
        approved_approval = approve_content(db, id, current_admin.id, action_data.notes)
        logger.info(f"Admin {current_admin.username} đã phê duyệt nội dung ID={id}")
        return approved_approval
    except ValueError as e:
        logger.error(f"Lỗi khi phê duyệt nội dung ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{id}/reject", response_model=ContentApprovalInfo)
@profile_endpoint(name="admin:content_approval:reject")
@invalidate_cache(namespace="admin:content_approval")
@log_admin_action(action="reject", resource_type="content_approval", resource_id="{id}")
async def reject_content_item(
    id: int = Path(..., ge=1, description="ID nội dung chờ phê duyệt"),
    action_data: ContentApprovalAction = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["content_approval:reject"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> ContentApprovalInfo:
    """
    Từ chối nội dung.

    **Quyền yêu cầu**: `content_approval:reject`

    **Cách sử dụng**:
    - Cung cấp ID nội dung cần từ chối
    - Cung cấp ghi chú từ chối trong body

    **Kết quả**:
    - Thông tin yêu cầu phê duyệt đã cập nhật
    """
    # Kiểm tra yêu cầu phê duyệt tồn tại
    approval = get_content_approval_by_id(db, id)

    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nội dung chờ phê duyệt không tồn tại",
        )

    # Từ chối nội dung
    try:
        rejected_approval = reject_content(db, id, current_admin.id, action_data.notes)
        logger.info(f"Admin {current_admin.username} đã từ chối nội dung ID={id}")
        return rejected_approval
    except ValueError as e:
        logger.error(f"Lỗi khi từ chối nội dung ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
