from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date, timedelta
import json

from app.admin_site.models import SystemMetric
from app.admin_site.schemas.system_metric import SystemMetricCreate, SystemMetricUpdate
from app.admin_site.repositories.system_metric_repo import SystemMetricRepository
from app.cache.decorators import cached, invalidate_cache
from app.core.exceptions import NotFoundException, ServerException, BadRequestException
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


@cached(ttl=300, namespace="admin:system_metrics", tags=["system_metrics"])
def get_all_system_metrics(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    metric_type: Optional[str] = None,
    metric_name: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    order_by: str = "recorded_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[SystemMetric]:
    """
    Lấy danh sách chỉ số hệ thống.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        metric_type: Lọc theo loại metric
        metric_name: Lọc theo tên metric
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        order_by: Sắp xếp theo trường
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách chỉ số hệ thống
    """
    try:
        # Chuyển đổi date thành datetime
        start_datetime = None
        end_datetime = None

        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())

        # Sử dụng repository để lấy dữ liệu
        # Chú ý: Repository hiện không có tham số metric_name, cần bổ sung
        results = SystemMetricRepository.get_all(
            db,
            skip,
            limit,
            metric_name,
            start_datetime,
            end_datetime,
            order_by,
            order_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SYSTEM_METRICS_LIST",
                        entity_id=0,
                        description="Viewed system metrics list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "metric_type": metric_type,
                            "metric_name": metric_name,
                            "start_date": (
                                start_date.isoformat() if start_date else None
                            ),
                            "end_date": end_date.isoformat() if end_date else None,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(results),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return results
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách chỉ số hệ thống: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách chỉ số hệ thống: {str(e)}")


def count_system_metrics(
    db: Session,
    metric_type: Optional[str] = None,
    metric_name: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> int:
    """
    Đếm số lượng chỉ số hệ thống.

    Args:
        db: Database session
        metric_type: Lọc theo loại metric
        metric_name: Lọc theo tên metric
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc

    Returns:
        Tổng số chỉ số hệ thống
    """
    try:
        # Chuyển đổi date thành datetime
        start_datetime = None
        end_datetime = None

        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())

        return SystemMetricRepository.count(
            db, metric_name, start_datetime, end_datetime
        )
    except Exception as e:
        logger.error(f"Lỗi khi đếm chỉ số hệ thống: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm chỉ số hệ thống: {str(e)}")


@cached(ttl=300, namespace="admin:system_metrics", tags=["system_metrics"])
def get_system_metric_by_id(
    db: Session, metric_id: int, admin_id: Optional[int] = None
) -> SystemMetric:
    """
    Lấy thông tin chỉ số hệ thống theo ID.

    Args:
        db: Database session
        metric_id: ID chỉ số
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemMetric object

    Raises:
        NotFoundException: Nếu không tìm thấy chỉ số
    """
    metric = SystemMetricRepository.get_by_id(db, metric_id)
    if not metric:
        logger.warning(f"Không tìm thấy chỉ số hệ thống với ID={metric_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy chỉ số hệ thống với ID={metric_id}"
        )

    # Log admin activity
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="SYSTEM_METRIC",
                    entity_id=metric_id,
                    description=f"Viewed system metric details for {metric.metric_name}",
                    metadata={
                        "metric_name": metric.metric_name,
                        "value": metric.value,
                        "recorded_at": (
                            metric.recorded_at.isoformat()
                            if hasattr(metric, "recorded_at") and metric.recorded_at
                            else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return metric


@cached(ttl=1800, namespace="admin:system_metrics:aggregation", tags=["system_metrics"])
def get_metric_aggregation(
    db: Session,
    metric_name: str,
    interval: str,  # 'hour', 'day', 'week', 'month'
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    admin_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Lấy dữ liệu tổng hợp của chỉ số theo thời gian.

    Args:
        db: Database session
        metric_name: Tên chỉ số
        interval: Khoảng thời gian ('hour', 'day', 'week', 'month')
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách dữ liệu tổng hợp

    Raises:
        BadRequestException: Nếu tham số không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra interval hợp lệ
    valid_intervals = ["hour", "day", "week", "month"]
    if interval not in valid_intervals:
        raise BadRequestException(
            detail=f"Interval không hợp lệ. Chọn một trong: {', '.join(valid_intervals)}"
        )

    try:
        # Chuyển đổi date thành datetime
        start_datetime = None
        end_datetime = None

        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())

        # Lấy dữ liệu tổng hợp
        result = SystemMetricRepository.get_aggregation(
            db, metric_name, interval, start_datetime, end_datetime
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SYSTEM_METRIC_AGGREGATION",
                        entity_id=0,
                        description=f"Viewed aggregated data for metric {metric_name}",
                        metadata={
                            "metric_name": metric_name,
                            "interval": interval,
                            "start_date": (
                                start_date.isoformat() if start_date else None
                            ),
                            "end_date": end_date.isoformat() if end_date else None,
                            "results_count": len(result),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu tổng hợp chỉ số: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy dữ liệu tổng hợp chỉ số: {str(e)}")


def create_system_metric(
    db: Session, metric_data: SystemMetricCreate, admin_id: Optional[int] = None
) -> SystemMetric:
    """
    Tạo chỉ số hệ thống mới.

    Args:
        db: Database session
        metric_data: Thông tin chỉ số mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemMetric object đã tạo

    Raises:
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Chuẩn bị dữ liệu metadata
    metadata_json = None
    if metric_data.metadata:
        try:
            # Kiểm tra nếu là chuỗi JSON
            if isinstance(metric_data.metadata, str):
                json.loads(metric_data.metadata)  # Chỉ để kiểm tra
                metadata_json = metric_data.metadata
            else:
                # Chuyển đổi đối tượng thành chuỗi JSON
                metadata_json = json.dumps(metric_data.metadata)
        except json.JSONDecodeError:
            logger.error(f"Metadata không phải là JSON hợp lệ")
            raise BadRequestException(detail="Metadata không phải là JSON hợp lệ")

    # Chuẩn bị dữ liệu
    metric_dict = metric_data.model_dump()
    metric_dict.update({"metadata": metadata_json, "created_at": datetime.now(timezone.utc)})

    # Đảm bảo recorded_at luôn có giá trị
    if not metric_dict.get("recorded_at"):
        metric_dict["recorded_at"] = datetime.now(timezone.utc)

    # Tạo chỉ số mới
    try:
        created_metric = SystemMetricRepository.create(db, metric_dict)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="SYSTEM_METRIC",
                        entity_id=created_metric.id,
                        description=f"Created new system metric for {created_metric.metric_name}",
                        metadata={
                            "metric_name": created_metric.metric_name,
                            "value": created_metric.value,
                            "recorded_at": (
                                created_metric.recorded_at.isoformat()
                                if hasattr(created_metric, "recorded_at")
                                and created_metric.recorded_at
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return created_metric
    except Exception as e:
        logger.error(f"Lỗi khi tạo chỉ số hệ thống: {str(e)}")
        raise ServerException(detail=f"Không thể tạo chỉ số hệ thống: {str(e)}")


def update_system_metric(
    db: Session,
    metric_id: int,
    metric_data: SystemMetricUpdate,
    admin_id: Optional[int] = None,
) -> SystemMetric:
    """
    Cập nhật thông tin chỉ số hệ thống.

    Args:
        db: Database session
        metric_id: ID chỉ số
        metric_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemMetric object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy chỉ số
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra chỉ số tồn tại
    metric = SystemMetricRepository.get_by_id(db, metric_id)
    if not metric:
        logger.warning(f"Không tìm thấy chỉ số hệ thống với ID={metric_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy chỉ số hệ thống với ID={metric_id}"
        )

    # Xử lý metadata nếu có
    if metric_data.metadata is not None:
        try:
            # Kiểm tra nếu là chuỗi JSON
            if isinstance(metric_data.metadata, str):
                json.loads(metric_data.metadata)  # Chỉ để kiểm tra
            else:
                # Chuyển đổi đối tượng thành chuỗi JSON
                metric_data.metadata = json.dumps(metric_data.metadata)
        except json.JSONDecodeError:
            logger.error(f"Metadata không phải là JSON hợp lệ")
            raise BadRequestException(detail="Metadata không phải là JSON hợp lệ")

    # Chuẩn bị dữ liệu cập nhật
    update_data = metric_data.model_dump(exclude_unset=True)

    # Cập nhật chỉ số
    try:
        updated_metric = SystemMetricRepository.update(db, metric_id, update_data)
        if not updated_metric:
            raise ServerException(
                detail=f"Không thể cập nhật chỉ số hệ thống với ID={metric_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="SYSTEM_METRIC",
                        entity_id=metric_id,
                        description=f"Updated system metric for {updated_metric.metric_name}",
                        metadata={
                            "metric_name": updated_metric.metric_name,
                            "previous_value": (
                                metric.value if hasattr(metric, "value") else None
                            ),
                            "new_value": (
                                updated_metric.value
                                if hasattr(updated_metric, "value")
                                else None
                            ),
                            "recorded_at": (
                                updated_metric.recorded_at.isoformat()
                                if hasattr(updated_metric, "recorded_at")
                                and updated_metric.recorded_at
                                else None
                            ),
                            "updates": {
                                k: v for k, v in update_data.items() if k != "metadata"
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_metric
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi cập nhật chỉ số hệ thống: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật chỉ số hệ thống: {str(e)}")


def delete_system_metric(
    db: Session, metric_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa chỉ số hệ thống.

    Args:
        db: Database session
        metric_id: ID chỉ số
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy chỉ số
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra chỉ số tồn tại
    metric = SystemMetricRepository.get_by_id(db, metric_id)
    if not metric:
        logger.warning(f"Không tìm thấy chỉ số hệ thống với ID={metric_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy chỉ số hệ thống với ID={metric_id}"
        )

    # Log admin activity before deletion
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="DELETE",
                    entity_type="SYSTEM_METRIC",
                    entity_id=metric_id,
                    description=f"Deleted system metric for {metric.metric_name}",
                    metadata={
                        "metric_name": metric.metric_name,
                        "value": metric.value if hasattr(metric, "value") else None,
                        "recorded_at": (
                            metric.recorded_at.isoformat()
                            if hasattr(metric, "recorded_at") and metric.recorded_at
                            else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    # Xóa chỉ số
    try:
        success = SystemMetricRepository.delete(db, metric_id)
        if not success:
            raise ServerException(
                detail=f"Không thể xóa chỉ số hệ thống với ID={metric_id}"
            )

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa chỉ số hệ thống: {str(e)}")
        raise ServerException(detail=f"Không thể xóa chỉ số hệ thống: {str(e)}")


def delete_old_metrics(
    db: Session, days: int = 30, admin_id: Optional[int] = None
) -> int:
    """
    Xóa các chỉ số cũ.

    Args:
        db: Database session
        days: Số ngày giữ lại
        admin_id: ID của admin thực hiện hành động

    Returns:
        Số lượng chỉ số đã xóa

    Raises:
        BadRequestException: Nếu tham số không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    if days <= 0:
        raise BadRequestException(detail="Số ngày phải lớn hơn 0")

    try:
        result = SystemMetricRepository.delete_old_metrics(db, days)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="SYSTEM_METRICS",
                        entity_id=0,
                        description=f"Deleted old system metrics older than {days} days",
                        metadata={"days_retained": days, "deleted_count": result},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi xóa chỉ số cũ: {str(e)}")
        raise ServerException(detail=f"Lỗi khi xóa chỉ số cũ: {str(e)}")
