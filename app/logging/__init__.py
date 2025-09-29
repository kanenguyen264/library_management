"""
Module logging - Cung cấp hệ thống ghi log toàn diện cho ứng dụng.

Module này bao gồm:
- Formatters: Định dạng log messages (JSON, màu sắc, ẩn thông tin nhạy cảm)
- Filters: Lọc log messages (loại bỏ thông tin nhạy cảm, theo path, audit)
- Handlers: Xử lý log output (file, database, Slack)
- Setup: Thiết lập logging cho ứng dụng
- Integration: Tích hợp logging với các tầng của API (Repository, Service, API)
"""

from app.logging.setup import (
    get_logger,
    setup_logging,
    get_admin_logger,
    get_user_logger,
    setup_admin_logging,
    setup_user_logging,
)
from app.logging.formatters import JSONFormatter, ColorizedFormatter, SecureFormatter
from app.logging.filters import SensitiveDataFilter, PathFilter, SecurityAuditFilter
from app.logging.handlers import (
    RotatingSecureFileHandler,
    SlackHandler,
    DatabaseHandler,
)
from app.logging.integration import (
    log_repository_operation,
    log_service_call,
    log_api_call,
)
from app.logging.config import (
    DEFAULT_LOGGING_CONFIG,
    DEVELOPMENT_LOGGING_CONFIG,
    PRODUCTION_LOGGING_CONFIG,
    TESTING_LOGGING_CONFIG,
    ADMIN_SITE_LOGGING_CONFIG,
    USER_SITE_LOGGING_CONFIG,
    SENSITIVE_FIELDS,
)

# Expose key functionality
__all__ = [
    # Setup
    "get_logger",
    "setup_logging",
    "get_admin_logger",
    "get_user_logger",
    "setup_admin_logging",
    "setup_user_logging",
    # Formatters
    "JSONFormatter",
    "ColorizedFormatter",
    "SecureFormatter",
    # Filters
    "SensitiveDataFilter",
    "PathFilter",
    "SecurityAuditFilter",
    # Handlers
    "RotatingSecureFileHandler",
    "SlackHandler",
    "DatabaseHandler",
    # Integration
    "log_repository_operation",
    "log_service_call",
    "log_api_call",
    # Config
    "DEFAULT_LOGGING_CONFIG",
    "DEVELOPMENT_LOGGING_CONFIG",
    "PRODUCTION_LOGGING_CONFIG",
    "TESTING_LOGGING_CONFIG",
    "ADMIN_SITE_LOGGING_CONFIG",
    "USER_SITE_LOGGING_CONFIG",
    "SENSITIVE_FIELDS",
]

# Module structure documentation
LOGGING_STRUCTURE = {
    "formatters": {
        "json": "Format logs as JSON for machine parsing",
        "colorized": "Format logs with colors for console readability",
        "secure": "Format logs with sensitive data masked",
    },
    "filters": {
        "sensitive_data": "Filter to mask sensitive data in logs",
        "path": "Filter logs by module path",
        "security_audit": "Filter to include security-related logs",
    },
    "handlers": {
        "rotating_secure_file": "Write logs to secure files with rotation",
        "slack": "Send important logs to Slack",
        "database": "Store structured logs in database",
    },
    "loggers": {
        "app": "Root application logger",
        "app.security": "Security-related logs",
        "app.api": "API request/response logs",
        "app.admin_site": "Admin site logs",
        "app.user_site": "User site logs",
        "app.errors": "Error logs",
    },
    "integration": {
        "log_repository_operation": "Decorator for repository operations",
        "log_service_call": "Decorator for service calls",
        "log_api_call": "Dependency for API endpoints",
    },
}
