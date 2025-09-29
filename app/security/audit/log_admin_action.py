from typing import Dict, Any, Optional, Union, List
from fastapi import Request, Response, Depends
from sqlalchemy.orm import Session
import json
import time
import asyncio
from functools import wraps
from app.common.db.session import get_db
from app.core.config import get_settings
from app.logging.setup import get_logger
from app.security.audit.audit_trails import (
    get_audit_trail,
    log_data_operation,
    log_access_attempt,
)

# Import Admin model conditionally to avoid circular imports
try:
    from app.admin_site.models import Admin
except ImportError:
    # Define a placeholder class for type hints
    class Admin:
        id: int = 0


settings = get_settings()
logger = get_logger(__name__)


def log_admin_action(
    action: str,
    resource_type: str,
    resource_id: Optional[Union[str, int]] = None,
    description: Optional[str] = None,
    changes: Optional[Dict[str, Any]] = None,
):
    """
    Decorator for logging admin actions.

    Args:
        action: Action performed (create, update, delete, view, etc.)
        resource_type: Type of resource (role, permission, setting, etc.)
        resource_id: ID of the resource (optional)
        description: Description of the action
        changes: Changes made (for update operations)

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract admin, db, and request from kwargs
            current_admin = None
            db = None
            request = None

            for key, value in kwargs.items():
                if isinstance(value, Admin):
                    current_admin = value
                elif isinstance(value, Session):
                    db = value
                elif isinstance(value, Request):
                    request = value

            if not db:
                # Get db from dependency if not in kwargs
                db = next(get_db())

            # Get resource_id from kwargs if not provided
            actual_resource_id = resource_id
            if not actual_resource_id and "id" in kwargs:
                actual_resource_id = kwargs["id"]

            # Prepare log details
            details = {}
            if changes:
                details["changes"] = changes
            if description:
                details["description"] = description

            # Setup timing and request info
            start_time = time.time()
            ip_address = None
            user_agent = None

            if request:
                # Get IP and User-Agent
                forwarded = request.headers.get("X-Forwarded-For")
                ip_address = (
                    forwarded.split(",")[0].strip()
                    if forwarded
                    else request.client.host
                )
                user_agent = request.headers.get("User-Agent")

                # Add request info to details
                details["endpoint"] = request.url.path
                details["method"] = request.method

                # Add query params if available
                if request.query_params:
                    details["query_params"] = dict(request.query_params)

            try:
                # Execute the function
                response = await func(*args, **kwargs)

                # Log successful execution
                if current_admin:
                    # Calculate execution time
                    execution_time = time.time() - start_time
                    details["execution_time"] = execution_time

                    # Log the operation
                    log_data_operation(
                        operation=action,
                        resource_type=resource_type,
                        resource_id=(
                            str(actual_resource_id) if actual_resource_id else None
                        ),
                        user_id=str(current_admin.id),
                        user_type="admin",
                        status="success",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        changes=details,
                        db=db,
                    )

                return response

            except Exception as e:
                # Log execution failure
                if current_admin:
                    details["error"] = str(e)
                    details["error_type"] = e.__class__.__name__

                    log_data_operation(
                        operation=action,
                        resource_type=resource_type,
                        resource_id=(
                            str(actual_resource_id) if actual_resource_id else None
                        ),
                        user_id=str(current_admin.id),
                        user_type="admin",
                        status="error",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        changes=details,
                        db=db,
                    )

                # Re-raise the exception
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Same implementation as async but for sync functions
            current_admin = None
            db = None
            request = None

            for key, value in kwargs.items():
                if isinstance(value, Admin):
                    current_admin = value
                elif isinstance(value, Session):
                    db = value
                elif isinstance(value, Request):
                    request = value

            if not db:
                db = next(get_db())

            actual_resource_id = resource_id
            if not actual_resource_id and "id" in kwargs:
                actual_resource_id = kwargs["id"]

            details = {}
            if changes:
                details["changes"] = changes
            if description:
                details["description"] = description

            start_time = time.time()
            ip_address = None
            user_agent = None

            if request:
                forwarded = request.headers.get("X-Forwarded-For")
                ip_address = (
                    forwarded.split(",")[0].strip()
                    if forwarded
                    else request.client.host
                )
                user_agent = request.headers.get("User-Agent")
                details["endpoint"] = request.url.path
                details["method"] = request.method
                if request.query_params:
                    details["query_params"] = dict(request.query_params)

            try:
                response = func(*args, **kwargs)

                if current_admin:
                    execution_time = time.time() - start_time
                    details["execution_time"] = execution_time

                    log_data_operation(
                        operation=action,
                        resource_type=resource_type,
                        resource_id=(
                            str(actual_resource_id) if actual_resource_id else None
                        ),
                        user_id=str(current_admin.id),
                        user_type="admin",
                        status="success",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        changes=details,
                        db=db,
                    )

                return response

            except Exception as e:
                if current_admin:
                    details["error"] = str(e)
                    details["error_type"] = e.__class__.__name__

                    log_data_operation(
                        operation=action,
                        resource_type=resource_type,
                        resource_id=(
                            str(actual_resource_id) if actual_resource_id else None
                        ),
                        user_id=str(current_admin.id),
                        user_type="admin",
                        status="error",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        changes=details,
                        db=db,
                    )

                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def log_admin_access(
    resource_type: str, action: str = "access", requires_admin: bool = True
):
    """
    Decorator for logging admin API access.

    Args:
        resource_type: Type of resource being accessed
        action: Action being performed
        requires_admin: Whether admin privileges are required

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract admin and request info
            current_admin = None
            request = None

            for key, value in kwargs.items():
                if isinstance(value, Admin):
                    current_admin = value
                elif isinstance(value, Request):
                    request = value

            # Basic info
            details = {}
            endpoint = None
            method = None
            ip_address = None
            user_agent = None

            if request:
                # Get request details
                forwarded = request.headers.get("X-Forwarded-For")
                ip_address = (
                    forwarded.split(",")[0].strip()
                    if forwarded
                    else request.client.host
                )
                user_agent = request.headers.get("User-Agent")
                endpoint = request.url.path
                method = request.method
                details["query_params"] = (
                    dict(request.query_params) if request.query_params else {}
                )

            start_time = time.time()

            try:
                # Log access attempt
                if current_admin:
                    log_access_attempt(
                        user_id=current_admin.id,
                        user_type="admin",
                        resource_type=resource_type,
                        action=action,
                        status="attempt",
                        endpoint=endpoint,
                        method=method,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )

                # Execute function
                response = await func(*args, **kwargs)

                # Log successful access
                if current_admin:
                    execution_time = time.time() - start_time
                    details["execution_time"] = execution_time

                    log_access_attempt(
                        user_id=current_admin.id,
                        user_type="admin",
                        resource_type=resource_type,
                        action=action,
                        status="success",
                        endpoint=endpoint,
                        method=method,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        duration=execution_time,
                    )

                return response

            except Exception as e:
                # Log access failure
                if current_admin:
                    details["error"] = str(e)
                    details["error_type"] = e.__class__.__name__

                    log_access_attempt(
                        user_id=current_admin.id,
                        user_type="admin",
                        resource_type=resource_type,
                        action=action,
                        status="error",
                        endpoint=endpoint,
                        method=method,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        error=str(e),
                    )

                # Re-raise exception
                raise

        return wrapper

    return decorator


def log_admin_login(db: Session = None):
    """
    Hàm ghi log đăng nhập admin.

    Args:
        db: Session database (tùy chọn)

    Returns:
        Hàm decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            request = None
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value

            # Thông tin cơ bản
            ip_address = None
            user_agent = None
            if request:
                forwarded = request.headers.get("X-Forwarded-For")
                ip_address = (
                    forwarded.split(",")[0].strip()
                    if forwarded
                    else request.client.host
                )
                user_agent = request.headers.get("User-Agent")

            current_db = db
            if not current_db:
                current_db = next(get_db())

            # Thực thi hàm đăng nhập
            try:
                response = await func(*args, **kwargs)

                # Nếu thành công, lấy thông tin admin
                admin_id = None
                username = None

                # Extract admin info from response
                if hasattr(response, "model_dump"):
                    data = response.model_dump()
                    if "user" in data and "id" in data["user"]:
                        admin_id = data["user"]["id"]
                    if "user" in data and "username" in data["user"]:
                        username = data["user"]["username"]

                # Log successful login
                if admin_id:
                    log_data_operation(
                        operation="login",
                        resource_type="authentication",
                        resource_id=None,
                        user_id=str(admin_id),
                        user_type="admin",
                        status="success",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        changes={"username": username},
                        db=current_db,
                    )

                return response

            except Exception as e:
                # Log failed login attempt if possible
                username = None
                for a in args:
                    if hasattr(a, "username"):
                        username = a.username

                if not username:
                    for key, value in kwargs.items():
                        if key == "username" or (
                            hasattr(value, "username") and value.username
                        ):
                            username = value if key == "username" else value.username

                if username:
                    log_data_operation(
                        operation="login",
                        resource_type="authentication",
                        resource_id=None,
                        user_id=username,  # Use username as we don't have ID for failed logins
                        user_type="admin",
                        status="error",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        changes={"error": str(e)},
                        db=current_db,
                    )

                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Similar implementation for sync functions
            request = None
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value

            ip_address = None
            user_agent = None
            if request:
                forwarded = request.headers.get("X-Forwarded-For")
                ip_address = (
                    forwarded.split(",")[0].strip()
                    if forwarded
                    else request.client.host
                )
                user_agent = request.headers.get("User-Agent")

            current_db = db
            if not current_db:
                current_db = next(get_db())

            try:
                response = func(*args, **kwargs)

                admin_id = None
                username = None

                if hasattr(response, "model_dump"):
                    data = response.model_dump()
                    if "user" in data and "id" in data["user"]:
                        admin_id = data["user"]["id"]
                    if "user" in data and "username" in data["user"]:
                        username = data["user"]["username"]

                if admin_id:
                    log_data_operation(
                        operation="login",
                        resource_type="authentication",
                        resource_id=None,
                        user_id=str(admin_id),
                        user_type="admin",
                        status="success",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        changes={"username": username},
                        db=current_db,
                    )

                return response

            except Exception as e:
                username = None
                for a in args:
                    if hasattr(a, "username"):
                        username = a.username

                if not username:
                    for key, value in kwargs.items():
                        if key == "username" or (
                            hasattr(value, "username") and value.username
                        ):
                            username = value if key == "username" else value.username

                if username:
                    log_data_operation(
                        operation="login",
                        resource_type="authentication",
                        resource_id=None,
                        user_id=username,
                        user_type="admin",
                        status="error",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        changes={"error": str(e)},
                        db=current_db,
                    )

                raise

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def log_admin_logout(db: Session = None):
    """
    Hàm ghi log đăng xuất admin.

    Args:
        db: Session database (tùy chọn)

    Returns:
        Hàm decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract admin info
            current_admin = None
            request = None

            for key, value in kwargs.items():
                if isinstance(value, Admin):
                    current_admin = value
                elif isinstance(value, Request):
                    request = value

            # Thông tin cơ bản
            ip_address = None
            user_agent = None
            if request:
                forwarded = request.headers.get("X-Forwarded-For")
                ip_address = (
                    forwarded.split(",")[0].strip()
                    if forwarded
                    else request.client.host
                )
                user_agent = request.headers.get("User-Agent")

            current_db = db
            if not current_db:
                current_db = next(get_db())

            # Log the logout
            if current_admin:
                log_data_operation(
                    operation="logout",
                    resource_type="authentication",
                    resource_id=None,
                    user_id=str(current_admin.id),
                    user_type="admin",
                    status="success",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    db=current_db,
                )

            # Execute the function
            response = await func(*args, **kwargs)
            return response

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Similar implementation for sync functions
            current_admin = None
            request = None

            for key, value in kwargs.items():
                if isinstance(value, Admin):
                    current_admin = value
                elif isinstance(value, Request):
                    request = value

            ip_address = None
            user_agent = None
            if request:
                forwarded = request.headers.get("X-Forwarded-For")
                ip_address = (
                    forwarded.split(",")[0].strip()
                    if forwarded
                    else request.client.host
                )
                user_agent = request.headers.get("User-Agent")

            current_db = db
            if not current_db:
                current_db = next(get_db())

            if current_admin:
                log_data_operation(
                    operation="logout",
                    resource_type="authentication",
                    resource_id=None,
                    user_id=str(current_admin.id),
                    user_type="admin",
                    status="success",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    db=current_db,
                )

            response = func(*args, **kwargs)
            return response

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
