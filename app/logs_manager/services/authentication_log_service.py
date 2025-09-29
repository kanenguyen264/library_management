from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging
import json

from app.logs_manager.repositories.authentication_log_repo import (
    AuthenticationLogRepository,
)
from app.logs_manager.models.authentication_log import AuthenticationLog
from app.logs_manager.schemas.authentication_log import (
    AuthenticationLogCreate,
    AuthenticationLogUpdate,
    AuthenticationLogRead,
    AuthenticationLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException
from app.logging.setup import get_logger

logger = get_logger(__name__)


# Helper function to recursively ensure JSON serializability
def ensure_serializable(obj):
    """Recursively convert any non-serializable objects to strings"""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, Exception):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: ensure_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [ensure_serializable(item) for item in obj]
    elif hasattr(obj, "__dict__"):
        # For custom objects that can be converted to dict
        return ensure_serializable(obj.__dict__)
    else:
        # For any other type, convert to string
        return str(obj)


async def create_authentication_log(
    db: Session, log_data: AuthenticationLogCreate, raise_exception: bool = True
) -> Optional[AuthenticationLogRead]:
    """
    Create a new authentication log entry

    Args:
        db: Database session (can be AsyncSession or regular Session)
        log_data: Authentication log data
        raise_exception: Whether to raise an exception on error (True) or return None (False)

    Returns:
        Created authentication log or None if error and raise_exception is False
    """
    try:
        # Sanitize log data to ensure it's serializable
        if hasattr(log_data, "details") and log_data.details:
            log_data.details = ensure_serializable(log_data.details)

        # Instantiate repository
        log_repo = AuthenticationLogRepository()

        # Check if we have an async session
        is_async_session = hasattr(db, "execute") and hasattr(db.execute, "__await__")

        try:
            # Create the log entry with proper method call
            if is_async_session:
                db_log = await log_repo.create_log(db, log_data)
            else:
                # For sync sessions, we need to use sync methods
                # Extract the details field from log_data to handle separately
                log_dict = log_data.model_dump(exclude_unset=True)
                details_data = log_dict.pop("details", None)

                # Đảm bảo trường action được truyền đúng cách
                if (
                    "action" not in log_dict
                    and details_data
                    and "action" in details_data
                ):
                    log_dict["action"] = details_data.pop("action")

                # If we have details, convert them to JSON for failure_reason field
                if details_data:
                    if (
                        "failure_reason" not in log_dict
                        or not log_dict["failure_reason"]
                    ):
                        # Convert details to string and use as failure_reason if not already set
                        try:
                            log_dict["failure_reason"] = json.dumps(details_data)
                        except Exception:
                            # If can't convert to JSON, use string representation
                            log_dict["failure_reason"] = str(details_data)

                db_log = AuthenticationLog(**log_dict)
                db.add(db_log)

                # Check if we're accidentally using an AsyncSession with sync methods
                if hasattr(db.commit, "__await__"):
                    await db.commit()
                    await db.refresh(db_log)
                else:
                    # Regular sync session
                    db.commit()
                    db.refresh(db_log)

            # Validate the result
            if not db_log or not hasattr(db_log, "id"):
                import traceback

                logger.error(
                    f"Failed to create authentication log: Invalid result returned\nCall stack: {traceback.format_stack()}"
                )
                if raise_exception:
                    raise ValueError(
                        "Failed to create authentication log: Invalid result returned"
                    )
                return None

            # Return the properly formed response
            try:
                return AuthenticationLogRead.model_validate(db_log)
            except Exception as validation_error:
                logger.error(
                    f"Error validating authentication log: {str(validation_error)}"
                )
                # Tạo một dummy log response
                return AuthenticationLogRead(
                    id=-1,
                    user_id=log_data.user_id if hasattr(log_data, "user_id") else None,
                    event_type=(
                        log_data.event_type
                        if hasattr(log_data, "event_type")
                        else "unknown"
                    ),
                    status="error",
                    is_success=False,
                    timestamp=datetime.now(timezone.utc),
                    details={
                        "error": "Validation error",
                        "original_data": (
                            log_data.model_dump()
                            if hasattr(log_data, "model_dump")
                            else str(log_data)
                        ),
                    },
                )

        except Exception as e:
            import traceback

            logger.error(
                f"Error in authentication log repository: {str(e)}\nTraceback: {traceback.format_exc()}",
                exc_info=True,
            )
            if raise_exception:
                raise
            return None

    except Exception as e:
        import traceback

        logger.error(
            f"Error creating authentication log: {str(e)}\nTraceback: {traceback.format_exc()}",
            exc_info=True,
        )
        if raise_exception:
            raise
        return None


async def get_authentication_log(db: Session, log_id: int) -> AuthenticationLogRead:
    """
    Get authentication log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        Authentication log

    Raises:
        NotFoundException: If log not found
    """
    repo = AuthenticationLogRepository()
    db_log = await repo.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Authentication log with ID {log_id} not found")
    return AuthenticationLogRead.model_validate(db_log)


async def get_authentication_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    admin_id: Optional[int] = None,
    action: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> AuthenticationLogList:
    """
    Get authentication logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        user_id: Filter by user ID
        admin_id: Filter by admin ID
        action: Filter by action
        status: Filter by status
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of authentication logs
    """
    repo = AuthenticationLogRepository()
    logs = await repo.get_all(
        db=db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        admin_id=admin_id,
        action=action,
        status=status,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total = await AuthenticationLogRepository.count(
        db=db,
        user_id=user_id,
        admin_id=admin_id,
        action=action,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return AuthenticationLogList(
        items=[AuthenticationLogRead.model_validate(log) for log in logs["items"]],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


async def get_authentication_logs_by_user(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    action: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> AuthenticationLogList:
    """
    Get authentication logs for a specific user

    Args:
        db: Database session
        user_id: User ID
        skip: Number of records to skip
        limit: Maximum number of records to return
        action: Filter by action
        status: Filter by status
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of authentication logs
    """
    return await get_authentication_logs(
        db=db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        action=action,
        status=status,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


async def get_authentication_logs_by_admin(
    db: Session,
    admin_id: int,
    skip: int = 0,
    limit: int = 20,
    action: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> AuthenticationLogList:
    """
    Get authentication logs for a specific admin

    Args:
        db: Database session
        admin_id: Admin ID
        skip: Number of records to skip
        limit: Maximum number of records to return
        action: Filter by action
        status: Filter by status
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of authentication logs
    """
    return await get_authentication_logs(
        db=db,
        skip=skip,
        limit=limit,
        admin_id=admin_id,
        action=action,
        status=status,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


async def get_failed_authentication_attempts(
    db: Session,
    user_id: Optional[int] = None,
    admin_id: Optional[int] = None,
    window_minutes: int = 30,
    limit: int = 10,
) -> List[AuthenticationLogRead]:
    """
    Get recent failed authentication attempts

    Args:
        db: Database session
        user_id: Filter by user ID
        admin_id: Filter by admin ID
        window_minutes: Time window in minutes
        limit: Maximum number of records to return

    Returns:
        List of failed authentication logs
    """
    start_date = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    repo = AuthenticationLogRepository()

    logs = await repo.get_all(
        db=db,
        skip=0,
        limit=limit,
        user_id=user_id,
        admin_id=admin_id,
        status="failed",
        start_date=start_date,
        sort_by="timestamp",
        sort_desc=True,
    )

    return [AuthenticationLogRead.model_validate(log) for log in logs["items"]]


class AuthenticationLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log xác thực người dùng
    """

    def __init__(self):
        self.repository = AuthenticationLogRepository()

    async def log_authentication(
        self,
        db: Session,
        event_type: str,
        status: str,
        is_success: bool,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        location: Optional[Dict[str, Any]] = None,
        user_agent: Optional[str] = None,
        device_info: Optional[Dict[str, Any]] = None,
        failure_reason: Optional[str] = None,
        auth_method: Optional[str] = None,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuthenticationLogRead:
        """
        Ghi log xác thực người dùng

        Args:
            db: Phiên làm việc với database (can be AsyncSession or regular Session)
            event_type: Loại sự kiện xác thực
            status: Trạng thái xác thực
            is_success: Xác thực thành công hay không
            user_id: ID của người dùng
            ip_address: Địa chỉ IP
            location: Thông tin vị trí
            user_agent: User agent của trình duyệt
            device_info: Thông tin thiết bị
            failure_reason: Lý do thất bại (nếu có)
            auth_method: Phương thức xác thực
            session_id: ID phiên làm việc
            details: Thông tin chi tiết bổ sung (tùy chọn)

        Returns:
            Log xác thực đã được tạo
        """
        try:
            # Sanitize all input data to ensure it's serializable
            if details:
                details = ensure_serializable(details)
                # Nếu details có action, lấy giá trị để sử dụng cho trường action
                action_value = details.pop("action", None)
            else:
                action_value = None

            if location:
                location = ensure_serializable(location)

            if device_info:
                device_info = ensure_serializable(device_info)

            # Make sure user_id is properly handled
            if user_id is not None:
                try:
                    user_id = int(user_id)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid user_id provided: {user_id}, using None instead"
                    )
                    user_id = None

            log_data = AuthenticationLogCreate(
                user_id=user_id,
                event_type=event_type,
                action=action_value,  # Sử dụng giá trị action đã được trích xuất
                status=status,
                is_success=is_success,
                ip_address=ip_address,
                location=location,
                user_agent=user_agent,
                device_info=device_info,
                failure_reason=failure_reason,
                auth_method=auth_method,
                session_id=session_id,
                details=details,
            )

            try:
                # Check if it's an async session
                is_async_session = hasattr(db, "execute") and hasattr(
                    db.execute, "__await__"
                )

                if is_async_session:
                    # Use async repository method
                    db_log = await self.repository.create_log(db, log_data)
                else:
                    # For sync sessions, use direct model creation
                    # Extract the details field from log_data to handle separately
                    log_dict = log_data.model_dump(exclude_unset=True)
                    details_data = log_dict.pop("details", None)

                    # Đảm bảo trường action được truyền đúng cách
                    if (
                        "action" not in log_dict
                        and details_data
                        and "action" in details_data
                    ):
                        log_dict["action"] = details_data.pop("action")

                    # If we have details, convert them to JSON for failure_reason field
                    if details_data:
                        if (
                            "failure_reason" not in log_dict
                            or not log_dict["failure_reason"]
                        ):
                            # Convert details to string and use as failure_reason if not already set
                            try:
                                log_dict["failure_reason"] = json.dumps(details_data)
                            except Exception:
                                # If can't convert to JSON, use string representation
                                log_dict["failure_reason"] = str(details_data)

                    # Create the log entry directly - NO async operations for sync sessions
                    db_log = AuthenticationLog(**log_dict)

                    # Use non-async commit for non-async session
                    db.add(db_log)

                    # Check if we're accidentally using an AsyncSession with sync methods
                    if hasattr(db.commit, "__await__"):
                        await db.commit()
                        await db.refresh(db_log)
                    else:
                        # Regular sync session
                        db.commit()
                        db.refresh(db_log)

                # Return the properly formed response
                return AuthenticationLogRead.model_validate(db_log)
            except Exception as e:
                import traceback

                logger.error(
                    f"Error creating authentication log in database: {str(e)}\nTraceback: {traceback.format_exc()}",
                    exc_info=True,
                )
                # Don't raise - create a dummy log instead
                dummy_log = {
                    "id": -1,  # Dummy ID
                    "user_id": user_id,
                    "event_type": event_type,
                    "status": "error",
                    "is_success": False,
                    "timestamp": datetime.now(timezone.utc),
                    "ip_address": ip_address,
                    "details": {"error": str(e), "traceback": traceback.format_exc()},
                }
                return AuthenticationLogRead(**dummy_log)
        except Exception as e:
            import traceback

            logger.error(
                f"Error preparing authentication log data: {str(e)}\nTraceback: {traceback.format_exc()}",
                exc_info=True,
            )
            # Don't raise - create a dummy log instead
            dummy_log = {
                "id": -2,  # Different dummy ID
                "user_id": user_id,
                "event_type": "error",
                "status": "error",
                "is_success": False,
                "timestamp": datetime.now(timezone.utc),
                "ip_address": ip_address,
                "details": {"error": str(e), "traceback": traceback.format_exc()},
            }
            return AuthenticationLogRead(**dummy_log)

    async def get_user_authentication_logs(
        self,
        db: Session,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AuthenticationLogList:
        """
        Lấy danh sách log xác thực của người dùng

        Args:
            db: Phiên làm việc với database (can be AsyncSession or regular Session)
            user_id: ID của người dùng
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách log xác thực và thông tin phân trang
        """
        try:
            skip = (page - 1) * page_size

            # Check if it's an async session
            is_async_session = hasattr(db, "execute") and hasattr(
                db.execute, "__await__"
            )

            if is_async_session:
                logs = await self.repository.get_all(
                    db=db,
                    skip=skip,
                    limit=page_size,
                    user_id=user_id,
                    start_date=start_date,
                    end_date=end_date,
                    sort_by="timestamp",
                    sort_desc=True,
                )

                total = await self.repository.count(
                    db=db,
                    user_id=user_id,
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                # For sync sessions, use direct queries
                query = db.query(AuthenticationLog).filter(
                    AuthenticationLog.user_id == user_id
                )

                if start_date:
                    query = query.filter(AuthenticationLog.timestamp >= start_date)
                if end_date:
                    query = query.filter(AuthenticationLog.timestamp <= end_date)

                total = query.count()

                logs = {
                    "items": query.order_by(AuthenticationLog.timestamp.desc())
                    .offset(skip)
                    .limit(page_size)
                    .all(),
                    "total": total,
                    "page": page,
                    "size": page_size,
                    "pages": (
                        (total + page_size - 1) // page_size if page_size > 0 else 1
                    ),
                }

            # Calculate pagination info
            pages = (total + page_size - 1) // page_size if page_size > 0 else 1

            return AuthenticationLogList(
                items=[
                    AuthenticationLogRead.model_validate(log) for log in logs["items"]
                ],
                total=total,
                page=page,
                size=page_size,
                pages=pages,
            )
        except Exception as e:
            import traceback

            logger.error(
                f"Error getting user authentication logs: {str(e)}\nTraceback: {traceback.format_exc()}",
                exc_info=True,
            )
            # Return empty response on error
            return AuthenticationLogList(
                items=[],
                total=0,
                page=page,
                size=page_size,
                pages=0,
            )
