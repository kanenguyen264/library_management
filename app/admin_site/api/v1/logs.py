from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date

from app.common.db.session import get_db
from app.admin_site.api.deps import get_current_admin, check_admin_permissions
from app.admin_site.models import Admin
from app.logs_manager.services import (
    # User Activity Logs
    get_user_activity_logs,
    get_user_activity_log,
    get_user_activities_by_user,
    # Admin Activity Logs
    get_admin_activity_logs,
    get_admin_activities_by_admin,
    # Error Logs
    get_error_logs,
    get_error_logs_by_level,
    # Authentication Logs
    get_authentication_logs,
    get_authentication_logs_by_user,
    get_authentication_logs_by_admin,
    get_failed_authentication_attempts,
    # API Request Logs
    get_api_request_logs,
    get_requests_by_endpoint,
    get_endpoint_stats,
    # Performance Logs
    get_performance_logs,
    get_slow_operations,
    get_slow_endpoints,
    get_performance_stats,
    # Search Logs
    get_search_logs,
    get_popular_search_terms,
    get_zero_results_searches,
    # Log Analysis
    get_log_summary,
    get_error_trends,
    get_user_activity_trends,
    get_admin_activity_trends,
    get_api_usage_trends,
    get_performance_trends,
    get_authentication_trends,
    get_search_trends,
)
from app.logs_manager.schemas.user_activity_log import UserActivityLogRead
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogRead
from app.logs_manager.schemas.error_log import ErrorLogRead
from app.logs_manager.schemas.authentication_log import AuthenticationLogRead
from app.logs_manager.schemas.api_request_log import ApiRequestLogRead
from app.logs_manager.schemas.performance_log import PerformanceLogRead
from app.logs_manager.schemas.search_log import SearchLogRead
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint
from app.cache.decorators import cached
from app.security.audit.log_admin_action import log_admin_action

logger = get_logger(__name__)
router = APIRouter()


@router.get("/user-activity", response_model=List[UserActivityLogRead])
@profile_endpoint(name="admin:logs:user_activity")
@log_admin_action(
    action="view",
    resource_type="user_activity_log",
    description="Admin viewed user activity logs",
)
@cached(
    ttl=300,
    namespace="admin:logs:user_activity",
    key_prefix="user_activity_logs",
    include_args_types=True,
)
async def read_user_activity_logs(
    start_date: Optional[datetime] = Query(None, description="Thời gian bắt đầu"),
    end_date: Optional[datetime] = Query(None, description="Thời gian kết thúc"),
    user_id: Optional[int] = Query(None, description="ID người dùng"),
    activity_type: Optional[str] = Query(None, description="Loại hoạt động"),
    skip: int = Query(0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(100, description="Số lượng bản ghi tối đa"),
    current_admin: Admin = Depends(check_admin_permissions(["log:read"])),
    db: Session = Depends(get_db),
) -> List[UserActivityLogRead]:
    """
    Lấy nhật ký hoạt động của người dùng.

    **Quyền yêu cầu**: `log:read`

    **Tham số**:
    - **start_date**: Thời gian bắt đầu
    - **end_date**: Thời gian kết thúc
    - **user_id**: ID người dùng
    - **activity_type**: Loại hoạt động
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa

    **Kết quả**:
    - Danh sách nhật ký hoạt động của người dùng
    """
    # Thiết lập thời gian mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    if not end_date:
        end_date = datetime.now(timezone.utc)

    logs = get_user_activity_logs(
        db,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        activity_type=activity_type,
        skip=skip,
        limit=limit,
    )

    logger.info(f"Admin {current_admin.username} đã xem nhật ký hoạt động người dùng")

    return logs.items


@router.get("/admin-activity", response_model=List[AdminActivityLogRead])
@profile_endpoint(name="admin:logs:admin_activity")
@log_admin_action(
    action="view",
    resource_type="admin_activity_log",
    description="Admin viewed admin activity logs",
)
@cached(
    ttl=300,
    namespace="admin:logs:admin_activity",
    key_prefix="admin_activity_logs",
    include_args_types=True,
)
async def read_admin_activity_logs(
    start_date: Optional[datetime] = Query(None, description="Thời gian bắt đầu"),
    end_date: Optional[datetime] = Query(None, description="Thời gian kết thúc"),
    admin_id: Optional[int] = Query(None, description="ID admin"),
    activity_type: Optional[str] = Query(None, description="Loại hoạt động"),
    skip: int = Query(0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(100, description="Số lượng bản ghi tối đa"),
    current_admin: Admin = Depends(check_admin_permissions(["log:admin"])),
    db: Session = Depends(get_db),
) -> List[AdminActivityLogRead]:
    """
    Lấy nhật ký hoạt động của admin.

    **Quyền yêu cầu**: `log:admin`

    **Tham số**:
    - **start_date**: Thời gian bắt đầu
    - **end_date**: Thời gian kết thúc
    - **admin_id**: ID admin
    - **activity_type**: Loại hoạt động
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa

    **Kết quả**:
    - Danh sách nhật ký hoạt động của admin
    """
    # Thiết lập thời gian mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    if not end_date:
        end_date = datetime.now(timezone.utc)

    logs = get_admin_activity_logs(
        db,
        start_date=start_date,
        end_date=end_date,
        admin_id=admin_id,
        activity_type=activity_type,
        skip=skip,
        limit=limit,
    )

    logger.info(f"Admin {current_admin.username} đã xem nhật ký hoạt động admin")

    return logs.items


@router.get("/errors", response_model=List[ErrorLogRead])
@profile_endpoint(name="admin:logs:errors")
@log_admin_action(
    action="view", resource_type="error_log", description="Admin viewed error logs"
)
@cached(
    ttl=300,
    namespace="admin:logs:errors",
    key_prefix="error_logs",
    include_args_types=True,
)
async def read_error_logs(
    start_date: Optional[datetime] = Query(None, description="Thời gian bắt đầu"),
    end_date: Optional[datetime] = Query(None, description="Thời gian kết thúc"),
    error_level: Optional[str] = Query(None, description="Mức độ lỗi"),
    component: Optional[str] = Query(None, description="Thành phần gây lỗi"),
    skip: int = Query(0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(100, description="Số lượng bản ghi tối đa"),
    current_admin: Admin = Depends(check_admin_permissions(["log:error"])),
    db: Session = Depends(get_db),
) -> List[ErrorLogRead]:
    """
    Lấy nhật ký lỗi hệ thống.

    **Quyền yêu cầu**: `log:error`

    **Tham số**:
    - **start_date**: Thời gian bắt đầu
    - **end_date**: Thời gian kết thúc
    - **error_level**: Mức độ lỗi
    - **component**: Thành phần gây lỗi
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa

    **Kết quả**:
    - Danh sách nhật ký lỗi hệ thống
    """
    # Thiết lập thời gian mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    if not end_date:
        end_date = datetime.now(timezone.utc)

    logs = get_error_logs(
        db,
        start_date=start_date,
        end_date=end_date,
        error_level=error_level,
        source=component,
        skip=skip,
        limit=limit,
    )

    logger.info(f"Admin {current_admin.username} đã xem nhật ký lỗi hệ thống")

    return logs.items


@router.get("/authentication", response_model=List[AuthenticationLogRead])
@profile_endpoint(name="admin:logs:authentication")
@log_admin_action(
    action="view",
    resource_type="authentication_log",
    description="Admin viewed authentication logs",
)
@cached(
    ttl=300,
    namespace="admin:logs:authentication",
    key_prefix="authentication_logs",
    include_args_types=True,
)
async def read_authentication_logs(
    start_date: Optional[datetime] = Query(None, description="Thời gian bắt đầu"),
    end_date: Optional[datetime] = Query(None, description="Thời gian kết thúc"),
    user_id: Optional[int] = Query(None, description="ID người dùng"),
    admin_id: Optional[int] = Query(None, description="ID admin"),
    auth_type: Optional[str] = Query(None, description="Loại xác thực"),
    status: Optional[str] = Query(None, description="Trạng thái"),
    skip: int = Query(0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(100, description="Số lượng bản ghi tối đa"),
    current_admin: Admin = Depends(check_admin_permissions(["log:auth"])),
    db: Session = Depends(get_db),
) -> List[AuthenticationLogRead]:
    """
    Lấy nhật ký xác thực.

    **Quyền yêu cầu**: `log:auth`

    **Tham số**:
    - **start_date**: Thời gian bắt đầu
    - **end_date**: Thời gian kết thúc
    - **user_id**: ID người dùng
    - **admin_id**: ID admin
    - **auth_type**: Loại xác thực
    - **status**: Trạng thái
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa

    **Kết quả**:
    - Danh sách nhật ký xác thực
    """
    # Thiết lập thời gian mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    if not end_date:
        end_date = datetime.now(timezone.utc)

    logs = get_authentication_logs(
        db,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        admin_id=admin_id,
        action=auth_type,
        status=status,
        skip=skip,
        limit=limit,
    )

    logger.info(f"Admin {current_admin.username} đã xem nhật ký xác thực")

    return logs.items


@router.get("/api-requests", response_model=List[ApiRequestLogRead])
@profile_endpoint(name="admin:logs:api_requests")
@log_admin_action(
    action="view",
    resource_type="api_request_log",
    description="Admin viewed API request logs",
)
@cached(
    ttl=300,
    namespace="admin:logs:api_requests",
    key_prefix="api_request_logs",
    include_args_types=True,
)
async def read_api_request_logs(
    start_date: Optional[datetime] = Query(None, description="Thời gian bắt đầu"),
    end_date: Optional[datetime] = Query(None, description="Thời gian kết thúc"),
    endpoint: Optional[str] = Query(None, description="Endpoint API"),
    method: Optional[str] = Query(None, description="Phương thức HTTP"),
    status_code: Optional[int] = Query(None, description="Mã trạng thái HTTP"),
    skip: int = Query(0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(100, description="Số lượng bản ghi tối đa"),
    current_admin: Admin = Depends(check_admin_permissions(["log:api"])),
    db: Session = Depends(get_db),
) -> List[ApiRequestLogRead]:
    """
    Lấy nhật ký yêu cầu API.

    **Quyền yêu cầu**: `log:api`

    **Tham số**:
    - **start_date**: Thời gian bắt đầu
    - **end_date**: Thời gian kết thúc
    - **endpoint**: Endpoint API
    - **method**: Phương thức HTTP
    - **status_code**: Mã trạng thái HTTP
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa

    **Kết quả**:
    - Danh sách nhật ký yêu cầu API
    """
    # Thiết lập thời gian mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    if not end_date:
        end_date = datetime.now(timezone.utc)

    logs = get_api_request_logs(
        db,
        start_date=start_date,
        end_date=end_date,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        skip=skip,
        limit=limit,
    )

    logger.info(f"Admin {current_admin.username} đã xem nhật ký yêu cầu API")

    return logs.items


@router.get("/search", response_model=List[SearchLogRead])
@profile_endpoint(name="admin:logs:search")
@log_admin_action(
    action="view", resource_type="search_log", description="Admin viewed search logs"
)
@cached(
    ttl=300,
    namespace="admin:logs:search",
    key_prefix="search_logs",
    include_args_types=True,
)
async def read_search_logs(
    start_date: Optional[datetime] = Query(None, description="Thời gian bắt đầu"),
    end_date: Optional[datetime] = Query(None, description="Thời gian kết thúc"),
    user_id: Optional[int] = Query(None, description="ID người dùng"),
    query: Optional[str] = Query(None, description="Truy vấn tìm kiếm"),
    skip: int = Query(0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(100, description="Số lượng bản ghi tối đa"),
    current_admin: Admin = Depends(check_admin_permissions(["log:read"])),
    db: Session = Depends(get_db),
) -> List[SearchLogRead]:
    """
    Lấy nhật ký tìm kiếm.

    **Quyền yêu cầu**: `log:read`

    **Tham số**:
    - **start_date**: Thời gian bắt đầu
    - **end_date**: Thời gian kết thúc
    - **user_id**: ID người dùng
    - **query**: Truy vấn tìm kiếm
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa

    **Kết quả**:
    - Danh sách nhật ký tìm kiếm
    """
    # Thiết lập thời gian mặc định
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)
    if not end_date:
        end_date = datetime.now(timezone.utc)

    logs = get_search_logs(
        db,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        query_term=query,
        skip=skip,
        limit=limit,
    )

    logger.info(f"Admin {current_admin.username} đã xem nhật ký tìm kiếm")

    return logs.items


@router.get("/summary")
@profile_endpoint(name="admin:logs:summary")
@log_admin_action(
    action="view", resource_type="log_summary", description="Admin viewed log summary"
)
@cached(
    ttl=1800,
    namespace="admin:logs:summary",
    key_prefix="log_summary",
    include_args_types=True,
)
async def read_logs_summary(
    days: int = Query(30, description="Số ngày để phân tích"),
    current_admin: Admin = Depends(check_admin_permissions(["logs:read"])),
    db: Session = Depends(get_db),
):
    """Lấy tổng quan về logs trong hệ thống"""
    return await get_log_summary(db, days)


@router.get("/user-activity/{log_id}", response_model=UserActivityLogRead)
@profile_endpoint(name="admin:logs:user_activity_detail")
@log_admin_action(action="view", resource_type="user_activity_log")
async def read_user_activity_log(
    log_id: int = Path(..., ge=1),
    current_admin: Admin = Depends(check_admin_permissions(["logs:read"])),
    db: Session = Depends(get_db),
):
    """Lấy chi tiết log hoạt động của người dùng theo ID"""
    return get_user_activity_log(db, log_id)


@router.get(
    "/admin-activity/by-admin/{admin_id}", response_model=List[AdminActivityLogRead]
)
@profile_endpoint(name="admin:logs:admin_activities_by_admin")
@log_admin_action(action="view", resource_type="admin_activity_log")
@cached(
    ttl=300,
    namespace="admin:logs:admin_activities",
    key_prefix="admin_activities_by_admin",
    include_args_types=True,
)
async def read_admin_activities_by_admin(
    admin_id: int = Path(..., ge=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    activity_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_admin: Admin = Depends(check_admin_permissions(["logs:admin"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách logs hoạt động của một admin cụ thể"""
    logs = get_admin_activities_by_admin(
        db, admin_id, skip, limit, activity_type, start_date, end_date
    )
    return logs.items


@router.get("/errors/by-level/{error_level}", response_model=List[ErrorLogRead])
@profile_endpoint(name="admin:logs:errors_by_level")
@log_admin_action(action="view", resource_type="error_log")
@cached(
    ttl=300,
    namespace="admin:logs:errors",
    key_prefix="errors_by_level",
    include_args_types=True,
)
async def read_error_logs_by_level(
    error_level: str = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_admin: Admin = Depends(check_admin_permissions(["logs:error"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách logs lỗi theo mức độ"""
    logs = get_error_logs_by_level(db, error_level, skip, limit, start_date, end_date)
    return logs.items


@router.get("/authentication/failed", response_model=List[AuthenticationLogRead])
@profile_endpoint(name="admin:logs:failed_authentication")
@log_admin_action(
    action="view",
    resource_type="authentication_log",
    description="Admin viewed failed authentication attempts",
)
@cached(
    ttl=300,
    namespace="admin:logs:authentication",
    key_prefix="failed_auth_attempts",
    include_args_types=True,
)
async def read_failed_authentication_attempts(
    user_id: Optional[int] = None,
    admin_id: Optional[int] = None,
    window_minutes: int = Query(30, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_admin: Admin = Depends(check_admin_permissions(["logs:auth"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách các lần xác thực thất bại gần đây"""
    return get_failed_authentication_attempts(
        db, user_id, admin_id, window_minutes, limit
    )


@router.get("/api-requests/by-endpoint", response_model=List[ApiRequestLogRead])
@profile_endpoint(name="admin:logs:api_requests_by_endpoint")
@log_admin_action(action="view", resource_type="api_request_log")
@cached(
    ttl=300,
    namespace="admin:logs:api_requests",
    key_prefix="api_requests_by_endpoint",
    include_args_types=True,
)
async def read_api_requests_by_endpoint(
    endpoint: str = Query(..., min_length=1),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_admin: Admin = Depends(check_admin_permissions(["logs:api"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách logs API request theo endpoint"""
    logs = get_requests_by_endpoint(db, endpoint, start_date, end_date, skip, limit)
    return logs.items


@router.get("/api-requests/endpoint-stats")
@profile_endpoint(name="admin:logs:endpoint_stats")
@log_admin_action(
    action="view",
    resource_type="api_stats",
    description="Admin viewed API endpoint statistics",
)
@cached(
    ttl=1800,
    namespace="admin:logs:api_stats",
    key_prefix="endpoint_stats",
    include_args_types=True,
)
async def read_api_endpoint_stats(
    days: int = Query(7, ge=1),
    current_admin: Admin = Depends(check_admin_permissions(["logs:api"])),
    db: Session = Depends(get_db),
):
    """Lấy thống kê về các endpoint API"""
    return get_endpoint_stats(db, days)


@router.get("/performance", response_model=List[PerformanceLogRead])
@profile_endpoint(name="admin:logs:performance")
@log_admin_action(
    action="view",
    resource_type="performance_log",
    description="Admin viewed performance logs",
)
@cached(
    ttl=300,
    namespace="admin:logs:performance",
    key_prefix="performance_logs",
    include_args_types=True,
)
async def read_performance_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    endpoint: Optional[str] = None,
    component: Optional[str] = None,
    operation: Optional[str] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    current_admin: Admin = Depends(check_admin_permissions(["logs:perf"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách logs hiệu suất"""
    logs = get_performance_logs(
        db,
        skip,
        limit,
        endpoint,
        component,
        operation,
        min_duration,
        max_duration,
        start_date,
        end_date,
        sort_by,
        sort_desc,
    )
    return logs.items


@router.get("/performance/slow-operations", response_model=List[PerformanceLogRead])
@profile_endpoint(name="admin:logs:slow_operations")
@log_admin_action(
    action="view",
    resource_type="performance_log",
    description="Admin viewed slow operations",
)
@cached(
    ttl=1800,
    namespace="admin:logs:performance",
    key_prefix="slow_operations",
    include_args_types=True,
)
async def read_slow_operations(
    min_duration_ms: float = Query(1000.0, ge=0),
    days: int = Query(7, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_admin: Admin = Depends(check_admin_permissions(["logs:perf"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách các thao tác chậm"""
    return get_slow_operations(db, min_duration_ms, days, limit)


@router.get("/performance/slow-endpoints")
@profile_endpoint(name="admin:logs:slow_endpoints")
@log_admin_action(
    action="view",
    resource_type="performance_log",
    description="Admin viewed slow endpoints",
)
@cached(
    ttl=1800,
    namespace="admin:logs:performance",
    key_prefix="slow_endpoints",
    include_args_types=True,
)
async def read_slow_endpoints(
    days: int = Query(7, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_admin: Admin = Depends(check_admin_permissions(["logs:perf"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách các endpoint chậm"""
    return get_slow_endpoints(db, days, limit)


@router.get("/search/popular-terms")
@profile_endpoint(name="admin:logs:popular_search_terms")
@log_admin_action(
    action="view",
    resource_type="search_log",
    description="Admin viewed popular search terms",
)
@cached(
    ttl=1800,
    namespace="admin:logs:search",
    key_prefix="popular_search_terms",
    include_args_types=True,
)
async def read_popular_search_terms(
    days: int = Query(7, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_admin: Admin = Depends(check_admin_permissions(["logs:read"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách các từ khóa tìm kiếm phổ biến"""
    return get_popular_search_terms(db, days, limit)


@router.get("/search/zero-results")
@profile_endpoint(name="admin:logs:zero_results_searches")
@log_admin_action(
    action="view",
    resource_type="search_log",
    description="Admin viewed zero results searches",
)
@cached(
    ttl=1800,
    namespace="admin:logs:search",
    key_prefix="zero_results_searches",
    include_args_types=True,
)
async def read_zero_results_searches(
    days: int = Query(7, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_admin: Admin = Depends(check_admin_permissions(["logs:read"])),
    db: Session = Depends(get_db),
):
    """Lấy danh sách các tìm kiếm không có kết quả"""
    return get_zero_results_searches(db, days, limit)


@router.get("/analytics/errors")
@profile_endpoint(name="admin:logs:error_trends")
@log_admin_action(
    action="view",
    resource_type="error_analytics",
    description="Admin viewed error trends",
)
@cached(
    ttl=1800,
    namespace="admin:logs:analytics",
    key_prefix="error_trends",
    include_args_types=True,
)
async def read_error_trends(
    days: int = Query(30, ge=1),
    error_level: Optional[str] = None,
    error_code: Optional[str] = None,
    current_admin: Admin = Depends(check_admin_permissions(["logs:analytics"])),
    db: Session = Depends(get_db),
):
    """Lấy xu hướng lỗi"""
    return get_error_trends(db, days, error_level, error_code)


@router.get("/analytics/user-activity")
@profile_endpoint(name="admin:logs:user_activity_trends")
@log_admin_action(
    action="view",
    resource_type="user_activity_analytics",
    description="Admin viewed user activity trends",
)
@cached(
    ttl=1800,
    namespace="admin:logs:analytics",
    key_prefix="user_activity_trends",
    include_args_types=True,
)
async def read_user_activity_trends(
    days: int = Query(30, ge=1),
    current_admin: Admin = Depends(check_admin_permissions(["logs:analytics"])),
    db: Session = Depends(get_db),
):
    """Lấy xu hướng hoạt động của người dùng"""
    return get_user_activity_trends(db, days)


@router.get("/analytics/admin-activity")
@profile_endpoint(name="admin:logs:admin_activity_trends")
@log_admin_action(
    action="view",
    resource_type="admin_activity_analytics",
    description="Admin viewed admin activity trends",
)
@cached(
    ttl=1800,
    namespace="admin:logs:analytics",
    key_prefix="admin_activity_trends",
    include_args_types=True,
)
async def read_admin_activity_trends(
    days: int = Query(30, ge=1),
    current_admin: Admin = Depends(check_admin_permissions(["logs:analytics"])),
    db: Session = Depends(get_db),
):
    """Lấy xu hướng hoạt động của admin"""
    return get_admin_activity_trends(db, days)


@router.get("/analytics/api-usage")
@profile_endpoint(name="admin:logs:api_usage_trends")
@log_admin_action(
    action="view",
    resource_type="api_analytics",
    description="Admin viewed API usage trends",
)
@cached(
    ttl=1800,
    namespace="admin:logs:analytics",
    key_prefix="api_usage_trends",
    include_args_types=True,
)
async def read_api_usage_trends(
    days: int = Query(30, ge=1),
    current_admin: Admin = Depends(check_admin_permissions(["logs:analytics"])),
    db: Session = Depends(get_db),
):
    """Lấy xu hướng sử dụng API"""
    return get_api_usage_trends(db, days)


@router.get("/analytics/performance")
@profile_endpoint(name="admin:logs:performance_trends")
@log_admin_action(
    action="view",
    resource_type="performance_analytics",
    description="Admin viewed performance trends",
)
@cached(
    ttl=1800,
    namespace="admin:logs:analytics",
    key_prefix="performance_trends",
    include_args_types=True,
)
async def read_performance_trends(
    days: int = Query(30, ge=1),
    current_admin: Admin = Depends(check_admin_permissions(["logs:analytics"])),
    db: Session = Depends(get_db),
):
    """Lấy xu hướng hiệu suất"""
    return get_performance_trends(db, days)


@router.get("/analytics/authentication")
@profile_endpoint(name="admin:logs:authentication_trends")
@log_admin_action(
    action="view",
    resource_type="authentication_analytics",
    description="Admin viewed authentication trends",
)
@cached(
    ttl=1800,
    namespace="admin:logs:analytics",
    key_prefix="authentication_trends",
    include_args_types=True,
)
async def read_authentication_trends(
    days: int = Query(30, ge=1),
    current_admin: Admin = Depends(check_admin_permissions(["logs:analytics"])),
    db: Session = Depends(get_db),
):
    """Lấy xu hướng xác thực"""
    return get_authentication_trends(db, days)


@router.get("/analytics/search")
@profile_endpoint(name="admin:logs:search_trends")
@log_admin_action(
    action="view",
    resource_type="search_analytics",
    description="Admin viewed search trends",
)
@cached(
    ttl=1800,
    namespace="admin:logs:analytics",
    key_prefix="search_trends",
    include_args_types=True,
)
async def read_search_trends(
    days: int = Query(30, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_admin: Admin = Depends(check_admin_permissions(["logs:analytics"])),
    db: Session = Depends(get_db),
):
    """Lấy xu hướng tìm kiếm"""
    return get_search_trends(db, days, limit)
