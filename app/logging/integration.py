"""
Module tích hợp logging với các tầng của API.
"""

import logging
from fastapi import FastAPI, Depends, Request
from typing import Callable, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from app.logging.setup import get_logger, get_admin_logger, get_user_logger
from app.logging.config import SENSITIVE_FIELDS
from app.core.db import get_session
from app.core.config import get_settings

settings = get_settings()

try:
    from app.security.audit import log_data_operation
except ImportError:
    # Fallback function if module doesn't exist
    def log_data_operation(**kwargs):
        """Fallback function when audit module is not available."""
        logging.getLogger("app.security").warning(
            "audit module not available, operation not logged to audit trail",
            extra=kwargs,
        )


def log_repository_operation(
    operation: str,
    resource_type: str,
    log_params: bool = True,
    log_result: bool = False,
    sensitive_params: Optional[list] = None,
):
    """
    Decorator để log các operation trong repository layer.

    Args:
        operation: Loại operation (create, read, update, delete)
        resource_type: Loại tài nguyên (user, book, etc.)
        log_params: Có log parameters không
        log_result: Có log kết quả không
        sensitive_params: Danh sách tên tham số nhạy cảm cần che dấu

    Returns:
        Decorator function
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Xác định nguồn gọi (admin hay user) dựa trên tên module
            module_name = func.__module__
            is_admin = "admin_site" in module_name
            site = "admin" if is_admin else "user"

            # Lấy logger phù hợp
            logger = (
                get_admin_logger("repositories")
                if is_admin
                else get_user_logger("repositories")
            )

            # Chuẩn bị thông tin để log
            func_name = func.__name__

            # Che dấu tham số nhạy cảm
            masked_kwargs = kwargs.copy()
            all_sensitive = sensitive_params or []
            all_sensitive.extend([p for p in SENSITIVE_FIELDS if p in masked_kwargs])

            for param in all_sensitive:
                if param in masked_kwargs:
                    masked_kwargs[param] = "***REDACTED***"

            # Log trước khi thực hiện
            if log_params:
                logger.info(
                    f"Repository {operation} operation on {resource_type}",
                    extra={
                        "operation": operation,
                        "resource_type": resource_type,
                        "function": func_name,
                        "params": masked_kwargs if masked_kwargs else "No parameters",
                    },
                )

            # Thực hiện function
            try:
                result = await func(*args, **kwargs)

                # Log kết quả nếu cần
                if log_result:
                    logger.debug(
                        f"Repository {operation} completed successfully",
                        extra={
                            "operation": operation,
                            "resource_type": resource_type,
                            "function": func_name,
                            "result_type": type(result).__name__,
                        },
                    )

                # Nếu là create/update/delete, log vào audit trail
                if operation in ["create", "update", "delete"] and "db" in kwargs:
                    # Lấy thông tin user nếu có
                    user_id = kwargs.get("user_id")
                    admin_id = kwargs.get("admin_id")

                    # Bỏ qua logging cho non-entity operations
                    if resource_type not in ["log", "cache", "token"]:
                        try:
                            # Lấy ID của resource nếu có
                            resource_id = None
                            if operation == "create" and hasattr(result, "id"):
                                resource_id = str(result.id)
                            elif "id" in kwargs:
                                resource_id = str(kwargs["id"])

                            log_data_operation(
                                operation=operation,
                                resource_type=resource_type,
                                resource_id=resource_id,
                                user_id=str(user_id) if user_id else None,
                                user_type=site,
                                status="success",
                                changes=masked_kwargs if log_params else None,
                                db=kwargs["db"],
                            )
                        except Exception as e:
                            logger.error(f"Error logging to audit trail: {str(e)}")

                return result

            except Exception as e:
                # Log lỗi
                logger.error(
                    f"Repository {operation} failed: {str(e)}",
                    extra={
                        "operation": operation,
                        "resource_type": resource_type,
                        "function": func_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

                # Log vào audit trail cho create/update/delete
                if operation in ["create", "update", "delete"] and "db" in kwargs:
                    try:
                        # Lấy thông tin user nếu có
                        user_id = kwargs.get("user_id")
                        admin_id = kwargs.get("admin_id")

                        # Xác định loại user
                        user_type = "admin" if admin_id else "user"

                        log_data_operation(
                            operation=operation,
                            resource_type=resource_type,
                            resource_id=str(kwargs.get("id", "")),
                            user_id=str(user_id or admin_id),
                            user_type=user_type,
                            status="error",
                            changes={"error": str(e)},
                            db=kwargs["db"],
                        )
                    except Exception as log_err:
                        logger.error(f"Error logging operation failure: {str(log_err)}")

                # Re-raise the exception
                raise

        # Handle non-async functions
        def sync_wrapper(*args, **kwargs):
            # Xác định nguồn gọi (admin hay user) dựa trên tên module
            module_name = func.__module__
            is_admin = "admin_site" in module_name
            site = "admin" if is_admin else "user"

            # Lấy logger phù hợp
            logger = (
                get_admin_logger("repositories")
                if is_admin
                else get_user_logger("repositories")
            )

            # Chuẩn bị thông tin để log
            func_name = func.__name__

            # Che dấu tham số nhạy cảm
            masked_kwargs = kwargs.copy()
            all_sensitive = sensitive_params or []
            all_sensitive.extend([p for p in SENSITIVE_FIELDS if p in masked_kwargs])

            for param in all_sensitive:
                if param in masked_kwargs:
                    masked_kwargs[param] = "***REDACTED***"

            # Log trước khi thực hiện
            if log_params:
                logger.info(
                    f"Repository {operation} operation on {resource_type}",
                    extra={
                        "operation": operation,
                        "resource_type": resource_type,
                        "function": func_name,
                        "params": masked_kwargs if masked_kwargs else "No parameters",
                    },
                )

            # Thực hiện function
            try:
                result = func(*args, **kwargs)

                # Log kết quả nếu cần
                if log_result:
                    logger.debug(
                        f"Repository {operation} completed successfully",
                        extra={
                            "operation": operation,
                            "resource_type": resource_type,
                            "function": func_name,
                            "result_type": type(result).__name__,
                        },
                    )

                # Nếu là create/update/delete, log vào audit trail
                if operation in ["create", "update", "delete"] and "db" in kwargs:
                    # Lấy thông tin user nếu có
                    user_id = kwargs.get("user_id")
                    admin_id = kwargs.get("admin_id")

                    # Bỏ qua logging cho non-entity operations
                    if resource_type not in ["log", "cache", "token"]:
                        try:
                            # Lấy ID của resource nếu có
                            resource_id = None
                            if operation == "create" and hasattr(result, "id"):
                                resource_id = str(result.id)
                            elif "id" in kwargs:
                                resource_id = str(kwargs["id"])

                            log_data_operation(
                                operation=operation,
                                resource_type=resource_type,
                                resource_id=resource_id,
                                user_id=str(user_id) if user_id else None,
                                user_type=site,
                                status="success",
                                changes=masked_kwargs if log_params else None,
                                db=kwargs["db"],
                            )
                        except Exception as e:
                            logger.error(f"Error logging to audit trail: {str(e)}")

                return result

            except Exception as e:
                # Log lỗi
                logger.error(
                    f"Repository {operation} failed: {str(e)}",
                    extra={
                        "operation": operation,
                        "resource_type": resource_type,
                        "function": func_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

                # Log vào audit trail cho create/update/delete
                if operation in ["create", "update", "delete"] and "db" in kwargs:
                    try:
                        # Lấy thông tin user nếu có
                        user_id = kwargs.get("user_id")
                        admin_id = kwargs.get("admin_id")

                        # Xác định loại user
                        user_type = "admin" if admin_id else "user"

                        log_data_operation(
                            operation=operation,
                            resource_type=resource_type,
                            resource_id=str(kwargs.get("id", "")),
                            user_id=str(user_id or admin_id),
                            user_type=user_type,
                            status="error",
                            changes={"error": str(e)},
                            db=kwargs["db"],
                        )
                    except Exception as log_err:
                        logger.error(f"Error logging operation failure: {str(log_err)}")

                # Re-raise the exception
                raise

        # Determine which wrapper to return based on if the function is async or not
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return wrapper
        else:
            return sync_wrapper

    return decorator


def log_service_call(
    service_name: str,
    log_input: bool = True,
    log_result: bool = False,
    sensitive_params: Optional[list] = None,
):
    """
    Decorator để log các cuộc gọi service.

    Args:
        service_name: Tên của service
        log_input: Có log input parameters không
        log_result: Có log kết quả không
        sensitive_params: Danh sách tên tham số nhạy cảm cần che dấu

    Returns:
        Decorator function
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Xác định nguồn gọi (admin hay user) dựa trên tên module
            module_name = func.__module__
            is_admin = "admin_site" in module_name

            # Lấy logger phù hợp
            logger = (
                get_admin_logger("services")
                if is_admin
                else get_user_logger("services")
            )

            # Chuẩn bị thông tin để log
            func_name = func.__name__

            # Che dấu tham số nhạy cảm
            masked_kwargs = kwargs.copy()
            all_sensitive = sensitive_params or []
            all_sensitive.extend([p for p in SENSITIVE_FIELDS if p in masked_kwargs])

            for param in all_sensitive:
                if param in masked_kwargs:
                    masked_kwargs[param] = "***REDACTED***"

            # Log trước khi thực hiện
            if log_input:
                logger.info(
                    f"Service call: {service_name}.{func_name}",
                    extra={
                        "service": service_name,
                        "method": func_name,
                        "params": masked_kwargs if masked_kwargs else "No parameters",
                    },
                )

            # Thực hiện function
            try:
                start_time = get_settings().START_TIME_FUNCTION_METHOD_NAME()
                result = await func(*args, **kwargs)
                elapsed_time = get_settings().END_TIME_FUNCTION_METHOD_NAME(start_time)

                # Log kết quả nếu cần
                if log_result:
                    logger.debug(
                        f"Service call completed: {service_name}.{func_name}",
                        extra={
                            "service": service_name,
                            "method": func_name,
                            "execution_time_ms": elapsed_time,
                            "result_type": type(result).__name__,
                        },
                    )
                else:
                    logger.debug(
                        f"Service call completed: {service_name}.{func_name}",
                        extra={
                            "service": service_name,
                            "method": func_name,
                            "execution_time_ms": elapsed_time,
                        },
                    )

                return result

            except Exception as e:
                # Log lỗi
                logger.error(
                    f"Service call failed: {service_name}.{func_name} - {str(e)}",
                    extra={
                        "service": service_name,
                        "method": func_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

                # Re-raise the exception
                raise

        # Handle non-async functions
        def sync_wrapper(*args, **kwargs):
            # Xác định nguồn gọi (admin hay user) dựa trên tên module
            module_name = func.__module__
            is_admin = "admin_site" in module_name

            # Lấy logger phù hợp
            logger = (
                get_admin_logger("services")
                if is_admin
                else get_user_logger("services")
            )

            # Chuẩn bị thông tin để log
            func_name = func.__name__

            # Che dấu tham số nhạy cảm
            masked_kwargs = kwargs.copy()
            all_sensitive = sensitive_params or []
            all_sensitive.extend([p for p in SENSITIVE_FIELDS if p in masked_kwargs])

            for param in all_sensitive:
                if param in masked_kwargs:
                    masked_kwargs[param] = "***REDACTED***"

            # Log trước khi thực hiện
            if log_input:
                logger.info(
                    f"Service call: {service_name}.{func_name}",
                    extra={
                        "service": service_name,
                        "method": func_name,
                        "params": masked_kwargs if masked_kwargs else "No parameters",
                    },
                )

            # Thực hiện function
            try:
                start_time = get_settings().START_TIME_FUNCTION_METHOD_NAME()
                result = func(*args, **kwargs)
                elapsed_time = get_settings().END_TIME_FUNCTION_METHOD_NAME(start_time)

                # Log kết quả nếu cần
                if log_result:
                    logger.debug(
                        f"Service call completed: {service_name}.{func_name}",
                        extra={
                            "service": service_name,
                            "method": func_name,
                            "execution_time_ms": elapsed_time,
                            "result_type": type(result).__name__,
                        },
                    )
                else:
                    logger.debug(
                        f"Service call completed: {service_name}.{func_name}",
                        extra={
                            "service": service_name,
                            "method": func_name,
                            "execution_time_ms": elapsed_time,
                        },
                    )

                return result

            except Exception as e:
                # Log lỗi
                logger.error(
                    f"Service call failed: {service_name}.{func_name} - {str(e)}",
                    extra={
                        "service": service_name,
                        "method": func_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

                # Re-raise the exception
                raise

        # Determine which wrapper to return based on if the function is async or not
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return wrapper
        else:
            return sync_wrapper

    return decorator


def log_api_call(request: Request, db: Session = Depends(get_session)):
    """
    Dependency để log API calls.

    Args:
        request: FastAPI request
        db: Database session

    Returns:
        None
    """
    # Xác định nguồn (admin hay user) dựa trên đường dẫn
    path = request.url.path
    is_admin = "/api/admin" in path or "/api/v1/admin" in path

    # Lấy logger phù hợp
    logger = get_admin_logger("api") if is_admin else get_user_logger("api")

    # Log message
    logger.info(
        f"API request: {request.method} {path}",
        extra={
            "method": request.method,
            "path": path,
            "query_params": dict(request.query_params),
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("User-Agent", "unknown"),
        },
    )

    # Lưu request vào state để có thể truy cập trong response
    request.state.log_start_time = get_settings().START_TIME_FUNCTION_METHOD_NAME()
    request.state.logger = logger

    return None
