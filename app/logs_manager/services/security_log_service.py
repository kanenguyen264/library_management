from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.logs_manager.repositories.security_log_repo import SecurityLogRepository
from app.logs_manager.schemas.security_log import (
    SecurityLogCreate,
    SecurityLog,
    SecurityLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


def create_security_log(db: Session, log_data: SecurityLogCreate) -> SecurityLog:
    """
    Create a new security log entry

    Args:
        db: Database session
        log_data: Security log data

    Returns:
        Created security log
    """
    try:
        log_dict = log_data.model_dump()
        db_log = SecurityLogRepository.create(db, log_dict)
        return SecurityLog.model_validate(db_log)
    except Exception as e:
        logger.error(f"Error creating security log: {str(e)}")
        raise


def get_security_log(db: Session, log_id: int) -> SecurityLog:
    """
    Get security log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        Security log

    Raises:
        NotFoundException: If log not found
    """
    db_log = SecurityLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Security log with ID {log_id} not found")
    return SecurityLog.model_validate(db_log)


def get_security_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> SecurityLogList:
    """
    Get security logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        event_type: Filter by event type
        severity: Filter by severity
        user_id: Filter by user ID
        ip_address: Filter by IP address
        is_resolved: Filter by resolution status
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of security logs
    """
    logs = SecurityLogRepository.get_all(
        db=db,
        skip=skip,
        limit=limit,
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        ip_address=ip_address,
        is_resolved=is_resolved,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total = SecurityLogRepository.count(
        db=db,
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        ip_address=ip_address,
        is_resolved=is_resolved,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return SecurityLogList(
        items=[SecurityLog.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


def get_high_severity_logs(
    db: Session, days: int = 7, skip: int = 0, limit: int = 20
) -> SecurityLogList:
    """
    Get high severity security logs

    Args:
        db: Database session
        days: Number of days to look back
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of high severity security logs
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    return get_security_logs(
        db=db,
        skip=skip,
        limit=limit,
        severity="high",
        start_date=start_date,
        sort_by="timestamp",
        sort_desc=True,
    )


def update_security_log_resolution(
    db: Session, log_id: int, is_resolved: bool, resolution_notes: Optional[str] = None
) -> SecurityLog:
    """
    Update resolution status of a security log

    Args:
        db: Database session
        log_id: ID of the log entry
        is_resolved: Resolution status
        resolution_notes: Notes about the resolution

    Returns:
        Updated security log

    Raises:
        NotFoundException: If log not found
    """
    db_log = SecurityLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Security log with ID {log_id} not found")

    update_data = {
        "is_resolved": is_resolved,
        "resolution_notes": resolution_notes,
    }
    updated_log = SecurityLogRepository.update(db, log_id, update_data)

    return SecurityLog.model_validate(updated_log)


class SecurityLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log bảo mật
    """

    def __init__(self):
        self.repository = SecurityLogRepository()

    async def log_security_event(
        self,
        db: Session,
        event_type: str,
        severity: str,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        action_taken: Optional[str] = None,
    ) -> SecurityLog:
        """
        Ghi log sự kiện bảo mật

        Args:
            db: Phiên làm việc với database
            event_type: Loại sự kiện
            severity: Mức độ nghiêm trọng
            user_id: ID của người dùng
            ip_address: Địa chỉ IP
            user_agent: User agent của người dùng
            request_path: Đường dẫn request
            details: Chi tiết sự kiện
            action_taken: Hành động đã thực hiện

        Returns:
            Log bảo mật đã được tạo
        """
        log_data = SecurityLogCreate(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            details=details,
            action_taken=action_taken,
            is_resolved=False,
        )

        log_dict = log_data.model_dump()
        db_log = self.repository.create(db, log_dict)
        return SecurityLog.model_validate(db_log)

    async def get_security_incidents(
        self,
        db: Session,
        severity: Optional[str] = None,
        is_resolved: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SecurityLogList:
        """
        Lấy danh sách các sự cố bảo mật

        Args:
            db: Phiên làm việc với database
            severity: Mức độ nghiêm trọng
            is_resolved: Đã được giải quyết chưa
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách sự cố bảo mật và thông tin phân trang
        """
        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            severity=severity,
            is_resolved=is_resolved,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            severity=severity,
            is_resolved=is_resolved,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return SecurityLogList(
            items=[SecurityLog.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )

    async def resolve_security_incident(
        self, db: Session, log_id: int, resolution_notes: str
    ) -> SecurityLog:
        """
        Đánh dấu sự cố bảo mật đã được giải quyết

        Args:
            db: Phiên làm việc với database
            log_id: ID của log bảo mật
            resolution_notes: Ghi chú về cách giải quyết

        Returns:
            Log bảo mật đã được cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy log bảo mật
        """
        db_log = self.repository.get_by_id(db, log_id)
        if not db_log:
            raise NotFoundException(detail=f"Security log with ID {log_id} not found")

        update_data = {
            "is_resolved": True,
            "resolution_notes": resolution_notes,
        }

        updated_log = self.repository.update(db, log_id, update_data)
        return SecurityLog.model_validate(updated_log)
