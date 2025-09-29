from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    get_super_admin,
    secure_admin_access,
)
from app.admin_site.models import Admin, AdminSession
from app.admin_site.schemas.admin_session import AdminSessionInfo
from app.admin_site.services.admin_session_service import (
    get_admin_sessions,
    get_admin_session_by_id,
    invalidate_session,
    invalidate_all_admin_sessions,
    clean_expired_sessions,
)
from app.security.audit.log_admin_action import log_admin_action
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()


@router.get("", response_model=List[AdminSessionInfo])
@profile_endpoint(name="admin:sessions:list")
@log_admin_action(
    action="view",
    resource_type="admin_session",
    description="Xem danh sách phiên đăng nhập",
)
async def read_admin_sessions(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    admin_id: Optional[int] = Query(None, description="Lọc theo ID admin"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái"),
    ip_address: Optional[str] = Query(None, description="Lọc theo địa chỉ IP"),
    current_admin: Admin = Depends(secure_admin_access(["admin_session:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[AdminSessionInfo]:
    """
    Lấy danh sách phiên đăng nhập admin.

    **Quyền yêu cầu**: `admin_session:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Lọc theo ID admin, trạng thái, địa chỉ IP

    **Kết quả**:
    - Danh sách phiên đăng nhập admin
    """
    # Nếu không phải super admin thì chỉ được xem phiên của chính mình
    if (
        not current_admin.is_super_admin
        and admin_id is not None
        and admin_id != current_admin.id
    ):
        logger.warning(
            f"Admin {current_admin.username} đang cố xem phiên đăng nhập của admin khác"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền xem phiên đăng nhập của admin khác",
        )

    # Nếu không phải super admin và không có admin_id thì set admin_id là ID của admin hiện tại
    if not current_admin.is_super_admin and admin_id is None:
        admin_id = current_admin.id

    sessions = get_admin_sessions(db, skip, limit, admin_id, status, ip_address)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(sessions)} phiên đăng nhập"
    )

    return sessions


@router.get("/{id}", response_model=AdminSessionInfo)
@profile_endpoint(name="admin:sessions:detail")
@log_admin_action(action="view", resource_type="admin_session", resource_id="{id}")
async def read_admin_session(
    id: int = Path(..., ge=1, description="ID phiên đăng nhập"),
    current_admin: Admin = Depends(secure_admin_access(["admin_session:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> AdminSessionInfo:
    """
    Lấy thông tin chi tiết phiên đăng nhập.

    **Quyền yêu cầu**: `admin_session:read`

    **Cách sử dụng**:
    - Cung cấp ID phiên đăng nhập cần xem

    **Kết quả**:
    - Thông tin chi tiết phiên đăng nhập
    """
    session = get_admin_session_by_id(db, id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phiên đăng nhập không tồn tại",
        )

    # Nếu không phải super admin thì chỉ được xem phiên của chính mình
    if not current_admin.is_super_admin and session.admin_id != current_admin.id:
        logger.warning(
            f"Admin {current_admin.username} đang cố xem phiên đăng nhập ID={id} của admin khác"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền xem phiên đăng nhập của admin khác",
        )

    logger.info(
        f"Admin {current_admin.username} đã xem thông tin phiên đăng nhập ID={id}"
    )

    return session


@router.post("/{id}/invalidate", status_code=status.HTTP_200_OK)
@profile_endpoint(name="admin:sessions:invalidate")
@log_admin_action(
    action="update",
    resource_type="admin_session",
    resource_id="{id}",
    description="Vô hiệu hóa phiên đăng nhập",
)
async def invalidate_admin_session(
    id: int = Path(..., ge=1, description="ID phiên đăng nhập"),
    current_admin: Admin = Depends(secure_admin_access(["admin_session:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Vô hiệu hóa phiên đăng nhập (đăng xuất).

    **Quyền yêu cầu**: `admin_session:update`

    **Cách sử dụng**:
    - Cung cấp ID phiên đăng nhập cần vô hiệu hóa

    **Kết quả**:
    - Thông báo kết quả vô hiệu hóa
    """
    session = get_admin_session_by_id(db, id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phiên đăng nhập không tồn tại",
        )

    # Nếu không phải super admin thì chỉ được vô hiệu hóa phiên của chính mình
    if not current_admin.is_super_admin and session.admin_id != current_admin.id:
        logger.warning(
            f"Admin {current_admin.username} đang cố vô hiệu hóa phiên đăng nhập ID={id} của admin khác"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền vô hiệu hóa phiên đăng nhập của admin khác",
        )

    # Vô hiệu hóa phiên
    success = invalidate_session(db, session.token)

    if not success:
        logger.error(f"Không thể vô hiệu hóa phiên đăng nhập ID={id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể vô hiệu hóa phiên đăng nhập",
        )

    logger.info(
        f"Admin {current_admin.username} đã vô hiệu hóa phiên đăng nhập ID={id}"
    )

    return {"message": "Phiên đăng nhập đã được vô hiệu hóa"}


@router.post("/admin/{admin_id}/invalidate-all", status_code=status.HTTP_200_OK)
@profile_endpoint(name="admin:sessions:invalidate_all")
@log_admin_action(
    action="update",
    resource_type="admin_session",
    description="Vô hiệu hóa tất cả phiên đăng nhập",
    resource_id="{admin_id}",
)
async def invalidate_all_sessions(
    admin_id: int = Path(..., ge=1, description="ID admin"),
    current_admin: Admin = Depends(get_super_admin),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Vô hiệu hóa tất cả phiên đăng nhập của admin.

    **Quyền yêu cầu**: Super Admin

    **Cách sử dụng**:
    - Cung cấp ID admin cần vô hiệu hóa tất cả phiên

    **Kết quả**:
    - Thông báo kết quả vô hiệu hóa
    """
    # Vô hiệu hóa tất cả phiên
    count = invalidate_all_admin_sessions(db, admin_id)

    logger.info(
        f"Admin {current_admin.username} đã vô hiệu hóa {count} phiên đăng nhập của admin ID={admin_id}"
    )

    return {"message": f"Đã vô hiệu hóa {count} phiên đăng nhập"}


@router.post("/cleanup", status_code=status.HTTP_200_OK)
@profile_endpoint(name="admin:sessions:cleanup")
@log_admin_action(
    action="delete",
    resource_type="admin_session",
    description="Dọn dẹp phiên đăng nhập hết hạn",
)
async def cleanup_sessions(
    days: int = Query(30, ge=1, description="Số ngày trước khi xem là hết hạn"),
    current_admin: Admin = Depends(get_super_admin),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Xóa các phiên đăng nhập đã hết hạn.

    **Quyền yêu cầu**: Super Admin

    **Cách sử dụng**:
    - Chỉ định số ngày trước khi xem là hết hạn

    **Kết quả**:
    - Thông báo kết quả xóa
    """
    # Xóa các phiên hết hạn
    count = clean_expired_sessions(db, days)

    logger.info(
        f"Admin {current_admin.username} đã xóa {count} phiên đăng nhập hết hạn"
    )

    return {"message": f"Đã xóa {count} phiên đăng nhập hết hạn"}
