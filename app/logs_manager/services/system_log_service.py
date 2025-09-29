from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.logs_manager.repositories.system_log_repo import SystemLogRepository
from app.logs_manager.schemas.system_log import (
    SystemLogCreate,
    SystemLog,
    SystemLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


def create_system_log(db: Session, log_data: SystemLogCreate) -> SystemLog:
    """
    Create a new system log entry

    Args:
        db: Database session
        log_data: System log data

    Returns:
        Created system log
    """
    try:
        log_dict = log_data.model_dump()
        db_log = SystemLogRepository.create(db, log_dict)
        return SystemLog.model_validate(db_log)
    except Exception as e:
        logger.error(f"Error creating system log: {str(e)}")
        raise


def get_system_log(db: Session, log_id: int) -> SystemLog:
    """
    Get system log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        System log

    Raises:
        NotFoundException: If log not found
    """
    db_log = SystemLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"System log with ID {log_id} not found")
    return SystemLog.model_validate(db_log)


def get_system_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    event_type: Optional[str] = None,
    component: Optional[str] = None,
    environment: Optional[str] = None,
    success: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> SystemLogList:
    """
    Get system logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        event_type: Filter by event type
        component: Filter by component
        environment: Filter by environment
        success: Filter by success status
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of system logs
    """
    logs = SystemLogRepository.get_all(
        db=db,
        skip=skip,
        limit=limit,
        event_type=event_type,
        component=component,
        environment=environment,
        success=success,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total = SystemLogRepository.count(
        db=db,
        event_type=event_type,
        component=component,
        environment=environment,
        success=success,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return SystemLogList(
        items=[SystemLog.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


def get_component_logs(
    db: Session,
    component: str,
    skip: int = 0,
    limit: int = 20,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> SystemLogList:
    """
    Get system logs for a specific component

    Args:
        db: Database session
        component: Component name
        skip: Number of records to skip
        limit: Maximum number of records to return
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of system logs for the component
    """
    return get_system_logs(
        db=db,
        skip=skip,
        limit=limit,
        component=component,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


def get_failed_operations(
    db: Session, days: int = 7, skip: int = 0, limit: int = 20
) -> SystemLogList:
    """
    Get system logs for failed operations

    Args:
        db: Database session
        days: Number of days to look back
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of system logs for failed operations
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    return get_system_logs(
        db=db,
        skip=skip,
        limit=limit,
        success=False,
        start_date=start_date,
        sort_by="timestamp",
        sort_desc=True,
    )


class SystemLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log hệ thống
    """

    def __init__(self):
        self.repository = SystemLogRepository()

    async def log_system_event(
        self,
        db: Session,
        event_type: str,
        component: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        environment: Optional[str] = None,
        server_name: Optional[str] = None,
        success: bool = True,
    ) -> SystemLog:
        """
        Ghi log sự kiện hệ thống

        Args:
            db: Phiên làm việc với database
            event_type: Loại sự kiện
            component: Thành phần hệ thống
            message: Thông báo
            details: Chi tiết sự kiện
            environment: Môi trường
            server_name: Tên máy chủ
            success: Sự kiện thành công hay không

        Returns:
            Log hệ thống đã được tạo
        """
        log_data = SystemLogCreate(
            event_type=event_type,
            component=component,
            message=message,
            details=details,
            environment=environment,
            server_name=server_name,
            success=success,
        )

        log_dict = log_data.model_dump()
        db_log = self.repository.create(db, log_dict)
        return SystemLog.model_validate(db_log)

    async def get_component_events(
        self,
        db: Session,
        component: str,
        event_type: Optional[str] = None,
        success: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SystemLogList:
        """
        Lấy danh sách sự kiện của một thành phần hệ thống

        Args:
            db: Phiên làm việc với database
            component: Thành phần hệ thống
            event_type: Loại sự kiện
            success: Lọc theo trạng thái thành công
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách sự kiện hệ thống và thông tin phân trang
        """
        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            component=component,
            event_type=event_type,
            success=success,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            component=component,
            event_type=event_type,
            success=success,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return SystemLogList(
            items=[SystemLog.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )

    async def get_system_health(
        self, db: Session, days: int = 1, components: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin sức khỏe hệ thống dựa trên log

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích
            components: Danh sách các thành phần cần phân tích

        Returns:
            Dict với thông tin sức khỏe hệ thống
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Get component statistics
        component_stats = self.repository.get_component_stats(
            db, start_date=start_date, components=components
        )

        # Get failure statistics
        failure_stats = self.repository.get_failure_stats(
            db, start_date=start_date, components=components
        )

        # Calculate overall health
        total_events = sum(stat["total"] for stat in component_stats)
        total_failures = sum(stat["failures"] for stat in failure_stats)
        health_percentage = 100.0
        if total_events > 0:
            health_percentage = 100.0 - (total_failures / total_events * 100.0)

        return {
            "period_days": days,
            "start_date": start_date,
            "end_date": datetime.now(timezone.utc),
            "total_events": total_events,
            "total_failures": total_failures,
            "health_percentage": round(health_percentage, 2),
            "component_stats": component_stats,
            "failure_stats": failure_stats,
        }
