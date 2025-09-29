from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import date, datetime, timedelta

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    secure_admin_access,
)
from app.admin_site.models import Admin
from app.admin_site.services.dashboard_service import (
    get_dashboard_summary,
    get_recent_activities,
    get_dashboard_stats,
    get_alerts_and_notifications,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()


@router.get("/summary")
@profile_endpoint(name="admin:dashboard:summary")
@cached(ttl=300, namespace="admin:dashboard", key_prefix="summary")
@log_admin_action(
    action="view", resource_type="dashboard", description="Xem tóm tắt dashboard"
)
async def get_admin_dashboard_summary(
    current_admin: Admin = Depends(secure_admin_access(["dashboard:view"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Lấy tóm tắt dashboard cho admin.

    **Quyền yêu cầu**: `dashboard:view`

    **Kết quả**:
    - Tóm tắt chung về số liệu hệ thống, người dùng, nội dung và doanh thu
    """
    try:
        summary = get_dashboard_summary(db)
        logger.info(f"Admin {current_admin.username} đã xem tóm tắt dashboard")
        return summary
    except Exception as e:
        logger.error(f"Lỗi khi lấy tóm tắt dashboard: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Lỗi khi lấy tóm tắt dashboard: {str(e)}"
        )


@router.get("/stats")
@profile_endpoint(name="admin:dashboard:stats")
@cached(ttl=300, namespace="admin:dashboard", key_prefix="stats")
@log_admin_action(
    action="view", resource_type="dashboard", description="Xem thống kê dashboard"
)
async def get_admin_dashboard_statistics(
    period: Optional[str] = Query(
        "week", description="Khoảng thời gian (day, week, month, year)"
    ),
    current_admin: Admin = Depends(secure_admin_access(["dashboard:view"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê dashboard cho admin.

    **Quyền yêu cầu**: `dashboard:view`

    **Cách sử dụng**:
    - Chỉ định khoảng thời gian với tham số period (day, week, month, year)

    **Kết quả**:
    - Thống kê chi tiết về hoạt động hệ thống, người dùng, nội dung và doanh thu theo thời gian
    """
    # Xác định khoảng thời gian
    today = datetime.now(timezone.utc).date()

    if period == "day":
        start_date = today
    elif period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    elif period == "year":
        start_date = today - timedelta(days=365)
    else:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xem thống kê dashboard với khoảng thời gian không hợp lệ: {period}"
        )
        raise HTTPException(
            status_code=400,
            detail="Khoảng thời gian không hợp lệ. Sử dụng: day, week, month, year",
        )

    try:
        stats = get_dashboard_stats(db, start_date, today)
        logger.info(
            f"Admin {current_admin.username} đã xem thống kê dashboard cho khoảng thời gian: {period}"
        )
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê dashboard: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Lỗi khi lấy thống kê dashboard: {str(e)}"
        )


@router.get("/activities")
@profile_endpoint(name="admin:dashboard:activities")
@log_admin_action(
    action="view", resource_type="dashboard", description="Xem hoạt động gần đây"
)
async def get_admin_recent_activities(
    limit: int = Query(10, description="Số lượng hoạt động gần đây cần lấy"),
    current_admin: Admin = Depends(secure_admin_access(["dashboard:view"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Lấy hoạt động gần đây trên hệ thống.

    **Quyền yêu cầu**: `dashboard:view`

    **Cách sử dụng**:
    - Chỉ định số lượng hoạt động cần lấy với tham số limit

    **Kết quả**:
    - Danh sách hoạt động gần đây trên hệ thống
    """
    try:
        activities = get_recent_activities(db, limit)
        logger.info(f"Admin {current_admin.username} đã xem {limit} hoạt động gần đây")
        return {"activities": activities}
    except Exception as e:
        logger.error(f"Lỗi khi lấy hoạt động gần đây: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Lỗi khi lấy hoạt động gần đây: {str(e)}"
        )


@router.get("/alerts")
@profile_endpoint(name="admin:dashboard:alerts")
@log_admin_action(
    action="view", resource_type="dashboard", description="Xem cảnh báo và thông báo"
)
async def get_admin_alerts_notifications(
    current_admin: Admin = Depends(secure_admin_access(["dashboard:view"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Lấy cảnh báo và thông báo cho admin.

    **Quyền yêu cầu**: `dashboard:view`

    **Kết quả**:
    - Danh sách cảnh báo và thông báo cho admin
    """
    try:
        alerts = get_alerts_and_notifications(db, current_admin.id)
        logger.info(f"Admin {current_admin.username} đã xem cảnh báo và thông báo")
        return alerts
    except Exception as e:
        logger.error(f"Lỗi khi lấy cảnh báo và thông báo: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Lỗi khi lấy cảnh báo và thông báo: {str(e)}"
        )
