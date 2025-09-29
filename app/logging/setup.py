import logging
import json
import sys
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from fastapi import FastAPI
from app.core.config import get_settings
from app.logging.formatters import JSONFormatter, ColorizedFormatter, SecureFormatter
from app.logging.filters import SensitiveDataFilter, SecurityAuditFilter, PathFilter
from app.logging.handlers import (
    RotatingSecureFileHandler,
    SlackHandler,
    DatabaseHandler,
)

# Define exported functions
__all__ = [
    "get_logger",
    "setup_logging",
    "get_admin_logger",
    "get_user_logger",
    "setup_admin_logging",
    "setup_user_logging",
]

settings = get_settings()


def get_logger(name: str, extra: Optional[Dict[str, Any]] = None) -> logging.Logger:
    """
    Lấy logger với cấu hình thích hợp.

    Args:
        name: Tên logger
        extra: Thông tin bổ sung cho tất cả log message

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    # Nếu logger đã có handler, trả về luôn
    if logger.hasHandlers():
        return logger

    # Set log level từ cấu hình - luôn đảm bảo có thể ghi DEBUG logs
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(
        min(log_level, logging.DEBUG)
    )  # Chọn mức thấp nhất giữa DEBUG và log_level

    # Tạo formatter dựa trên môi trường - luôn sử dụng ColorizedFormatter cho terminal
    formatter = ColorizedFormatter()

    # Tạo console handler và đảm bảo ghi ra stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    # Luôn đặt console handler ở mức DEBUG để xem mọi logs
    console_handler.setLevel(logging.DEBUG)

    # Thêm filter để che dấu thông tin nhạy cảm
    sensitive_filter = SensitiveDataFilter()
    console_handler.addFilter(sensitive_filter)

    logger.addHandler(console_handler)

    # Tạo file handler trong môi trường prod
    if settings.APP_ENV == "production":
        log_dir = Path(settings.LOG_DIR)
        log_dir.mkdir(exist_ok=True)

        # Với bảo mật, tạo log file riêng biệt
        if name.startswith("app.security") or "auth" in name:
            log_file = log_dir / "security.log"
            security_filter = SecurityAuditFilter()
            file_handler = RotatingSecureFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                permissions=0o600,  # Chỉ owner đọc/ghi
            )
            file_handler.addFilter(security_filter)
        elif name.startswith("app.admin_site"):
            log_file = log_dir / "admin.log"
            file_handler = RotatingSecureFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5
            )
        elif name.startswith("app.user_site"):
            log_file = log_dir / "user.log"
            file_handler = RotatingSecureFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5
            )
        else:
            log_file = log_dir / "app.log"
            file_handler = RotatingSecureFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5
            )

        secure_formatter = SecureFormatter()
        file_handler.setFormatter(secure_formatter)
        file_handler.addFilter(sensitive_filter)
        logger.addHandler(file_handler)

        # Thêm SlackHandler cho lỗi nghiêm trọng nếu có cấu hình Slack
        if hasattr(settings, "SLACK_WEBHOOK_URL") and settings.SLACK_WEBHOOK_URL:
            slack_handler = SlackHandler(
                webhook_url=settings.SLACK_WEBHOOK_URL,
                channel=(
                    settings.SLACK_CHANNEL
                    if hasattr(settings, "SLACK_CHANNEL")
                    else "#alerts"
                ),
            )
            slack_handler.setLevel(logging.ERROR)
            slack_handler.setFormatter(secure_formatter)
            logger.addHandler(slack_handler)

    # Thêm extra fields nếu có
    if extra:
        logger = logging.LoggerAdapter(logger, extra)

    return logger


def setup_logging(config_path: Optional[str] = None) -> None:
    """
    Thiết lập logging cho ứng dụng.

    Args:
        config_path: Đường dẫn đến file cấu hình logging (tùy chọn)
    """
    # Đảm bảo sử dụng module logging đã import ở đầu file
    import logging as py_logging

    # Cấu hình log level - luôn đảm bảo DEBUG để nhìn thấy traceback
    log_level = getattr(py_logging, settings.LOG_LEVEL.upper(), py_logging.INFO)
    # Luôn chọn mức thấp nhất giữa DEBUG và log_level để đảm bảo không bỏ qua logs quan trọng
    log_level = min(log_level, py_logging.DEBUG)

    # Create colorized formatter for development environment
    formatter = ColorizedFormatter()

    # Cấu hình luôn root logger để bắt mọi log
    root_logger = py_logging.getLogger()
    root_logger.setLevel(log_level)

    # Xóa handler cũ nếu có
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Thêm console handler để hiển thị mọi log
    console_handler = py_logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # Tắt một số logger bên ngoài quá chi tiết
    py_logging.getLogger("uvicorn.access").setLevel(log_level)
    py_logging.getLogger("uvicorn.error").setLevel(log_level)

    # Sử dụng file cấu hình nếu được cung cấp
    if config_path and os.path.exists(config_path):
        try:
            import logging.config

            logging.config.fileConfig(config_path, disable_existing_loggers=False)

            # Apply colorized formatter to all handlers in non-production environments
            if settings.APP_ENV != "production":
                root_logger = py_logging.getLogger()
                for handler in root_logger.handlers:
                    if isinstance(handler, py_logging.StreamHandler):
                        handler.setFormatter(formatter)

            return  # Không cần thực hiện các cấu hình bên dưới nếu đã sử dụng file cấu hình
        except Exception as e:
            print(f"Warning: Could not configure logging from file {config_path}: {e}")

    # Tạo thư mục logs nếu chưa tồn tại
    log_dir = Path(getattr(settings, "LOG_DIR", "logs"))
    log_dir.mkdir(exist_ok=True)

    # Đảm bảo quyền truy cập an toàn cho thư mục log
    if os.name != "nt":  # Chỉ áp dụng cho Unix/Linux
        try:
            os.chmod(log_dir, 0o755)  # rwxr-xr-x
        except Exception as e:
            print(f"Warning: Could not set log directory permissions: {e}")

    # Khởi tạo log files và handlers cho các hệ thống quan trọng
    if settings.APP_ENV == "production":
        # Tạo secure formatter chung
        secure_formatter = SecureFormatter()

        # Log dành riêng cho bảo mật
        security_logger = py_logging.getLogger("app.security")
        security_file_handler = RotatingSecureFileHandler(
            log_dir / "security.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            permissions=0o600,  # Chỉ owner đọc/ghi
        )
        security_file_handler.setFormatter(secure_formatter)
        security_filter = SecurityAuditFilter()
        security_file_handler.addFilter(security_filter)
        security_logger.addHandler(security_file_handler)

        # Log cho admin site
        admin_logger = py_logging.getLogger("app.admin_site")
        admin_file_handler = RotatingSecureFileHandler(
            log_dir / "admin.log", maxBytes=10 * 1024 * 1024, backupCount=5
        )
        admin_file_handler.setFormatter(secure_formatter)
        admin_filter = SensitiveDataFilter()
        admin_file_handler.addFilter(admin_filter)
        admin_logger.addHandler(admin_file_handler)

        # Log cho user site
        user_logger = py_logging.getLogger("app.user_site")
        user_file_handler = RotatingSecureFileHandler(
            log_dir / "user.log", maxBytes=10 * 1024 * 1024, backupCount=5
        )
        user_file_handler.setFormatter(secure_formatter)
        user_filter = SensitiveDataFilter()
        user_file_handler.addFilter(user_filter)
        user_logger.addHandler(user_file_handler)

        # Log cho API requests
        api_logger = py_logging.getLogger("app.api")
        api_file_handler = RotatingSecureFileHandler(
            log_dir / "api.log", maxBytes=10 * 1024 * 1024, backupCount=5
        )
        api_file_handler.setFormatter(JSONFormatter())
        api_logger.addHandler(api_file_handler)

        # Log cho errors
        error_logger = py_logging.getLogger("app.errors")
        error_file_handler = RotatingSecureFileHandler(
            log_dir / "errors.log", maxBytes=10 * 1024 * 1024, backupCount=5
        )
        error_file_handler.setFormatter(JSONFormatter())
        error_logger.addHandler(error_file_handler)

        # Setup database logging nếu được cấu hình
        if settings.LOG_TO_DATABASE and hasattr(settings, "DATABASE_URL"):
            try:
                from app.common.db.session import engine

                db_handler = DatabaseHandler(engine)
                db_handler.setLevel(py_logging.WARNING)  # Chỉ log từ warning trở lên

                # Thêm db_handler cho các logger quan trọng
                security_logger.addHandler(db_handler)
                error_logger.addHandler(db_handler)
            except ImportError:
                print("Warning: Could not setup database logging, missing dependencies")


def get_admin_logger(
    module_name: str, extra: Optional[Dict[str, Any]] = None
) -> logging.Logger:
    """
    Lấy logger được cấu hình đặc biệt cho admin site.

    Args:
        module_name: Tên module (không bao gồm app.admin_site)
        extra: Thông tin bổ sung cho tất cả log message

    Returns:
        Configured logger for admin site
    """
    full_name = (
        f"app.admin_site.{module_name}"
        if not module_name.startswith("app.admin_site")
        else module_name
    )

    # Thêm thông tin specific cho admin site
    admin_extra = extra or {}
    admin_extra.update({"site": "admin"})

    return get_logger(full_name, admin_extra)


def get_user_logger(
    module_name: str, extra: Optional[Dict[str, Any]] = None
) -> logging.Logger:
    """
    Lấy logger được cấu hình đặc biệt cho user site.

    Args:
        module_name: Tên module (không bao gồm app.user_site)
        extra: Thông tin bổ sung cho tất cả log message

    Returns:
        Configured logger for user site
    """
    full_name = (
        f"app.user_site.{module_name}"
        if not module_name.startswith("app.user_site")
        else module_name
    )

    # Thêm thông tin specific cho user site
    user_extra = extra or {}
    user_extra.update({"site": "user"})

    return get_logger(full_name, user_extra)


def setup_admin_logging(app: FastAPI) -> None:
    """
    Thiết lập logging đặc biệt cho admin site.

    Args:
        app: FastAPI application cho admin site
    """
    logger = get_admin_logger("api")
    logger.info("Initializing admin site logging")

    # Cấu hình các logger đặc biệt cho admin site
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(exist_ok=True)

    # Setup audit logging cho admin actions
    audit_logger = logging.getLogger("app.admin_site.audit")
    audit_file_handler = RotatingSecureFileHandler(
        log_dir / "admin_audit.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        permissions=0o600,  # Chỉ owner đọc/ghi
    )
    audit_file_handler.setFormatter(JSONFormatter())
    audit_logger.addHandler(audit_file_handler)

    # Thiết lập audit logging middleware
    from app.middlewares.logging_middleware import LoggingMiddleware

    app.add_middleware(
        LoggingMiddleware,
        log_headers=True,
        log_body=True,
        log_responses=True,
        sensitive_headers=["Authorization", "Cookie", "Set-Cookie"],
        sensitive_body_fields=["password", "token", "secret", "api_key"],
    )

    logger.info("Admin site logging configured successfully")


def setup_user_logging(app: FastAPI) -> None:
    """
    Thiết lập logging đặc biệt cho user site.

    Args:
        app: FastAPI application cho user site
    """
    logger = get_user_logger("api")
    logger.info("Initializing user site logging")

    # Cấu hình logging middleware cho user site với ít chi tiết hơn
    from app.middlewares.logging_middleware import LoggingMiddleware

    app.add_middleware(
        LoggingMiddleware,
        log_headers=True,
        log_body=False,  # Không log body cho user site để giảm kích thước log
        log_responses=False,  # Không log response cho user site
        log_errors_only=True,  # Chỉ log khi có lỗi
    )

    logger.info("User site logging configured successfully")


def force_colorize_all_loggers():
    """
    Force all existing loggers to use the ColorizedFormatter for their StreamHandlers.
    This is useful to ensure that all logs, including those from libraries, are colorized.
    """
    import logging

    if settings.APP_ENV == "production":
        return  # Don't colorize logs in production

    # Create the colorized formatter
    formatter = ColorizedFormatter()

    # Iterate through all existing loggers
    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)

        # Update all StreamHandlers to use the colorized formatter
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setFormatter(formatter)

    # Don't forget the root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setFormatter(formatter)

    logging.info("Applied colorized formatting to all loggers")


# Expand exported functions
__all__ += ["force_colorize_all_loggers"]
