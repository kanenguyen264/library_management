from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging

from app.logs_manager.repositories.error_log_repo import ErrorLogRepository
from app.logs_manager.schemas.error_log import (
    ErrorLogCreate,
    ErrorLogUpdate,
    ErrorLogRead,
    ErrorLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


def create_error_log(db: Session, log_data: ErrorLogCreate) -> ErrorLogRead:
    """
    Create a new error log entry

    Args:
        db: Database session
        log_data: Error log data

    Returns:
        Created error log
    """
    try:
        log_dict = log_data.model_dump()
        db_log = ErrorLogRepository.create(db, log_dict)
        return ErrorLogRead.model_validate(db_log)
    except Exception as e:
        logger.error(f"Error creating error log: {str(e)}")
        raise


def get_error_log(db: Session, log_id: int) -> ErrorLogRead:
    """
    Get error log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        Error log

    Raises:
        NotFoundException: If log not found
    """
    db_log = ErrorLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Error log with ID {log_id} not found")
    return ErrorLogRead.model_validate(db_log)


def get_error_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    error_level: Optional[str] = None,
    error_code: Optional[str] = None,
    source: Optional[str] = None,
    user_id: Optional[int] = None,
    admin_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> ErrorLogList:
    """
    Get error logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        error_level: Filter by error level
        error_code: Filter by error code
        source: Filter by source
        user_id: Filter by user ID
        admin_id: Filter by admin ID
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of error logs
    """
    logs = ErrorLogRepository.get_all(
        db=db,
        skip=skip,
        limit=limit,
        error_level=error_level,
        error_code=error_code,
        source=source,
        user_id=user_id,
        admin_id=admin_id,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total = ErrorLogRepository.count(
        db=db,
        error_level=error_level,
        error_code=error_code,
        source=source,
        user_id=user_id,
        admin_id=admin_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return ErrorLogList(
        items=[ErrorLogRead.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


def get_error_logs_by_level(
    db: Session,
    error_level: str,
    skip: int = 0,
    limit: int = 20,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> ErrorLogList:
    """
    Get error logs for a specific error level

    Args:
        db: Database session
        error_level: Error level
        skip: Number of records to skip
        limit: Maximum number of records to return
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of error logs
    """
    return get_error_logs(
        db=db,
        skip=skip,
        limit=limit,
        error_level=error_level,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


def update_error_log(
    db: Session, log_id: int, log_data: ErrorLogUpdate
) -> ErrorLogRead:
    """
    Update an error log

    Args:
        db: Database session
        log_id: ID of the log entry
        log_data: Updated log data

    Returns:
        Updated error log

    Raises:
        NotFoundException: If log not found
    """
    db_log = ErrorLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Error log with ID {log_id} not found")

    update_data = log_data.model_dump(exclude_unset=True)
    updated_log = ErrorLogRepository.update(db, log_id, update_data)

    return ErrorLogRead.model_validate(updated_log)


def delete_error_log(db: Session, log_id: int) -> bool:
    """
    Delete an error log

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        True if deleted successfully

    Raises:
        NotFoundException: If log not found
    """
    db_log = ErrorLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Error log with ID {log_id} not found")

    return ErrorLogRepository.delete(db, log_id)


class ErrorLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log lỗi
    """

    def __init__(self):
        self.repository = ErrorLogRepository()

    async def log_error(
        self,
        db: Session,
        error_type: str,
        severity: str,
        message: str,
        stack_trace: Optional[str] = None,
        user_id: Optional[int] = None,
        request_path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        component: Optional[str] = None,
        handled: bool = False,
    ) -> ErrorLogRead:
        """
        Ghi log lỗi

        Args:
            db: Phiên làm việc với database
            error_type: Loại lỗi
            severity: Mức độ nghiêm trọng
            message: Thông báo lỗi
            stack_trace: Stack trace của lỗi
            user_id: ID của người dùng
            request_path: Đường dẫn request
            context: Context khi xảy ra lỗi
            component: Component xảy ra lỗi
            handled: Lỗi đã được xử lý hay chưa

        Returns:
            Log lỗi đã được tạo
        """
        log_data = ErrorLogCreate(
            error_type=error_type,
            severity=severity,
            message=message,
            stack_trace=stack_trace,
            user_id=user_id,
            request_path=request_path,
            context=context,
            component=component,
            handled=handled,
        )

        log_dict = log_data.model_dump()
        db_log = self.repository.create(db, log_dict)
        return ErrorLogRead.model_validate(db_log)

    async def get_errors(
        self,
        db: Session,
        error_level: Optional[str] = None,
        error_code: Optional[str] = None,
        source: Optional[str] = None,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ErrorLogList:
        """
        Lấy danh sách log lỗi theo các điều kiện

        Args:
            db: Phiên làm việc với database
            error_level: Lọc theo mức độ lỗi
            error_code: Lọc theo mã lỗi
            source: Lọc theo nguồn
            user_id: Lọc theo ID người dùng
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách log lỗi và thông tin phân trang
        """
        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            error_level=error_level,
            error_code=error_code,
            source=source,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            error_level=error_level,
            error_code=error_code,
            source=source,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return ErrorLogList(
            items=[ErrorLogRead.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )

    async def update_error_resolution(
        self,
        db: Session,
        log_id: int,
        resolution_status: str,
        resolution_time: Optional[datetime] = None,
    ) -> ErrorLogRead:
        """
        Cập nhật thông tin giải quyết lỗi

        Args:
            db: Phiên làm việc với database
            log_id: ID của log lỗi
            resolution_status: Trạng thái giải quyết
            resolution_time: Thời gian giải quyết

        Returns:
            Log lỗi đã được cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy log lỗi
        """
        db_log = self.repository.get_by_id(db, log_id)
        if not db_log:
            raise NotFoundException(detail=f"Error log with ID {log_id} not found")

        update_data = {
            "resolution_status": resolution_status,
            "resolution_time": resolution_time or datetime.now(timezone.utc),
            "handled": True,
        }

        updated_log = self.repository.update(db, log_id, update_data)
        return ErrorLogRead.model_validate(updated_log)
