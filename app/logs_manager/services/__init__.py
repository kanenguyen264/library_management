from app.logs_manager.services.user_activity_log_service import (
    create_user_activity_log,
    get_user_activity_log,
    get_user_activity_logs,
    get_user_activities_by_user,
    update_user_activity_log,
    delete_user_activity_log,
)

from app.logs_manager.services.admin_activity_log_service import (
    create_admin_activity_log,
    get_admin_activity_log,
    get_admin_activity_logs,
    get_admin_activities_by_admin,
    update_admin_activity_log,
    delete_admin_activity_log,
)

from app.logs_manager.services.error_log_service import (
    create_error_log,
    get_error_log,
    get_error_logs,
    get_error_logs_by_level,
    update_error_log,
    delete_error_log,
)

from app.logs_manager.services.authentication_log_service import (
    create_authentication_log,
    get_authentication_log,
    get_authentication_logs,
    get_authentication_logs_by_user,
    get_authentication_logs_by_admin,
    get_failed_authentication_attempts,
)

from app.logs_manager.services.performance_log_service import (
    create_performance_log,
    get_performance_log,
    get_performance_logs,
    get_slow_operations,
    get_slow_endpoints,
    get_performance_stats,
)

from app.logs_manager.services.api_request_log_service import (
    create_api_request_log,
    get_api_request_log,
    get_api_request_logs,
    get_requests_by_endpoint,
    get_endpoint_stats,
)

from app.logs_manager.services.search_log_service import (
    create_search_log,
    get_search_log,
    get_search_logs,
    get_popular_search_terms,
    get_zero_results_searches,
    update_clicked_results,
)

from app.logs_manager.services.log_analysis_service import (
    get_log_summary,
    get_error_trends,
    get_user_activity_trends,
    get_admin_activity_trends,
    get_api_usage_trends,
    get_performance_trends,
    get_authentication_trends,
    get_search_trends,
)

from app.logs_manager.services.security_log_service import (
    create_security_log,
    get_security_log,
    get_security_logs,
    get_high_severity_logs,
    update_security_log_resolution,
)

from app.logs_manager.services.system_log_service import (
    create_system_log,
    get_system_log,
    get_system_logs,
    get_component_logs,
    get_failed_operations,
)

from app.logs_manager.services.audit_log_service import (
    create_audit_log,
    get_audit_log,
    get_audit_logs,
    get_resource_audit_logs,
    get_user_audit_logs,
)

from app.logs_manager.services.admin_activity_log_service import AdminActivityLogService
from app.logs_manager.services.api_request_log_service import ApiRequestLogService
from app.logs_manager.services.authentication_log_service import (
    AuthenticationLogService,
)
from app.logs_manager.services.error_log_service import ErrorLogService
from app.logs_manager.services.log_analysis_service import LogAnalysisService
from app.logs_manager.services.performance_log_service import PerformanceLogService
from app.logs_manager.services.search_log_service import SearchLogService
from app.logs_manager.services.user_activity_log_service import UserActivityLogService
from app.logs_manager.services.security_log_service import SecurityLogService
from app.logs_manager.services.system_log_service import SystemLogService
from app.logs_manager.services.audit_log_service import AuditLogService

# Khởi tạo singleton services
admin_activity_log_service = AdminActivityLogService()
api_request_log_service = ApiRequestLogService()
authentication_log_service = AuthenticationLogService()
error_log_service = ErrorLogService()
log_analysis_service = LogAnalysisService()
performance_log_service = PerformanceLogService()
search_log_service = SearchLogService()
user_activity_log_service = UserActivityLogService()
security_log_service = SecurityLogService()
system_log_service = SystemLogService()
audit_log_service = AuditLogService()

__all__ = [
    # User Activity Log
    "create_user_activity_log",
    "get_user_activity_log",
    "get_user_activity_logs",
    "get_user_activities_by_user",
    "update_user_activity_log",
    "delete_user_activity_log",
    # Admin Activity Log
    "create_admin_activity_log",
    "get_admin_activity_log",
    "get_admin_activity_logs",
    "get_admin_activities_by_admin",
    "update_admin_activity_log",
    "delete_admin_activity_log",
    # Error Log
    "create_error_log",
    "get_error_log",
    "get_error_logs",
    "get_error_logs_by_level",
    "update_error_log",
    "delete_error_log",
    # Authentication Log
    "create_authentication_log",
    "get_authentication_log",
    "get_authentication_logs",
    "get_authentication_logs_by_user",
    "get_authentication_logs_by_admin",
    "get_failed_authentication_attempts",
    # Performance Log
    "create_performance_log",
    "get_performance_log",
    "get_performance_logs",
    "get_slow_operations",
    "get_slow_endpoints",
    "get_performance_stats",
    # API Request Log
    "create_api_request_log",
    "get_api_request_log",
    "get_api_request_logs",
    "get_requests_by_endpoint",
    "get_endpoint_stats",
    # Search Log
    "create_search_log",
    "get_search_log",
    "get_search_logs",
    "get_popular_search_terms",
    "get_zero_results_searches",
    "update_clicked_results",
    # Log Analysis
    "get_log_summary",
    "get_error_trends",
    "get_user_activity_trends",
    "get_admin_activity_trends",
    "get_api_usage_trends",
    "get_performance_trends",
    "get_authentication_trends",
    "get_search_trends",
    # Security Log
    "create_security_log",
    "get_security_log",
    "get_security_logs",
    "get_high_severity_logs",
    "update_security_log_resolution",
    # System Log
    "create_system_log",
    "get_system_log",
    "get_system_logs",
    "get_component_logs",
    "get_failed_operations",
    # Audit Log
    "create_audit_log",
    "get_audit_log",
    "get_audit_logs",
    "get_resource_audit_logs",
    "get_user_audit_logs",
    # Service instances
    "admin_activity_log_service",
    "api_request_log_service",
    "authentication_log_service",
    "error_log_service",
    "log_analysis_service",
    "performance_log_service",
    "search_log_service",
    "user_activity_log_service",
    "security_log_service",
    "system_log_service",
    "audit_log_service",
]
