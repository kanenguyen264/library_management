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
from datetime import date

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    secure_admin_access,
)
from app.admin_site.models import Admin
from app.admin_site.schemas.system_metric import (
    SystemMetricCreate,
    SystemMetricUpdate,
    SystemMetricInfo,
)
from app.admin_site.services.system_metric_service import (
    get_all_system_metrics,
    count_system_metrics,
    get_system_metric_by_id,
    create_system_metric,
    update_system_metric,
    delete_system_metric,
    get_metric_aggregation,
    delete_old_metrics,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/system-metrics - Lấy danh sách metric
# GET /api/v1/admin/system-metrics/{id} - Lấy thông tin chi tiết metric
# POST /api/v1/admin/system-metrics - Tạo metric mới
# PUT /api/v1/admin/system-metrics/{id} - Cập nhật thông tin metric
# DELETE /api/v1/admin/system-metrics/{id} - Xóa metric


@router.get("", response_model=List[SystemMetricInfo])
@profile_endpoint(name="admin:system_metrics:list")
@cached(ttl=300, namespace="admin:system_metrics", key_prefix="metrics_list")
@log_admin_action(
    action="view",
    resource_type="system_metric",
    description="Xem danh sách chỉ số hệ thống",
)
async def read_system_metrics(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(100, ge=1, le=100, description="Số bản ghi lấy"),
    metric_type: Optional[str] = Query(None, description="Lọc theo loại metric"),
    start_date: Optional[date] = Query(None, description="Ngày bắt đầu"),
    end_date: Optional[date] = Query(None, description="Ngày kết thúc"),
    current_admin: Admin = Depends(secure_admin_access(["system_metric:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[SystemMetricInfo]:
    """
    Lấy danh sách chỉ số hệ thống.

    **Quyền yêu cầu**: `system_metric:read`

    **Cách sử dụng**:
    - Dùng phân trang với skip và limit
    - Lọc theo loại chỉ số với tham số metric_type
    - Lọc theo khoảng thời gian với start_date và end_date

    **Kết quả**:
    - Danh sách chỉ số hệ thống
    """
    if start_date and end_date and start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng truy vấn với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    metrics = get_all_system_metrics(db, skip, limit, metric_type, start_date, end_date)

    logger.info(
        f"Admin {current_admin.username} đã lấy danh sách {len(metrics)} chỉ số hệ thống"
    )

    return metrics


@router.get("/aggregation", response_model=List[Dict[str, Any]])
@profile_endpoint(name="admin:system_metrics:aggregation")
@cached(ttl=300, namespace="admin:system_metrics", key_prefix="metrics_aggregation")
@log_admin_action(
    action="view",
    resource_type="system_metric_aggregation",
    description="Xem dữ liệu tổng hợp chỉ số",
)
async def get_metrics_aggregation(
    metric_name: str = Query(..., description="Tên chỉ số"),
    interval: str = Query(
        "day", description="Khoảng thời gian (hour, day, week, month)"
    ),
    start_date: Optional[date] = Query(None, description="Ngày bắt đầu"),
    end_date: Optional[date] = Query(None, description="Ngày kết thúc"),
    current_admin: Admin = Depends(secure_admin_access(["system_metric:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> List[Dict[str, Any]]:
    """
    Lấy dữ liệu tổng hợp của chỉ số theo thời gian.

    **Quyền yêu cầu**: `system_metric:read`

    **Cách sử dụng**:
    - Chỉ định tên chỉ số với tham số metric_name
    - Chỉ định khoảng thời gian (hour, day, week, month) với tham số interval
    - Chỉ định khoảng thời gian với start_date và end_date

    **Kết quả**:
    - Danh sách dữ liệu tổng hợp
    """
    if start_date and end_date and start_date > end_date:
        logger.warning(
            f"Admin {current_admin.username} đã cố gắng truy vấn dữ liệu tổng hợp với start_date > end_date"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ngày bắt đầu phải trước ngày kết thúc",
        )

    aggregation = get_metric_aggregation(
        db, metric_name, interval, start_date, end_date
    )

    logger.info(
        f"Admin {current_admin.username} đã lấy dữ liệu tổng hợp cho chỉ số {metric_name}"
    )

    return aggregation


@router.get("/{id}", response_model=SystemMetricInfo)
@profile_endpoint(name="admin:system_metrics:detail")
@cached(ttl=300, namespace="admin:system_metrics", key_prefix="metrics_detail")
@log_admin_action(action="view", resource_type="system_metric", resource_id="{id}")
async def read_system_metric(
    id: int = Path(..., ge=1, description="ID chỉ số"),
    current_admin: Admin = Depends(secure_admin_access(["system_metric:read"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemMetricInfo:
    """
    Lấy thông tin chi tiết chỉ số hệ thống.

    **Quyền yêu cầu**: `system_metric:read`

    **Cách sử dụng**:
    - Cung cấp ID chỉ số cần xem

    **Kết quả**:
    - Thông tin chi tiết chỉ số hệ thống
    """
    metric = get_system_metric_by_id(db, id)

    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chỉ số hệ thống không tồn tại",
        )

    logger.info(
        f"Admin {current_admin.username} đã xem thông tin chỉ số hệ thống ID={id}"
    )

    return metric


@router.post("", response_model=SystemMetricInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:system_metrics:create")
@invalidate_cache(namespace="admin:system_metrics")
@log_admin_action(
    action="create",
    resource_type="system_metric",
    description="Tạo chỉ số hệ thống mới",
)
async def create_new_system_metric(
    metric_data: SystemMetricCreate,
    current_admin: Admin = Depends(secure_admin_access(["system_metric:create"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemMetricInfo:
    """
    Tạo chỉ số hệ thống mới.

    **Quyền yêu cầu**: `system_metric:create`

    **Cách sử dụng**:
    - Cung cấp thông tin chỉ số hệ thống trong body

    **Kết quả**:
    - Thông tin chỉ số hệ thống đã tạo
    """
    # Tạo chỉ số hệ thống mới
    try:
        new_metric = create_system_metric(db, metric_data)
        logger.info(
            f"Admin {current_admin.username} đã tạo chỉ số hệ thống mới: {new_metric.name}"
        )
        return new_metric
    except ValueError as e:
        logger.error(f"Lỗi khi tạo chỉ số hệ thống mới: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{id}", response_model=SystemMetricInfo)
@profile_endpoint(name="admin:system_metrics:update")
@invalidate_cache(namespace="admin:system_metrics")
@log_admin_action(action="update", resource_type="system_metric", resource_id="{id}")
async def update_system_metric_info(
    id: int = Path(..., ge=1, description="ID chỉ số"),
    metric_data: SystemMetricUpdate = Body(...),
    current_admin: Admin = Depends(secure_admin_access(["system_metric:update"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> SystemMetricInfo:
    """
    Cập nhật thông tin chỉ số hệ thống.

    **Quyền yêu cầu**: `system_metric:update`

    **Cách sử dụng**:
    - Cung cấp ID chỉ số cần cập nhật
    - Cung cấp thông tin cập nhật trong body

    **Kết quả**:
    - Thông tin chỉ số hệ thống đã cập nhật
    """
    # Kiểm tra chỉ số tồn tại
    metric = get_system_metric_by_id(db, id)

    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chỉ số hệ thống không tồn tại",
        )

    # Cập nhật chỉ số
    try:
        updated_metric = update_system_metric(db, id, metric_data)
        logger.info(
            f"Admin {current_admin.username} đã cập nhật chỉ số hệ thống ID={id}, name={updated_metric.name}"
        )
        return updated_metric
    except ValueError as e:
        logger.error(f"Lỗi khi cập nhật chỉ số hệ thống ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:system_metrics:delete")
@invalidate_cache(namespace="admin:system_metrics")
@log_admin_action(action="delete", resource_type="system_metric", resource_id="{id}")
async def delete_system_metric_item(
    id: int = Path(..., ge=1, description="ID chỉ số"),
    current_admin: Admin = Depends(secure_admin_access(["system_metric:delete"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> None:
    """
    Xóa chỉ số hệ thống.

    **Quyền yêu cầu**: `system_metric:delete`

    **Cách sử dụng**:
    - Cung cấp ID chỉ số cần xóa

    **Kết quả**:
    - Không có nội dung trả về
    """
    # Kiểm tra chỉ số tồn tại
    metric = get_system_metric_by_id(db, id)

    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chỉ số hệ thống không tồn tại",
        )

    # Xóa chỉ số
    try:
        deleted = delete_system_metric(db, id)

        if not deleted:
            logger.error(f"Không thể xóa chỉ số hệ thống ID={id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể xóa chỉ số hệ thống",
            )

        logger.info(
            f"Admin {current_admin.username} đã xóa chỉ số hệ thống ID={id}, name={metric.name}"
        )
    except ValueError as e:
        logger.error(f"Lỗi khi xóa chỉ số hệ thống ID={id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/cleanup", response_model=Dict[str, Any])
@profile_endpoint(name="admin:system_metrics:cleanup")
@invalidate_cache(namespace="admin:system_metrics")
@log_admin_action(
    action="cleanup", resource_type="system_metric", description="Dọn dẹp chỉ số cũ"
)
async def cleanup_old_metrics(
    days: int = Query(30, ge=1, description="Số ngày giữ lại"),
    current_admin: Admin = Depends(secure_admin_access(["system_metric:delete"])),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Xóa các chỉ số cũ.

    **Quyền yêu cầu**: `system_metric:delete`

    **Cách sử dụng**:
    - Chỉ định số ngày giữ lại với tham số days

    **Kết quả**:
    - Số lượng chỉ số đã xóa
    """
    try:
        deleted_count = delete_old_metrics(db, days)
        logger.info(
            f"Admin {current_admin.username} đã xóa {deleted_count} chỉ số cũ hơn {days} ngày"
        )
        return {"deleted_count": deleted_count}
    except ValueError as e:
        logger.error(f"Lỗi khi dọn dẹp chỉ số cũ: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
