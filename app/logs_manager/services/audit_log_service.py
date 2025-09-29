from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging

from app.logs_manager.repositories.audit_log_repo import AuditLogRepository
from app.logs_manager.schemas.audit_log import (
    AuditLogCreate,
    AuditLog,
    AuditLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


def create_audit_log(db: Session, log_data: AuditLogCreate) -> AuditLog:
    """
    Create a new audit log entry

    Args:
        db: Database session
        log_data: Audit log data

    Returns:
        Created audit log
    """
    try:
        log_dict = log_data.model_dump()
        db_log = AuditLogRepository.create(db, log_dict)
        return AuditLog.model_validate(db_log)
    except Exception as e:
        logger.error(f"Error creating audit log: {str(e)}")
        raise


def get_audit_log(db: Session, log_id: int) -> AuditLog:
    """
    Get audit log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        Audit log

    Raises:
        NotFoundException: If log not found
    """
    db_log = AuditLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Audit log with ID {log_id} not found")
    return AuditLog.model_validate(db_log)


def get_audit_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    user_type: Optional[str] = None,
    event_type: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> AuditLogList:
    """
    Get audit logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        user_id: Filter by user ID
        user_type: Filter by user type
        event_type: Filter by event type
        resource_type: Filter by resource type
        resource_id: Filter by resource ID
        action: Filter by action
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of audit logs
    """
    logs = AuditLogRepository.get_all(
        db=db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        user_type=user_type,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total = AuditLogRepository.count(
        db=db,
        user_id=user_id,
        user_type=user_type,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return AuditLogList(
        items=[AuditLog.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


def get_resource_audit_logs(
    db: Session,
    resource_type: str,
    resource_id: str,
    skip: int = 0,
    limit: int = 20,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> AuditLogList:
    """
    Get audit logs for a specific resource

    Args:
        db: Database session
        resource_type: Resource type
        resource_id: Resource ID
        skip: Number of records to skip
        limit: Maximum number of records to return
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of audit logs for the resource
    """
    return get_audit_logs(
        db=db,
        skip=skip,
        limit=limit,
        resource_type=resource_type,
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


def get_user_audit_logs(
    db: Session,
    user_id: int,
    user_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> AuditLogList:
    """
    Get audit logs for a specific user

    Args:
        db: Database session
        user_id: User ID
        user_type: User type
        skip: Number of records to skip
        limit: Maximum number of records to return
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of audit logs for the user
    """
    return get_audit_logs(
        db=db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        user_type=user_type,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


class AuditLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log kiểm toán
    """

    def __init__(self):
        self.repository = AuditLogRepository()

    async def log_activity(
        self,
        db: Session,
        user_id: int,
        user_type: str,
        event_type: str,
        resource_type: str,
        resource_id: str,
        action: str,
        before_value: Optional[Dict[str, Any]] = None,
        after_value: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        """
        Ghi log hoạt động kiểm toán

        Args:
            db: Phiên làm việc với database
            user_id: ID của người dùng
            user_type: Loại người dùng
            event_type: Loại sự kiện
            resource_type: Loại tài nguyên
            resource_id: ID của tài nguyên
            action: Hành động thực hiện
            before_value: Giá trị trước khi thay đổi
            after_value: Giá trị sau khi thay đổi
            metadata: Metadata bổ sung
            ip_address: Địa chỉ IP

        Returns:
            Log kiểm toán đã được tạo
        """
        log_data = AuditLogCreate(
            user_id=user_id,
            user_type=user_type,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            before_value=before_value,
            after_value=after_value,
            metadata=metadata,
            ip_address=ip_address,
        )

        log_dict = log_data.model_dump()
        db_log = self.repository.create(db, log_dict)
        return AuditLog.model_validate(db_log)

    async def get_resource_history(
        self,
        db: Session,
        resource_type: str,
        resource_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AuditLogList:
        """
        Lấy lịch sử thay đổi của một tài nguyên

        Args:
            db: Phiên làm việc với database
            resource_type: Loại tài nguyên
            resource_id: ID của tài nguyên
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách log kiểm toán và thông tin phân trang
        """
        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            resource_type=resource_type,
            resource_id=resource_id,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            resource_type=resource_type,
            resource_id=resource_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return AuditLogList(
            items=[AuditLog.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )

    async def get_user_activities(
        self,
        db: Session,
        user_id: int,
        user_type: Optional[str] = None,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AuditLogList:
        """
        Lấy lịch sử hoạt động của người dùng

        Args:
            db: Phiên làm việc với database
            user_id: ID của người dùng
            user_type: Loại người dùng
            event_type: Loại sự kiện
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách log kiểm toán và thông tin phân trang
        """
        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            user_id=user_id,
            user_type=user_type,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            user_id=user_id,
            user_type=user_type,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return AuditLogList(
            items=[AuditLog.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )
