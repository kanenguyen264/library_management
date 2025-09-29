from app.logs_manager.repositories.search_log_repo import SearchLogRepository
from app.logs_manager.repositories.user_activity_log_repo import (
    UserActivityLogRepository,
)
from app.logs_manager.repositories.admin_activity_log_repo import (
    AdminActivityLogRepository,
)
from app.logs_manager.repositories.api_request_log_repo import ApiRequestLogRepository
from app.logs_manager.repositories.authentication_log_repo import (
    AuthenticationLogRepository,
)
from app.logs_manager.repositories.error_log_repo import ErrorLogRepository
from app.logs_manager.repositories.performance_log_repo import PerformanceLogRepository
from app.logs_manager.repositories.log_rotation_repo import LogRotationRepository
from app.logs_manager.repositories.security_log_repo import SecurityLogRepository
from app.logs_manager.repositories.system_log_repo import SystemLogRepository
from app.logs_manager.repositories.audit_log_repo import AuditLogRepository

# Khởi tạo singleton instances
search_log_repo = SearchLogRepository()
user_activity_log_repo = UserActivityLogRepository()
admin_activity_log_repo = AdminActivityLogRepository()
api_request_log_repo = ApiRequestLogRepository()
authentication_log_repo = AuthenticationLogRepository()
error_log_repo = ErrorLogRepository()
performance_log_repo = PerformanceLogRepository()
security_log_repo = SecurityLogRepository()
system_log_repo = SystemLogRepository()
audit_log_repo = AuditLogRepository()
log_rotation_repo = LogRotationRepository()

__all__ = [
    "search_log_repo",
    "user_activity_log_repo",
    "admin_activity_log_repo",
    "api_request_log_repo",
    "authentication_log_repo",
    "error_log_repo",
    "performance_log_repo",
    "security_log_repo",
    "system_log_repo",
    "audit_log_repo",
    "log_rotation_repo",
]
