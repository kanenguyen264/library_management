import json
import time
import uuid
from typing import Any, Dict, List, Optional, Union
from fastapi import Request, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.config import get_settings
from app.logging.setup import get_logger
from app.core.constants import SECURITY_EVENT

settings = get_settings()
logger = get_logger(__name__)


class AuditEvent(BaseModel):
    """Audit event data model."""

    id: str
    timestamp: float
    event_type: str
    actor_id: Optional[str] = None
    actor_type: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: str
    status: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    severity: str = "INFO"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.dict()


class AuditLogger:
    """
    Lớp ghi nhật ký kiểm toán (audit) cho các hoạt động trong hệ thống.
    Cung cấp các phương thức tiện ích để ghi nhật ký audit một cách nhất quán.
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Khởi tạo audit logger.

        Args:
            db: SQLAlchemy session (optional)
        """
        self.db = db
        self.audit_trail = AuditTrail(db)

    def log_user_activity(
        self,
        user_id: Union[str, int],
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
        severity: str = "INFO",
    ) -> str:
        """
        Ghi nhật ký hoạt động của người dùng.

        Args:
            user_id: ID của người dùng
            action: Hành động thực hiện
            resource_type: Loại tài nguyên tác động
            resource_id: ID của tài nguyên
            status: Trạng thái (success/failure)
            details: Chi tiết bổ sung
            request: FastAPI request
            severity: Mức độ nghiêm trọng

        Returns:
            Event ID
        """
        return self.audit_trail.log_event(
            event_type="user_activity",
            action=action,
            status=status,
            actor_id=str(user_id),
            actor_type="user",
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            request=request,
            severity=severity,
        )

    def log_admin_activity(
        self,
        admin_id: Union[str, int],
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
        severity: str = "INFO",
    ) -> str:
        """
        Ghi nhật ký hoạt động của quản trị viên.

        Args:
            admin_id: ID của quản trị viên
            action: Hành động thực hiện
            resource_type: Loại tài nguyên tác động
            resource_id: ID của tài nguyên
            status: Trạng thái (success/failure)
            details: Chi tiết bổ sung
            request: FastAPI request
            severity: Mức độ nghiêm trọng

        Returns:
            Event ID
        """
        return self.audit_trail.log_event(
            event_type="admin_activity",
            action=action,
            status=status,
            actor_id=str(admin_id),
            actor_type="admin",
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            request=request,
            severity=severity,
        )

    def log_auth_event(
        self,
        action: str,
        status: str,
        user_id: Optional[Union[str, int]] = None,
        user_type: str = "user",
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
        severity: str = "INFO",
    ) -> str:
        """
        Ghi nhật ký sự kiện xác thực.

        Args:
            action: Hành động (login/logout/password_reset)
            status: Trạng thái (success/failure)
            user_id: ID của người dùng (nếu có)
            user_type: Loại người dùng (user/admin)
            details: Chi tiết bổ sung
            request: FastAPI request
            severity: Mức độ nghiêm trọng

        Returns:
            Event ID
        """
        if status == "failure" and severity == "INFO":
            severity = "WARNING"

        return self.audit_trail.log_event(
            event_type="authentication",
            action=action,
            status=status,
            actor_id=str(user_id) if user_id else None,
            actor_type=user_type,
            details=details,
            request=request,
            severity=severity,
        )

    def log_data_access(
        self,
        user_id: Union[str, int],
        user_type: str,
        resource_type: str,
        action: str = "read",
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
    ) -> str:
        """
        Ghi nhật ký truy cập dữ liệu.

        Args:
            user_id: ID của người dùng
            user_type: Loại người dùng (user/admin)
            resource_type: Loại tài nguyên
            action: Hành động (read/list)
            resource_id: ID của tài nguyên
            status: Trạng thái (success/failure)
            details: Chi tiết bổ sung
            request: FastAPI request

        Returns:
            Event ID
        """
        severity = "INFO"
        if status == "failure":
            severity = "WARNING"

        return self.audit_trail.log_event(
            event_type="data_access",
            action=action,
            status=status,
            actor_id=str(user_id),
            actor_type=user_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            request=request,
            severity=severity,
        )

    def log_data_modification(
        self,
        user_id: Union[str, int],
        user_type: str,
        resource_type: str,
        action: str,
        resource_id: Optional[str] = None,
        status: str = "success",
        changes: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
    ) -> str:
        """
        Ghi nhật ký sửa đổi dữ liệu.

        Args:
            user_id: ID của người dùng
            user_type: Loại người dùng (user/admin)
            resource_type: Loại tài nguyên
            action: Hành động (create/update/delete)
            resource_id: ID của tài nguyên
            status: Trạng thái (success/failure)
            changes: Thay đổi
            request: FastAPI request

        Returns:
            Event ID
        """
        return self.audit_trail.log_event(
            event_type="data_modification",
            action=action,
            status=status,
            actor_id=str(user_id),
            actor_type=user_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=changes,
            request=request,
            severity="INFO",
        )

    def log_security_event(
        self,
        event_name: str,
        severity: str,
        details: Dict[str, Any],
        user_id: Optional[Union[str, int]] = None,
        user_type: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> str:
        """
        Ghi nhật ký sự kiện bảo mật.

        Args:
            event_name: Tên sự kiện
            severity: Mức độ nghiêm trọng
            details: Chi tiết
            user_id: ID của người dùng (nếu có)
            user_type: Loại người dùng (nếu có)
            request: FastAPI request

        Returns:
            Event ID
        """
        return self.audit_trail.log_event(
            event_type="security",
            action=event_name,
            status="detected",
            actor_id=str(user_id) if user_id else None,
            actor_type=user_type,
            details=details,
            request=request,
            severity=severity,
        )


class AuditTrail:
    """
    Lớp quản lý audit trail cho security events và user actions.
    Lưu trữ trong database và tích hợp với logging.
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Khởi tạo audit trail.

        Args:
            db: SQLAlchemy session
        """
        self.db = db

    def log_event(
        self,
        event_type: str,
        action: str,
        status: str,
        actor_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_path: Optional[str] = None,
        request_method: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "INFO",
        request: Optional[Request] = None,
        db: Optional[Session] = None,
    ) -> str:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            action: Action performed
            status: Status of action
            actor_id: ID of actor
            actor_type: Type of actor
            resource_type: Type of resource
            resource_id: ID of resource
            ip_address: IP address
            user_agent: User agent
            request_path: Request path
            request_method: Request method
            details: Additional details
            severity: Severity level
            request: FastAPI request
            db: SQLAlchemy session

        Returns:
            Event ID
        """
        # Generate event ID
        event_id = str(uuid.uuid4())

        # Extract info from request if provided
        if request and not ip_address:
            forwarded = request.headers.get("X-Forwarded-For")
            ip_address = (
                forwarded.split(",")[0].strip() if forwarded else request.client.host
            )

        if request and not user_agent:
            user_agent = request.headers.get("User-Agent")

        if request and not request_path:
            request_path = request.url.path

        if request and not request_method:
            request_method = request.method

        # Create event object
        event = AuditEvent(
            id=event_id,
            timestamp=time.time(),
            event_type=event_type,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
            request_path=request_path,
            request_method=request_method,
            details=details,
            severity=severity,
        )

        # Log the event
        self._log_to_file(event)

        # Store in database
        self._store_in_db(event, db or self.db)

        return event_id

    def _log_to_file(self, event: AuditEvent) -> None:
        """
        Log event to file using logger.

        Args:
            event: Audit event
        """
        log_data = event.to_dict()

        # Determine log level
        if event.severity == "INFO":
            logger.info(
                f"AUDIT: {event.event_type} - {event.action} - {event.status}",
                extra={"audit": log_data},
            )
        elif event.severity == "WARNING":
            logger.warning(
                f"AUDIT: {event.event_type} - {event.action} - {event.status}",
                extra={"audit": log_data},
            )
        elif event.severity == "ERROR":
            logger.error(
                f"AUDIT: {event.event_type} - {event.action} - {event.status}",
                extra={"audit": log_data},
            )
        elif event.severity == "CRITICAL":
            logger.critical(
                f"AUDIT: {event.event_type} - {event.action} - {event.status}",
                extra={"audit": log_data},
            )

    def _store_in_db(self, event: AuditEvent, db: Optional[Session]) -> None:
        """
        Store event in database.

        Args:
            event: Audit event
            db: SQLAlchemy session
        """
        if not db:
            return

        try:
            # Admin activity log
            if event.actor_type == "admin":
                from app.logs_manager.models.admin_activity_log import AdminActivityLog

                log_entry = AdminActivityLog(
                    admin_id=int(event.actor_id) if event.actor_id else None,
                    activity_type=event.action,
                    description=f"{event.event_type}: {event.status}",
                    ip_address=event.ip_address,
                    affected_resource=event.resource_type,
                    resource_id=event.resource_id,
                    changes_json=json.dumps(event.details) if event.details else None,
                )
                db.add(log_entry)

            # User activity log
            elif event.actor_type == "user":
                from app.logs_manager.models.user_activity_log import UserActivityLog

                log_entry = UserActivityLog(
                    user_id=int(event.actor_id) if event.actor_id else None,
                    activity_type=event.action,
                    entity_type=event.resource_type,
                    entity_id=event.resource_id,
                    description=f"{event.event_type}: {event.status}",
                    metadata_json=event.details,
                    ip_address=event.ip_address,
                    user_agent=event.user_agent,
                )
                db.add(log_entry)

            # Authentication log
            elif event.event_type == "authentication":
                from app.logs_manager.models.authentication_log import AuthenticationLog

                # Determine user_id and admin_id
                user_id = None
                admin_id = None

                if event.actor_type == "user":
                    user_id = int(event.actor_id) if event.actor_id else None
                elif event.actor_type == "admin":
                    admin_id = int(event.actor_id) if event.actor_id else None

                log_entry = AuthenticationLog(
                    user_id=user_id,
                    admin_id=admin_id,
                    event_type=event.action,
                    status=event.status,
                    ip_address=event.ip_address,
                    user_agent=event.user_agent,
                )
                db.add(log_entry)

            # Error log
            elif event.severity in ["ERROR", "CRITICAL"]:
                from app.logs_manager.models.error_log import ErrorLog

                # Determine user_id and admin_id
                user_id = None
                admin_id = None

                if event.actor_type == "user":
                    user_id = int(event.actor_id) if event.actor_id else None
                elif event.actor_type == "admin":
                    admin_id = int(event.actor_id) if event.actor_id else None

                log_entry = ErrorLog(
                    error_level=event.severity,
                    error_message=f"{event.event_type}: {event.action} - {event.status}",
                    stack_trace=(
                        event.details.get("stack_trace") if event.details else None
                    ),
                    source=event.details.get("source") if event.details else None,
                    user_id=user_id,
                    admin_id=admin_id,
                    ip_address=event.ip_address,
                    user_agent=event.user_agent,
                    request_data=event.details,
                )
                db.add(log_entry)

            # Commit changes
            db.commit()

        except Exception as e:
            logger.error(f"Error storing audit event in database: {e}")
            db.rollback()


# Global audit trail instance
_audit_trail = None


def get_audit_trail(db: Optional[Session] = None) -> AuditTrail:
    """
    Get the singleton AuditTrail instance.

    Args:
        db: SQLAlchemy session

    Returns:
        AuditTrail instance
    """
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = AuditTrail(db)
    elif db and not _audit_trail.db:
        _audit_trail.db = db

    return _audit_trail


def log_auth_success(
    user_id: str,
    user_type: str,
    ip_address: str,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> str:
    """
    Log successful authentication.

    Args:
        user_id: User ID
        user_type: User type (user or admin)
        ip_address: IP address
        user_agent: User agent
        details: Additional details
        db: SQLAlchemy session

    Returns:
        Event ID
    """
    if details is None:
        details = {}

    if "action" not in details:
        details["action"] = "login"

    audit = get_audit_trail(db)
    return audit.log_event(
        event_type="authentication",
        action=details.get("action", "login"),
        status="success",
        actor_id=user_id,
        actor_type=user_type,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
    )


def log_auth_failure(
    username: str,
    ip_address: str,
    reason: str,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> str:
    """
    Log failed authentication.

    Args:
        username: Username
        ip_address: IP address
        reason: Failure reason
        user_agent: User agent
        details: Additional details
        db: SQLAlchemy session

    Returns:
        Event ID
    """
    if details is None:
        details = {}

    details["username"] = username
    details["reason"] = reason

    if "action" not in details:
        details["action"] = "login"

    audit = get_audit_trail(db)
    return audit.log_event(
        event_type="authentication",
        action=details.get("action", "login"),
        status="failure",
        severity="WARNING",
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
    )


def log_access_attempt(
    ip_address: str,
    endpoint: str,
    method: str,
    status_code: int,
    processing_time: Optional[float] = None,
    user_id: Optional[str] = None,
    user_type: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> str:
    """
    Log API access attempt.

    Args:
        ip_address: IP address
        endpoint: API endpoint
        method: HTTP method
        status_code: HTTP status code
        processing_time: Request processing time in seconds
        user_id: User ID if authenticated
        user_type: User type if authenticated
        user_agent: User agent
        details: Additional details
        db: SQLAlchemy session

    Returns:
        Event ID
    """
    if details is None:
        details = {}

    details["endpoint"] = endpoint
    details["method"] = method
    details["status_code"] = status_code

    if processing_time is not None:
        details["processing_time"] = processing_time

    if "action" not in details:
        details["action"] = "api_access"

    # Determine severity based on status code
    severity = "INFO"
    if status_code >= 400:
        severity = "WARNING"
    if status_code >= 500:
        severity = "ERROR"

    audit = get_audit_trail(db)
    return audit.log_event(
        event_type="access",
        action=details.get("action", "api_access"),
        status="success" if status_code < 400 else "failure",
        actor_id=user_id,
        actor_type=user_type,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
        severity=severity,
    )


def log_data_operation(
    operation: str,
    resource_type: str,
    resource_id: str,
    user_id: str,
    user_type: str,
    status: str,
    ip_address: Optional[str] = None,
    changes: Optional[Dict[str, Any]] = None,
    user_agent: Optional[str] = None,
    db: Optional[Session] = None,
) -> str:
    """
    Log a data operation.

    Args:
        operation: Operation performed (create, update, delete)
        resource_type: Type of resource
        resource_id: ID of resource
        user_id: User ID
        user_type: User type (user or admin)
        status: Status of operation
        ip_address: IP address
        changes: Changes made
        user_agent: User agent
        db: SQLAlchemy session

    Returns:
        Event ID
    """
    details = {"changes": changes} if changes else {}

    audit = get_audit_trail(db)
    return audit.log_event(
        event_type="data_operation",
        action=operation,
        status=status,
        actor_id=user_id,
        actor_type=user_type,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
    )


def log_security_event(
    event_name: str,
    severity: str,
    details: Dict[str, Any],
    user_id: Optional[str] = None,
    user_type: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_path: Optional[str] = None,
    request_method: Optional[str] = None,
    db: Optional[Session] = None,
) -> str:
    """
    Log a security event.

    Args:
        event_name: Name of event
        severity: Severity level
        details: Event details
        user_id: User ID
        user_type: User type (user or admin)
        ip_address: IP address
        user_agent: User agent
        request_path: Request path
        request_method: Request method
        db: SQLAlchemy session

    Returns:
        Event ID
    """
    audit = get_audit_trail(db)
    return audit.log_event(
        event_type=SECURITY_EVENT,
        action=event_name,
        status="detected",
        actor_id=user_id,
        actor_type=user_type,
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path,
        request_method=request_method,
        details=details,
        severity=severity,
    )
