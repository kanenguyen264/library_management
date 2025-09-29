"""
Module giám sát (Monitoring) - Cung cấp các công cụ theo dõi, ghi metrics và truy vết ứng dụng.

Module này bao gồm:
- Alerting: Hệ thống cảnh báo theo các ngưỡng và sự kiện
- APM: Application Performance Monitoring (Giám sát hiệu suất ứng dụng)
- Metrics: Thu thập và báo cáo các metrics của ứng dụng
- Tracing: Phân tích và theo dõi các request xuyên suốt hệ thống
"""

# Import các module con
from app.monitoring import alerting
from app.monitoring import apm
from app.monitoring import metrics
from app.monitoring import tracing

# Export các hàm và class chính cho dễ sử dụng
from app.monitoring.metrics import (
    track_auth_request,
    track_request_duration,
    track_error_request,
)

from app.monitoring.apm.apm_agent import APMAgent, initialize_apm, trace_function

from app.monitoring.alerting.alerts import (
    AlertSeverity,
    AlertChannel,
    alert_on_exception,
    get_alerting_system,
)

from app.monitoring.tracing.tracer import Tracer, trace, setup_tracer, TracingMiddleware


# Hàm tiện ích để khởi tạo toàn bộ hệ thống monitoring
def setup_monitoring(
    app, service_name: str = "api_readingbook", env: str = "development"
):
    """
    Thiết lập toàn bộ hệ thống monitoring cho ứng dụng.

    Args:
        app: Ứng dụng FastAPI
        service_name: Tên service
        env: Môi trường (development, staging, production)
    """
    # Khởi tạo APM
    initialize_apm(service_name, env)

    # Thiết lập tracer
    setup_tracer(service_name)

    # Thêm middleware tracing
    app.add_middleware(TracingMiddleware)

    # Khởi tạo metrics exporter
    metrics.metrics.start_exporter()

    # Khởi tạo alerting system (nếu trong production)
    if env == "production":
        from app.monitoring.alerting import initialize_alert_channels

        initialize_alert_channels()


__all__ = [
    "setup_monitoring",
    "alerting",
    "apm",
    "metrics",
    "tracing",
    "track_auth_request",
    "track_request_duration",
    "track_error_request",
    "APMAgent",
    "initialize_apm",
    "trace_function",
    "get_alerting_system",
    "AlertSeverity",
    "AlertChannel",
    "alert_on_exception",
    "Tracer",
    "trace",
    "setup_tracer",
    "TracingMiddleware",
]
