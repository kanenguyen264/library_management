from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.logs_manager.repositories.api_request_log_repo import ApiRequestLogRepository
from app.logs_manager.schemas.api_request_log import (
    ApiRequestLogCreate,
    ApiRequestLogUpdate,
    ApiRequestLogRead,
    ApiRequestLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


def create_api_request_log(
    db: Session, log_data: ApiRequestLogCreate
) -> ApiRequestLogRead:
    """
    Create a new API request log entry

    Args:
        db: Database session
        log_data: API request log data

    Returns:
        Created API request log
    """
    try:
        repo = ApiRequestLogRepository()
        db_log = repo.create_log(db, log_data)
        return ApiRequestLogRead.model_validate(db_log)
    except Exception as e:
        logger.error(f"Error creating API request log: {str(e)}")
        raise


def get_api_request_log(db: Session, log_id: int) -> ApiRequestLogRead:
    """
    Get API request log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        API request log

    Raises:
        NotFoundException: If log not found
    """
    repo = ApiRequestLogRepository()
    db_log = repo.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"API request log with ID {log_id} not found")
    return ApiRequestLogRead.model_validate(db_log)


def get_api_request_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    user_id: Optional[int] = None,
    admin_id: Optional[int] = None,
    client_ip: Optional[str] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> ApiRequestLogList:
    """
    Get API request logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        endpoint: Filter by API endpoint
        method: Filter by HTTP method
        status_code: Filter by status code
        user_id: Filter by user ID
        admin_id: Filter by admin ID
        client_ip: Filter by client IP address
        min_duration: Minimum request duration in ms
        max_duration: Maximum request duration in ms
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of API request logs
    """
    repo = ApiRequestLogRepository()

    # Sử dụng phương thức get_all trên đối tượng
    result = repo.get_all(
        db=db,
        filters={
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "user_id": user_id,
            "admin_id": admin_id,
            "client_ip": client_ip,
            "min_duration": min_duration,
            "max_duration": max_duration,
            "start_date": start_date,
            "end_date": end_date,
        },
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    # Lấy dữ liệu từ kết quả
    logs = result["items"]
    total = result["total"]

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return ApiRequestLogList(
        items=[ApiRequestLogRead.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


def get_error_requests(
    db: Session, days: int = 7, skip: int = 0, limit: int = 100
) -> ApiRequestLogList:
    """
    Get API requests that resulted in errors

    Args:
        db: Database session
        days: Number of days to look back
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of API request logs with error status codes
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    return get_api_request_logs(
        db=db,
        skip=skip,
        limit=limit,
        min_status_code=400,  # Consider 400+ as errors
        start_date=start_date,
        sort_by="timestamp",
        sort_desc=True,
    )


def get_slow_requests(
    db: Session,
    min_duration_ms: float = 1000.0,  # 1 second
    days: int = 7,
    skip: int = 0,
    limit: int = 100,
) -> ApiRequestLogList:
    """
    Get slow API requests

    Args:
        db: Database session
        min_duration_ms: Minimum request duration in milliseconds to consider as slow
        days: Number of days to look back
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of slow API request logs
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    return get_api_request_logs(
        db=db,
        skip=skip,
        limit=limit,
        min_duration=min_duration_ms,
        start_date=start_date,
        sort_by="duration_ms",
        sort_desc=True,
    )


def get_requests_by_endpoint(
    db: Session,
    endpoint: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 100,
) -> ApiRequestLogList:
    """
    Get API requests for a specific endpoint

    Args:
        db: Database session
        endpoint: API endpoint
        start_date: Filter by start date
        end_date: Filter by end date
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of API request logs for the specified endpoint
    """
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=7)

    return get_api_request_logs(
        db=db,
        skip=skip,
        limit=limit,
        endpoint=endpoint,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


def get_endpoint_stats(db: Session, days: int = 7) -> List[Dict[str, Any]]:
    """
    Get statistics for each API endpoint for the past days

    Args:
        db: Database session
        days: Number of days to look back

    Returns:
        List of dictionaries with endpoint statistics
    """
    repo = ApiRequestLogRepository()
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    return repo.get_endpoint_stats(db, start_date=start_date, limit=20)


def delete_api_request_log(db: Session, log_id: int) -> bool:
    """
    Delete API request log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        True if log was deleted, False if not found

    Raises:
        NotFoundException: If log not found
    """
    repo = ApiRequestLogRepository()
    db_log = repo.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"API request log with ID {log_id} not found")

    return repo.delete(db, log_id)


def cleanup_old_logs(db: Session, days: int = 90) -> int:
    """
    Delete logs older than the specified number of days

    Args:
        db: Database session
        days: Number of days to keep logs for

    Returns:
        Number of logs deleted
    """
    repo = ApiRequestLogRepository()
    return repo.delete_old_logs(db, days)


class ApiRequestLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log request API
    """

    def __init__(self):
        self.repository = ApiRequestLogRepository()

    async def log_request(
        self,
        db: Session,
        endpoint: str,
        method: str,
        status_code: int,
        user_id: Optional[int] = None,
        admin_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        response_time: Optional[float] = None,
        request_body: Optional[Dict[str, Any]] = None,
        response_body: Optional[Dict[str, Any]] = None,
    ) -> ApiRequestLogRead:
        """
        Ghi log request API

        Args:
            db: Phiên làm việc với database
            endpoint: Đường dẫn API
            method: Phương thức HTTP
            status_code: Mã trạng thái HTTP
            user_id: ID của người dùng
            admin_id: ID của admin
            ip_address: Địa chỉ IP
            response_time: Thời gian phản hồi (ms)
            request_body: Body của request
            response_body: Body của response

        Returns:
            Log request API đã được tạo
        """
        log_data = ApiRequestLogCreate(
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            user_id=user_id,
            admin_id=admin_id,
            ip_address=ip_address,
            response_time=response_time,
            request_body=request_body,
            response_body=response_body,
        )

        db_log = self.repository.create_log(db, log_data)
        return ApiRequestLogRead.model_validate(db_log)

    async def get_api_requests(
        self,
        db: Session,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[int] = None,
        user_id: Optional[int] = None,
        admin_id: Optional[int] = None,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ApiRequestLogList:
        """
        Lấy danh sách log request API theo các điều kiện

        Args:
            db: Phiên làm việc với database
            endpoint: Lọc theo đường dẫn API
            method: Lọc theo phương thức HTTP
            status_code: Lọc theo mã trạng thái
            user_id: Lọc theo ID người dùng
            admin_id: Lọc theo ID admin
            min_duration: Thời gian phản hồi tối thiểu
            max_duration: Thời gian phản hồi tối đa
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách log request API và thông tin phân trang
        """
        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            user_id=user_id,
            admin_id=admin_id,
            min_duration=min_duration,
            max_duration=max_duration,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            user_id=user_id,
            admin_id=admin_id,
            min_duration=min_duration,
            max_duration=max_duration,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return ApiRequestLogList(
            items=[ApiRequestLogRead.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )
