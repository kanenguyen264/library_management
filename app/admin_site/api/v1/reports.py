from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    secure_admin_access,
)
from app.admin_site.models import Admin
from app.admin_site.schemas.report import (
    UserReportResponse,
    ContentReportResponse,
    FinancialReportResponse,
    SystemReportResponse,
    ActivityReportResponse,
)
from app.admin_site.services.report_service import (
    get_user_report,
    get_content_report,
    get_financial_report,
    get_system_report,
    get_activity_report,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/reports/users - Lấy báo cáo về người dùng
# GET /api/v1/admin/reports/content - Lấy báo cáo về nội dung
# GET /api/v1/admin/reports/financial - Lấy báo cáo tài chính
# GET /api/v1/admin/reports/system - Lấy báo cáo hệ thống
# GET /api/v1/admin/reports/activity - Lấy báo cáo hoạt động


@router.get("/users", response_model=UserReportResponse)
@profile_endpoint(name="admin:reports:users")
@cached(ttl=3600, namespace="admin:reports", key_prefix="user_report")
@log_admin_action(
    action="view", resource_type="report", description="Xem báo cáo người dùng"
)
async def get_users_report(
    start_date: Optional[date] = Query(
        None, description="Ngày bắt đầu (mặc định: 30 ngày trước)"
    ),
    end_date: Optional[date] = Query(
        None, description="Ngày kết thúc (mặc định: hôm nay)"
    ),
    current_admin: Admin = Depends(secure_admin_access(["report:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> UserReportResponse:
    """
    Lấy báo cáo về người dùng.

    **Quyền yêu cầu**: `report:read`

    **Cách sử dụng**:
    - Chỉ định khoảng thời gian với start_date và end_date

    **Kết quả**:
    - Báo cáo về người dùng bao gồm: số lượng người dùng mới, người dùng hoạt động,
      phân bố theo tuổi, giới tính, vị trí địa lý, v.v.
    """
    # Thiết lập ngày mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc).date() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now(timezone.utc).date()

    # Kiểm tra khoảng thời gian hợp lệ
    if start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xem báo cáo với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    try:
        report = get_user_report(db, start_date, end_date)

        logger.info(
            f"Admin {current_admin.username} đã xem báo cáo người dùng từ {start_date} đến {end_date}"
        )

        return report
    except ValueError as e:
        logger.error(f"Lỗi khi lấy báo cáo người dùng: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/content", response_model=ContentReportResponse)
@profile_endpoint(name="admin:reports:content")
@cached(ttl=3600, namespace="admin:reports", key_prefix="content_report")
@log_admin_action(
    action="view", resource_type="report", description="Xem báo cáo nội dung"
)
async def get_content_report_data(
    start_date: Optional[date] = Query(
        None, description="Ngày bắt đầu (mặc định: 30 ngày trước)"
    ),
    end_date: Optional[date] = Query(
        None, description="Ngày kết thúc (mặc định: hôm nay)"
    ),
    content_type: Optional[str] = Query(
        None, description="Loại nội dung (books, authors, series)"
    ),
    current_admin: Admin = Depends(secure_admin_access(["report:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> ContentReportResponse:
    """
    Lấy báo cáo về nội dung.

    **Quyền yêu cầu**: `report:read`

    **Cách sử dụng**:
    - Chỉ định khoảng thời gian với start_date và end_date
    - Lọc theo loại nội dung với tham số content_type

    **Kết quả**:
    - Báo cáo về nội dung bao gồm: số lượng sách mới, tác giả mới, đánh giá,
      nội dung phổ biến, thể loại phổ biến, v.v.
    """
    # Thiết lập ngày mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc).date() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now(timezone.utc).date()

    # Kiểm tra khoảng thời gian hợp lệ
    if start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xem báo cáo nội dung với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    try:
        report = get_content_report(db, start_date, end_date, content_type)

        logger.info(
            f"Admin {current_admin.username} đã xem báo cáo nội dung từ {start_date} đến {end_date}"
        )

        return report
    except ValueError as e:
        logger.error(f"Lỗi khi lấy báo cáo nội dung: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/financial", response_model=FinancialReportResponse)
@profile_endpoint(name="admin:reports:financial")
@cached(ttl=3600, namespace="admin:reports", key_prefix="financial_report")
@log_admin_action(
    action="view", resource_type="report", description="Xem báo cáo tài chính"
)
async def get_financial_report_data(
    start_date: Optional[date] = Query(
        None, description="Ngày bắt đầu (mặc định: 30 ngày trước)"
    ),
    end_date: Optional[date] = Query(
        None, description="Ngày kết thúc (mặc định: hôm nay)"
    ),
    current_admin: Admin = Depends(secure_admin_access(["report:financial"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> FinancialReportResponse:
    """
    Lấy báo cáo tài chính.

    **Quyền yêu cầu**: `report:financial`

    **Cách sử dụng**:
    - Chỉ định khoảng thời gian với start_date và end_date

    **Kết quả**:
    - Báo cáo tài chính bao gồm: doanh thu, số lượng đăng ký, chuyển đổi, v.v.
    """
    # Thiết lập ngày mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc).date() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now(timezone.utc).date()

    # Kiểm tra khoảng thời gian hợp lệ
    if start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xem báo cáo tài chính với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    try:
        report = get_financial_report(db, start_date, end_date)

        logger.info(
            f"Admin {current_admin.username} đã xem báo cáo tài chính từ {start_date} đến {end_date}"
        )

        return report
    except ValueError as e:
        logger.error(f"Lỗi khi lấy báo cáo tài chính: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/system", response_model=SystemReportResponse)
@profile_endpoint(name="admin:reports:system")
@cached(ttl=3600, namespace="admin:reports", key_prefix="system_report")
@log_admin_action(
    action="view", resource_type="report", description="Xem báo cáo hệ thống"
)
async def get_system_report_data(
    start_date: Optional[date] = Query(
        None, description="Ngày bắt đầu (mặc định: 7 ngày trước)"
    ),
    end_date: Optional[date] = Query(
        None, description="Ngày kết thúc (mặc định: hôm nay)"
    ),
    current_admin: Admin = Depends(secure_admin_access(["report:system"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemReportResponse:
    """
    Lấy báo cáo hệ thống.

    **Quyền yêu cầu**: `report:system`

    **Cách sử dụng**:
    - Chỉ định khoảng thời gian với start_date và end_date

    **Kết quả**:
    - Báo cáo hệ thống bao gồm: hiệu suất, thời gian phản hồi, lỗi, sử dụng tài nguyên, v.v.
    """
    # Thiết lập ngày mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc).date() - timedelta(days=7)
    if not end_date:
        end_date = datetime.now(timezone.utc).date()

    # Kiểm tra khoảng thời gian hợp lệ
    if start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xem báo cáo hệ thống với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    try:
        report = get_system_report(db, start_date, end_date)

        logger.info(
            f"Admin {current_admin.username} đã xem báo cáo hệ thống từ {start_date} đến {end_date}"
        )

        return report
    except ValueError as e:
        logger.error(f"Lỗi khi lấy báo cáo hệ thống: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/activity", response_model=ActivityReportResponse)
@profile_endpoint(name="admin:reports:activity")
@cached(ttl=3600, namespace="admin:reports", key_prefix="activity_report")
@log_admin_action(
    action="view", resource_type="report", description="Xem báo cáo hoạt động"
)
async def get_activity_report_data(
    start_date: Optional[date] = Query(
        None, description="Ngày bắt đầu (mặc định: 30 ngày trước)"
    ),
    end_date: Optional[date] = Query(
        None, description="Ngày kết thúc (mặc định: hôm nay)"
    ),
    activity_type: Optional[str] = Query(None, description="Loại hoạt động"),
    current_admin: Admin = Depends(secure_admin_access(["report:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> ActivityReportResponse:
    """
    Lấy báo cáo hoạt động.

    **Quyền yêu cầu**: `report:read`

    **Cách sử dụng**:
    - Chỉ định khoảng thời gian với start_date và end_date
    - Lọc theo loại hoạt động với tham số activity_type

    **Kết quả**:
    - Báo cáo hoạt động bao gồm: lượt xem, lượt đọc, lượt tải, tương tác, v.v.
    """
    # Thiết lập ngày mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc).date() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now(timezone.utc).date()

    # Kiểm tra khoảng thời gian hợp lệ
    if start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xem báo cáo hoạt động với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    try:
        report = get_activity_report(db, start_date, end_date, activity_type)

        logger.info(
            f"Admin {current_admin.username} đã xem báo cáo hoạt động từ {start_date} đến {end_date}"
        )

        return report
    except ValueError as e:
        logger.error(f"Lỗi khi lấy báo cáo hoạt động: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/export/{report_type}")
@profile_endpoint(name="admin:reports:export")
@log_admin_action(action="export", resource_type="report", resource_id="{report_type}")
async def export_report(
    report_type: str = Path(
        ..., description="Loại báo cáo (users, content, financial, system, activity)"
    ),
    format: str = Query("csv", description="Định dạng xuất (csv, excel, pdf)"),
    start_date: Optional[date] = Query(
        None, description="Ngày bắt đầu (mặc định: 30 ngày trước)"
    ),
    end_date: Optional[date] = Query(
        None, description="Ngày kết thúc (mặc định: hôm nay)"
    ),
    current_admin: Admin = Depends(secure_admin_access(["report:export"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Xuất báo cáo theo định dạng.

    **Quyền yêu cầu**: `report:export`

    **Cách sử dụng**:
    - Chỉ định loại báo cáo cần xuất
    - Chỉ định định dạng xuất (csv, excel, pdf)
    - Chỉ định khoảng thời gian với start_date và end_date

    **Kết quả**:
    - Đường dẫn tải tệp báo cáo đã xuất
    """
    # Thiết lập ngày mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc).date() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now(timezone.utc).date()

    # Kiểm tra khoảng thời gian hợp lệ
    if start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xuất báo cáo với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    # Kiểm tra loại báo cáo hợp lệ
    valid_report_types = ["users", "content", "financial", "system", "activity"]
    if report_type not in valid_report_types:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xuất báo cáo với loại báo cáo không hợp lệ: {report_type}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Loại báo cáo không hợp lệ. Giá trị hợp lệ: {', '.join(valid_report_types)}",
        )

    # Kiểm tra định dạng hợp lệ
    valid_formats = ["csv", "excel", "pdf"]
    if format not in valid_formats:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng xuất báo cáo với định dạng không hợp lệ: {format}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng không hợp lệ. Giá trị hợp lệ: {', '.join(valid_formats)}",
        )

    # Tạm thời trả về kết quả giả lập vì chưa có dịch vụ xuất báo cáo thực tế
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{report_type}_{timestamp}.{format}"

    logger.info(
        f"Admin {current_admin.username} đã xuất báo cáo {report_type} từ {start_date} đến {end_date} định dạng {format}"
    )

    return {
        "message": "Xuất báo cáo thành công",
        "download_url": f"/api/v1/admin/downloads/reports/{filename}",
    }
