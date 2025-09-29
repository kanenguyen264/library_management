from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.logs_manager.repositories.performance_log_repo import PerformanceLogRepository
from app.logs_manager.schemas.performance_log import (
    PerformanceLogCreate,
    PerformanceLogUpdate,
    PerformanceLogRead,
    PerformanceLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


def create_performance_log(
    db: Session, log_data: PerformanceLogCreate
) -> PerformanceLogRead:
    """
    Create a new performance log entry

    Args:
        db: Database session
        log_data: Performance log data

    Returns:
        Created performance log
    """
    try:
        log_dict = log_data.model_dump()
        db_log = PerformanceLogRepository.create(db, log_dict)
        return PerformanceLogRead.model_validate(db_log)
    except Exception as e:
        logger.error(f"Error creating performance log: {str(e)}")
        raise


def get_performance_log(db: Session, log_id: int) -> PerformanceLogRead:
    """
    Get performance log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        Performance log

    Raises:
        NotFoundException: If log not found
    """
    db_log = PerformanceLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Performance log with ID {log_id} not found")
    return PerformanceLogRead.model_validate(db_log)


def get_performance_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    endpoint: Optional[str] = None,
    component: Optional[str] = None,
    operation: Optional[str] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> PerformanceLogList:
    """
    Get performance logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        endpoint: Filter by API endpoint
        component: Filter by component
        operation: Filter by operation
        min_duration: Minimum duration in ms
        max_duration: Maximum duration in ms
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of performance logs
    """
    logs = PerformanceLogRepository.get_all(
        db=db,
        skip=skip,
        limit=limit,
        endpoint=endpoint,
        component=component,
        operation=operation,
        min_duration=min_duration,
        max_duration=max_duration,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total = PerformanceLogRepository.count(
        db=db,
        endpoint=endpoint,
        component=component,
        operation=operation,
        min_duration=min_duration,
        max_duration=max_duration,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return PerformanceLogList(
        items=[PerformanceLogRead.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


def get_slow_operations(
    db: Session,
    min_duration_ms: float = 1000.0,  # 1 second
    days: int = 7,
    limit: int = 20,
) -> List[PerformanceLogRead]:
    """
    Get slow operations

    Args:
        db: Database session
        min_duration_ms: Minimum duration in milliseconds to consider as slow
        days: Number of days to look back
        limit: Maximum number of records to return

    Returns:
        List of slow performance logs
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    logs = PerformanceLogRepository.get_all(
        db=db,
        skip=0,
        limit=limit,
        min_duration=min_duration_ms,
        start_date=start_date,
        sort_by="duration_ms",
        sort_desc=True,
    )

    return [PerformanceLogRead.model_validate(log) for log in logs]


def get_slow_endpoints(
    db: Session, days: int = 7, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get endpoints with high average response times

    Args:
        db: Database session
        days: Number of days to look back
        limit: Maximum number of endpoints to return

    Returns:
        List of dictionaries with endpoint statistics
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    return PerformanceLogRepository.get_slow_endpoints(
        db, start_date=start_date, limit=limit
    )


def get_performance_stats(
    db: Session,
    component: Optional[str] = None,
    operation: Optional[str] = None,
    endpoint: Optional[str] = None,
    days: int = 7,
) -> Dict[str, Any]:
    """
    Get performance statistics

    Args:
        db: Database session
        component: Filter by component
        operation: Filter by operation
        endpoint: Filter by endpoint
        days: Number of days to look back

    Returns:
        Dictionary with performance statistics
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    return PerformanceLogRepository.get_performance_stats(
        db,
        start_date=start_date,
        component=component,
        operation=operation,
        endpoint=endpoint,
    )


def delete_performance_log(db: Session, log_id: int) -> bool:
    """
    Delete performance log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        True if log was deleted successfully

    Raises:
        NotFoundException: If log not found
    """
    db_log = PerformanceLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Performance log with ID {log_id} not found")

    return PerformanceLogRepository.delete(db, log_id)


def cleanup_old_logs(db: Session, days: int = 90) -> int:
    """
    Delete performance logs older than the specified number of days

    Args:
        db: Database session
        days: Number of days to keep logs for

    Returns:
        Number of logs deleted
    """
    return PerformanceLogRepository.delete_old_logs(db, days)


class PerformanceLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log hiệu suất
    """

    def __init__(self):
        self.repository = PerformanceLogRepository()

    async def log_performance(
        self,
        db: Session,
        operation_type: str,
        component: str,
        duration_ms: float,
        operation_name: Optional[str] = None,
        resource_usage: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ) -> PerformanceLogRead:
        """
        Ghi log hiệu suất

        Args:
            db: Phiên làm việc với database
            operation_type: Loại hoạt động
            component: Thành phần hệ thống
            duration_ms: Thời gian thực hiện (ms)
            operation_name: Tên hoạt động
            resource_usage: Thông tin tài nguyên sử dụng
            context: Context khi thực hiện
            metadata: Metadata bổ sung
            success: Hoạt động thành công hay không

        Returns:
            Log hiệu suất đã được tạo
        """
        log_data = PerformanceLogCreate(
            operation_type=operation_type,
            component=component,
            operation_name=operation_name,
            duration_ms=duration_ms,
            resource_usage=resource_usage or {},
            context=context or {},
            metadata=metadata or {},
            success=success,
        )

        log_dict = log_data.model_dump()
        db_log = self.repository.create(db, log_dict)
        return PerformanceLogRead.model_validate(db_log)

    async def get_performance_metrics(
        self,
        db: Session,
        component: Optional[str] = None,
        operation_type: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        max_duration_ms: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PerformanceLogList:
        """
        Lấy danh sách log hiệu suất theo các điều kiện

        Args:
            db: Phiên làm việc với database
            component: Lọc theo thành phần hệ thống
            operation_type: Lọc theo loại hoạt động
            min_duration_ms: Thời gian thực hiện tối thiểu
            max_duration_ms: Thời gian thực hiện tối đa
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách log hiệu suất và thông tin phân trang
        """
        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            component=component,
            operation=operation_type,
            min_duration=min_duration_ms,
            max_duration=max_duration_ms,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            component=component,
            operation=operation_type,
            min_duration=min_duration_ms,
            max_duration=max_duration_ms,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return PerformanceLogList(
            items=[PerformanceLogRead.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )

    async def get_slow_operations_analysis(
        self,
        db: Session,
        days: int = 7,
        min_duration_ms: float = 1000.0,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Phân tích các hoạt động chậm trong hệ thống

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích
            min_duration_ms: Thời gian tối thiểu để coi là chậm (ms)
            limit: Số lượng kết quả tối đa

        Returns:
            Danh sách phân tích các hoạt động chậm
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        return self.repository.get_slow_endpoints(
            db, start_date=start_date, min_duration=min_duration_ms, limit=limit
        )
