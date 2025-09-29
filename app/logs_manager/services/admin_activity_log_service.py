from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.logs_manager.repositories.admin_activity_log_repo import (
    AdminActivityLogRepository,
)
from app.logs_manager.schemas.admin_activity_log import (
    AdminActivityLogCreate,
    AdminActivityLog,
    AdminActivityLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


def create_admin_activity_log(
    db: Session, log_data: AdminActivityLogCreate
) -> AdminActivityLog:
    """
    Create a new admin activity log entry

    Args:
        db: Database session
        log_data: Admin activity log data

    Returns:
        Created admin activity log
    """
    try:
        log_dict = log_data.model_dump()
        db_log = AdminActivityLogRepository.create(db, log_dict)
        return AdminActivityLog.model_validate(db_log)
    except Exception as e:
        logger.error(f"Error creating admin activity log: {str(e)}")
        raise


def get_admin_activity_log(db: Session, log_id: int) -> AdminActivityLog:
    """
    Get admin activity log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        Admin activity log

    Raises:
        NotFoundException: If log not found
    """
    db_log = AdminActivityLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Admin activity log with ID {log_id} not found")
    return AdminActivityLog.model_validate(db_log)


def get_admin_activity_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    admin_id: Optional[int] = None,
    activity_type: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> AdminActivityLogList:
    """
    Get admin activity logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        admin_id: Filter by admin ID
        activity_type: Filter by activity type
        resource_type: Filter by resource type
        resource_id: Filter by resource ID
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of admin activity logs
    """
    logs = AdminActivityLogRepository.get_all(
        db=db,
        skip=skip,
        limit=limit,
        admin_id=admin_id,
        activity_type=activity_type,
        resource_type=resource_type,
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total = AdminActivityLogRepository.count(
        db=db,
        admin_id=admin_id,
        activity_type=activity_type,
        resource_type=resource_type,
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return AdminActivityLogList(
        items=[AdminActivityLog.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


def get_admin_activities_by_admin(
    db: Session,
    admin_id: int,
    skip: int = 0,
    limit: int = 20,
    activity_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> AdminActivityLogList:
    """
    Get activity logs for a specific admin

    Args:
        db: Database session
        admin_id: Admin ID
        skip: Number of records to skip
        limit: Maximum number of records to return
        activity_type: Filter by activity type
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of admin activity logs
    """
    return get_admin_activity_logs(
        db=db,
        skip=skip,
        limit=limit,
        admin_id=admin_id,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


def update_admin_activity_log(
    db: Session, log_id: int, update_data: Dict[str, Any]
) -> AdminActivityLog:
    """
    Update an admin activity log

    Args:
        db: Database session
        log_id: ID of the log entry
        update_data: Updated log data

    Returns:
        Updated admin activity log

    Raises:
        NotFoundException: If log not found
    """
    db_log = AdminActivityLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Admin activity log with ID {log_id} not found")

    updated_log = AdminActivityLogRepository.update(db, log_id, update_data)
    return AdminActivityLog.model_validate(updated_log)


def delete_admin_activity_log(db: Session, log_id: int) -> bool:
    """
    Delete an admin activity log

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        True if deleted successfully

    Raises:
        NotFoundException: If log not found
    """
    db_log = AdminActivityLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Admin activity log with ID {log_id} not found")

    return AdminActivityLogRepository.delete(db, log_id)


class AdminActivityLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log hoạt động của admin
    """

    def __init__(self):
        self.repository = AdminActivityLogRepository()

    async def log_activity(
        self,
        db: Session,
        admin_id: int,
        activity_type: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
    ) -> AdminActivityLog:
        """
        Ghi log hoạt động của admin

        Args:
            db: Phiên làm việc với database
            admin_id: ID của admin
            activity_type: Loại hoạt động
            action: Hành động
            resource_type: Loại tài nguyên
            resource_id: ID của tài nguyên
            before_state: Trạng thái trước khi thay đổi
            after_state: Trạng thái sau khi thay đổi
            details: Chi tiết về hoạt động
            ip_address: Địa chỉ IP
            user_agent: User agent
            success: Hoạt động thành công hay không

        Returns:
            Log hoạt động đã được tạo
        """
        log_data = AdminActivityLogCreate(
            admin_id=admin_id,
            activity_type=activity_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=before_state,
            after_state=after_state,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
        )

        log_dict = log_data.model_dump()
        db_log = self.repository.create(db, log_dict)
        return AdminActivityLog.model_validate(db_log)

    async def get_admin_activities(
        self,
        db: Session,
        admin_id: Optional[int] = None,
        activity_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AdminActivityLogList:
        """
        Lấy danh sách log hoạt động của admin theo các điều kiện

        Args:
            db: Phiên làm việc với database
            admin_id: ID của admin
            activity_type: Loại hoạt động
            resource_type: Loại tài nguyên
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách log hoạt động và thông tin phân trang
        """
        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            admin_id=admin_id,
            activity_type=activity_type,
            resource_type=resource_type,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            admin_id=admin_id,
            activity_type=activity_type,
            resource_type=resource_type,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return AdminActivityLogList(
            items=[AdminActivityLog.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )
