from typing import Dict, List, Any, Optional, Union, Set, Tuple
import time
import asyncio
import logging
import psutil
import threading
import os
from enum import Enum
from functools import wraps
import json
import uuid
import socket
from datetime import datetime, timedelta
from prometheus_client import Counter, Histogram, Gauge, Summary
from prometheus_client import start_http_server, push_to_gateway
import platform

from app.core.config import get_settings
from app.logging.setup import get_logger


settings = get_settings()
logger = get_logger(__name__)

# Override metrics enabled flags to prevent startup issues
settings.METRICS_ENABLED = False
settings.PROMETHEUS_ENABLED = False

# Create empty metrics registry to avoid duplicate registration issues
# Global registry
METRIC_REGISTRY = {}

# Biến để theo dõi việc khởi tạo
_app_metrics_initialized = False


# Wrap Prometheus metric creation functions to avoid registration when disabled
def safe_counter(name, documentation, labelnames=(), **kwargs):
    if name in METRIC_REGISTRY:
        return METRIC_REGISTRY[name]

    # Only create actual Counter if metrics are enabled
    if settings.METRICS_ENABLED:
        counter = Counter(name, documentation, labelnames, **kwargs)
    else:
        # Create a dummy counter that does nothing
        counter = DummyMetric(name, documentation, labelnames)

    METRIC_REGISTRY[name] = counter
    return counter


def safe_histogram(name, documentation, labelnames=(), **kwargs):
    if name in METRIC_REGISTRY:
        return METRIC_REGISTRY[name]

    # Only create actual Histogram if metrics are enabled
    if settings.METRICS_ENABLED:
        histogram = Histogram(name, documentation, labelnames, **kwargs)
    else:
        # Create a dummy histogram that does nothing
        histogram = DummyMetric(name, documentation, labelnames)

    METRIC_REGISTRY[name] = histogram
    return histogram


def safe_summary(name, documentation, labelnames=(), **kwargs):
    if name in METRIC_REGISTRY:
        return METRIC_REGISTRY[name]

    # Only create actual Summary if metrics are enabled
    if settings.METRICS_ENABLED:
        summary = Summary(name, documentation, labelnames, **kwargs)
    else:
        # Create a dummy summary that does nothing
        summary = DummyMetric(name, documentation, labelnames)

    METRIC_REGISTRY[name] = summary
    return summary


def safe_gauge(name, documentation, labelnames=(), **kwargs):
    if name in METRIC_REGISTRY:
        return METRIC_REGISTRY[name]

    # Only create actual Gauge if metrics are enabled
    if settings.METRICS_ENABLED:
        gauge = Gauge(name, documentation, labelnames, **kwargs)
    else:
        # Create a dummy gauge that does nothing
        gauge = DummyMetric(name, documentation, labelnames)

    METRIC_REGISTRY[name] = gauge
    return gauge


# A dummy metric class that provides the same interface but does nothing
class DummyMetric:
    def __init__(self, name, documentation, labelnames):
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames

    def labels(self, *args, **kwargs):
        return self

    def inc(self, amount=1):
        pass

    def dec(self, amount=1):
        pass

    def set(self, value):
        pass

    def observe(self, value):
        pass


# Các nhóm metrics
class MetricsCategory(str, Enum):
    """Danh mục metrics."""

    HTTP = "http"  # Metrics liên quan đến HTTP requests
    DATABASE = "database"  # Metrics liên quan đến database queries
    CACHE = "cache"  # Metrics liên quan đến cache
    SYSTEM = "system"  # Metrics hệ thống (CPU, RAM, disk)
    BUSINESS = "business"  # Metrics nghiệp vụ (đăng ký, đăng nhập, etc.)
    AUTH = "auth"  # Metrics xác thực
    SECURITY = "security"  # Metrics bảo mật
    PERFORMANCE = "performance"  # Metrics hiệu suất


# HTTP Metrics
HTTP_REQUEST_LATENCY = safe_histogram(
    "http_request_latency_seconds",
    "Thời gian xử lý request HTTP",
    ["method", "endpoint", "status_code"],
    buckets=[
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1,
        2.5,
        5,
        7.5,
        10,
        25,
        50,
        75,
        100,
    ],
)

HTTP_REQUEST_COUNT = safe_counter(
    "http_request_total", "Tổng số request HTTP", ["method", "endpoint", "status_code"]
)

HTTP_REQUEST_SIZE = safe_summary(
    "http_request_size_bytes", "Kích thước request HTTP", ["method", "endpoint"]
)

HTTP_RESPONSE_SIZE = safe_summary(
    "http_response_size_bytes",
    "Kích thước response HTTP",
    ["method", "endpoint", "status_code"],
)

# Database Metrics
DB_QUERY_LATENCY = safe_histogram(
    "db_query_latency_seconds",
    "Thời gian thực thi truy vấn DB",
    ["operation", "table"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

DB_QUERY_COUNT = safe_counter(
    "db_query_total", "Tổng số truy vấn DB", ["operation", "table"]
)

DB_ERROR_COUNT = safe_counter(
    "db_error_total", "Số lỗi DB", ["operation", "error_type"]
)

DB_CONNECTION_POOL_SIZE = safe_gauge(
    "db_connection_pool_size",
    "Kích thước connection pool",
    ["state"],  # idle, active, total
)

# Cache Metrics
CACHE_OPERATION_LATENCY = safe_histogram(
    "cache_operation_latency_seconds",
    "Thời gian thực hiện thao tác cache",
    ["operation", "cache_type"],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1],
)

CACHE_HIT_COUNT = safe_counter("cache_hit_total", "Số lần cache hit", ["cache_type"])

CACHE_MISS_COUNT = safe_counter("cache_miss_total", "Số lần cache miss", ["cache_type"])

# System Metrics
MEMORY_USAGE = safe_gauge(
    "memory_usage_bytes", "Mức sử dụng bộ nhớ", ["type"]  # used, total, available
)

CPU_USAGE = safe_gauge("cpu_usage_percent", "Mức sử dụng CPU", [])

OPEN_FILE_DESCRIPTORS = safe_gauge(
    "open_file_descriptors", "Số file descriptors đang mở", []
)

# Auth Metrics
AUTH_REQUEST_COUNT = safe_counter(
    "auth_request_total",
    "Số lần xác thực",
    ["status", "reason"],  # success/failure, reason
)

AUTH_TOKEN_CHECK_COUNT = safe_counter(
    "auth_token_check_total",
    "Số lần kiểm tra token",
    ["status"],  # valid/invalid/expired
)

# Security Metrics
SECURITY_EVENT_COUNT = safe_counter(
    "security_event_total", "Số sự kiện bảo mật", ["event_type", "severity"]
)

RATE_LIMIT_COUNT = safe_counter(
    "rate_limit_total", "Số lần rate limit", ["endpoint", "ip_prefix"]
)

SECURITY_BLOCK_COUNT = safe_counter(
    "security_block_total",
    "Số lần chặn yêu cầu do vấn đề bảo mật",
    ["reason", "source_ip_prefix"],
)

# Business Metrics
USER_ACTIVITY_COUNT = safe_counter(
    "user_activity_total", "Số hoạt động người dùng", ["action", "user_type"]
)

BOOK_ACTIVITY_COUNT = safe_counter(
    "book_activity_total", "Số hoạt động liên quan đến sách", ["action", "user_type"]
)

READING_SESSION_COUNT = safe_counter(
    "reading_session_total", "Số phiên đọc sách", ["device_type", "book_type"]
)

READING_SESSION_DURATION = safe_summary(
    "reading_session_duration_seconds",
    "Thời lượng phiên đọc sách",
    ["device_type", "book_type"],
)


# Metrics singleton class
class Metrics:
    """
    Quản lý việc thu thập và báo cáo metrics.

    Hỗ trợ:
    - Thu thập metrics từ nhiều nguồn khác nhau
    - Tracking request HTTP, truy vấn DB, thao tác cache
    - Đo lường hiệu suất hệ thống
    - Báo cáo metrics với Prometheus
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Metrics, cls).__new__(cls)
        return cls._instance

    def __init__(self, app_name: str = "api_readingbook"):
        # Khởi tạo chỉ một lần
        if hasattr(self, "initialized"):
            return

        self.app_name = app_name
        self.hostname = socket.gethostname()
        self.start_time = time.time()
        self.system_info = self._get_system_info()

        # Cấu hình metrics
        self.disabled_metrics = (
            settings.DISABLED_METRICS if hasattr(settings, "DISABLED_METRICS") else []
        )
        self.metric_samples = {}  # Lưu trữ các mẫu metrics
        self.sampling_enabled = (
            settings.METRICS_SAMPLING_ENABLED
            if hasattr(settings, "METRICS_SAMPLING_ENABLED")
            else True
        )

        # Prometheus exports
        self.exporter_type = (
            settings.METRICS_EXPORTER_TYPE
            if hasattr(settings, "METRICS_EXPORTER_TYPE")
            else "http"
        )
        self.exporter_interval = (
            settings.METRICS_EXPORT_INTERVAL
            if hasattr(settings, "METRICS_EXPORT_INTERVAL")
            else 15
        )
        self.exporter_thread = None
        self.exporter_running = False

        # Bắt đầu Prometheus exporter nếu được cấu hình
        if settings.METRICS_ENABLED if hasattr(settings, "METRICS_ENABLED") else True:
            self._start_exporter()

        self.initialized = True
        logger.info(f"Khởi tạo metrics collector '{app_name}' trên {self.hostname}")

    def _get_system_info(self) -> Dict[str, Any]:
        """Thu thập thông tin hệ thống."""
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(logical=True),
            "memory_total": psutil.virtual_memory().total,
        }

    def _start_exporter(self):
        """Khởi động Prometheus metrics exporter."""
        # Skip exporter initialization if metrics are explicitly disabled
        if not settings.METRICS_ENABLED:
            logger.info("Metrics disabled, skipping exporter initialization.")
            return

        try:
            if self.exporter_type == "http":
                # HTTP server exporter
                metrics_port = (
                    settings.METRICS_PORT if hasattr(settings, "METRICS_PORT") else 9090
                )

                # Only start HTTP server if PROMETHEUS_ENABLED is True
                if settings.PROMETHEUS_ENABLED:
                    start_http_server(metrics_port)
                    logger.info(
                        f"Started Prometheus HTTP server on port {metrics_port}"
                    )
                else:
                    logger.info(f"Prometheus HTTP server disabled by configuration")

            elif self.exporter_type == "push":
                # Pushgateway exporter
                if not hasattr(settings, "METRICS_PUSH_GATEWAY"):
                    logger.warning(
                        "METRICS_PUSH_GATEWAY không được cấu hình. Tắt push gateway."
                    )
                    return

                # Only start push gateway if enabled
                if settings.METRICS_ENABLED:
                    # Bắt đầu thread để push metrics
                    self.exporter_running = True
                    self.exporter_thread = threading.Thread(
                        target=self._push_metrics_loop
                    )
                    self.exporter_thread.daemon = True
                    self.exporter_thread.start()
                    logger.info(
                        f"Started Prometheus push gateway thread (interval: {self.exporter_interval}s)"
                    )
                else:
                    logger.info("Metrics disabled, skipping push gateway setup")

            else:
                logger.warning(f"Không hỗ trợ exporter type: {self.exporter_type}")

        except Exception as e:
            logger.error(f"Lỗi khi khởi động metrics exporter: {str(e)}")

    def _push_metrics_loop(self):
        """Thread loop để push metrics đến Prometheus gateway."""
        while self.exporter_running:
            try:
                push_to_gateway(
                    gateway=settings.METRICS_PUSH_GATEWAY,
                    job=self.app_name,
                    registry=None,  # Default registry
                    grouping_key={"instance": self.hostname},
                )
            except Exception as e:
                logger.error(f"Lỗi khi push metrics: {str(e)}")

            # Sleep until next push interval
            time.sleep(self.exporter_interval)

    def track_request(
        self, method: str, endpoint: str, status: int, duration: float, size: int
    ):
        """
        Theo dõi request HTTP.

        Args:
            method: Phương thức HTTP (GET, POST, etc.)
            endpoint: Endpoint API
            status: Status code
            duration: Thời gian xử lý (seconds)
            size: Kích thước response (bytes)
        """
        if MetricsCategory.HTTP in self.disabled_metrics:
            return

        # Histogram for latency
        HTTP_REQUEST_LATENCY.labels(
            method=method, endpoint=endpoint, status_code=str(status)
        ).observe(duration)

        # Counter for requests
        HTTP_REQUEST_COUNT.labels(
            method=method, endpoint=endpoint, status_code=str(status)
        ).inc()

        # Response size
        HTTP_RESPONSE_SIZE.labels(
            method=method, endpoint=endpoint, status_code=str(status)
        ).observe(size)

    def track_db_query(self, operation: str, table: str, duration: float):
        """
        Theo dõi truy vấn DB.

        Args:
            operation: Loại truy vấn (SELECT, INSERT, etc.)
            table: Tên bảng
            duration: Thời gian thực thi (seconds)
        """
        if MetricsCategory.DATABASE in self.disabled_metrics:
            return

        # Histogram for latency
        DB_QUERY_LATENCY.labels(operation=operation, table=table).observe(duration)

        # Counter for queries
        DB_QUERY_COUNT.labels(operation=operation, table=table).inc()

    def track_db_error(self, operation: str, error_type: str):
        """
        Theo dõi lỗi DB.

        Args:
            operation: Loại truy vấn gây lỗi
            error_type: Loại lỗi
        """
        if MetricsCategory.DATABASE in self.disabled_metrics:
            return

        # Counter for DB errors
        DB_ERROR_COUNT.labels(operation=operation, error_type=error_type).inc()

    def track_cache_operation(
        self, operation: str, cache_type: str, hit: bool, duration: float
    ):
        """
        Theo dõi thao tác cache.

        Args:
            operation: Thao tác (get, set, delete, etc.)
            cache_type: Loại cache (redis, memory, etc.)
            hit: Có tìm thấy trong cache hay không
            duration: Thời gian thực thi (seconds)
        """
        if MetricsCategory.CACHE in self.disabled_metrics:
            return

        # Histogram for latency
        CACHE_OPERATION_LATENCY.labels(
            operation=operation, cache_type=cache_type
        ).observe(duration)

        # Counter for hits/misses
        if operation == "get":
            if hit:
                CACHE_HIT_COUNT.labels(cache_type=cache_type).inc()
            else:
                CACHE_MISS_COUNT.labels(cache_type=cache_type).inc()

    def track_login(self, success: bool, reason: Optional[str] = None):
        """
        Theo dõi đăng nhập.

        Args:
            success: Đăng nhập thành công hay không
            reason: Lý do thất bại (nếu có)
        """
        if MetricsCategory.AUTH in self.disabled_metrics:
            return

        status = "success" if success else "failure"
        reason = reason or "unknown"

        # Counter for auth requests
        AUTH_REQUEST_COUNT.labels(status=status, reason=reason).inc()

    def track_token_validation(self, status: str):
        """
        Theo dõi kiểm tra token.

        Args:
            status: Trạng thái token (valid, invalid, expired)
        """
        if MetricsCategory.AUTH in self.disabled_metrics:
            return

        # Counter for token checks
        AUTH_TOKEN_CHECK_COUNT.labels(status=status).inc()

    def track_user_activity(self, action: str, user_type: str = "registered"):
        """
        Theo dõi hoạt động người dùng.

        Args:
            action: Loại hoạt động
            user_type: Loại người dùng
        """
        if MetricsCategory.BUSINESS in self.disabled_metrics:
            return

        # Counter for user activities
        USER_ACTIVITY_COUNT.labels(action=action, user_type=user_type).inc()

    def track_book_activity(
        self,
        action: str,
        book_id: str,
        user_type: str = "registered",
        rating: Optional[int] = None,
    ):
        """
        Theo dõi hoạt động liên quan đến sách.

        Args:
            action: Loại hoạt động (view, rate, review, etc.)
            book_id: ID sách
            user_type: Loại người dùng
            rating: Đánh giá (nếu có)
        """
        if MetricsCategory.BUSINESS in self.disabled_metrics:
            return

        # Counter for book activities
        BOOK_ACTIVITY_COUNT.labels(action=action, user_type=user_type).inc()

    def track_reading_session(self, device_type: str, duration: float, book_type: str):
        """
        Theo dõi phiên đọc sách.

        Args:
            device_type: Loại thiết bị
            duration: Thời lượng (seconds)
            book_type: Loại sách
        """
        if MetricsCategory.BUSINESS in self.disabled_metrics:
            return

        # Counter for session count
        READING_SESSION_COUNT.labels(device_type=device_type, book_type=book_type).inc()

        # Summary for session duration
        READING_SESSION_DURATION.labels(
            device_type=device_type, book_type=book_type
        ).observe(duration)

    def track_security_event(
        self,
        event_type: str,
        severity: str = "medium",
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Theo dõi sự kiện bảo mật.

        Args:
            event_type: Loại sự kiện bảo mật
            severity: Mức độ nghiêm trọng
            details: Chi tiết sự kiện
        """
        if MetricsCategory.SECURITY in self.disabled_metrics:
            return

        # Counter for security events
        SECURITY_EVENT_COUNT.labels(event_type=event_type, severity=severity).inc()

        # Log chi tiết sự kiện nếu mức độ cao
        if severity in ["high", "critical"]:
            event_id = str(uuid.uuid4())
            logger.warning(
                f"Security event [{event_id}]: {event_type} (severity: {severity})"
            )
            if details:
                # Ẩn thông tin nhạy cảm
                sanitized_details = self._sanitize_sensitive_data(details)
                logger.warning(
                    f"Security event details [{event_id}]: {json.dumps(sanitized_details)}"
                )

    def track_rate_limit(self, endpoint: str, ip_address: str):
        """
        Theo dõi rate limit.

        Args:
            endpoint: Endpoint bị rate limit
            ip_address: Địa chỉ IP
        """
        if MetricsCategory.SECURITY in self.disabled_metrics:
            return

        # Lấy prefix IP (che giấu địa chỉ cụ thể)
        ip_prefix = self._get_ip_prefix(ip_address)

        # Counter for rate limits
        RATE_LIMIT_COUNT.labels(endpoint=endpoint, ip_prefix=ip_prefix).inc()

    def track_security_block(self, reason: str, ip_address: str):
        """
        Ghi nhận sự kiện chặn bảo mật.

        Args:
            reason: Lý do chặn
            ip_address: Địa chỉ IP bị chặn
        """
        if not settings.METRICS_ENABLED:
            return

        ip_prefix = self._get_ip_prefix(ip_address)
        SECURITY_BLOCK_COUNT.labels(reason=reason, source_ip_prefix=ip_prefix).inc()

    def record_endpoint_error(self, endpoint: str, error_type: str):
        """
        Ghi nhận lỗi endpoint cho API profiler.

        Args:
            endpoint: Tên endpoint
            error_type: Loại lỗi
        """
        # Chỉ ghi log mà không tạo metrics nếu metrics bị tắt
        logger.error(f"API Error trong endpoint {endpoint}: {error_type}")

        if not settings.METRICS_ENABLED:
            return

        try:
            # Có thể sử dụng HTTP_REQUEST_COUNT với status 5xx
            parts = endpoint.split()
            if len(parts) > 1:
                method, path = parts[0], " ".join(parts[1:])
            else:
                method, path = "UNKNOWN", endpoint

            HTTP_REQUEST_COUNT.labels(
                method=method, endpoint=path, status_code="500"
            ).inc()
        except Exception as e:
            logger.error(f"Lỗi khi ghi nhận endpoint error: {e}")

    def update_system_metrics(
        self, memory_data: Dict[str, float], cpu_percent: float, num_fds: int
    ):
        """
        Cập nhật metrics hệ thống.

        Args:
            memory_data: Thông tin bộ nhớ
            cpu_percent: Phần trăm CPU
            num_fds: Số file descriptors
        """
        if MetricsCategory.SYSTEM in self.disabled_metrics:
            return

        # Memory metrics
        for mem_type, value in memory_data.items():
            MEMORY_USAGE.labels(type=mem_type).set(value)

        # CPU usage
        CPU_USAGE.set(cpu_percent)

        # Open file descriptors
        OPEN_FILE_DESCRIPTORS.set(num_fds)

    def collect_system_metrics(self):
        """Thu thập metrics về hệ thống hiện tại."""
        try:
            # Bộ nhớ
            memory = psutil.virtual_memory()
            memory_data = {
                "used": memory.used,
                "total": memory.total,
                "available": memory.available,
            }

            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # File descriptors (Unix only)
            if hasattr(psutil, "Process"):
                process = psutil.Process(os.getpid())
                if hasattr(process, "num_fds"):
                    num_fds = process.num_fds()
                else:
                    num_fds = 0
            else:
                num_fds = 0

            # Cập nhật metrics
            self.update_system_metrics(memory_data, cpu_percent, num_fds)
        except Exception as e:
            logger.error(f"Lỗi khi thu thập system metrics: {str(e)}")

    def update_db_pool_metrics(self, idle: int, active: int, total: int):
        """
        Cập nhật metrics về connection pool.

        Args:
            idle: Số connections đang chờ
            active: Số connections đang active
            total: Tổng số connections
        """
        if MetricsCategory.DATABASE in self.disabled_metrics:
            return

        # Set gauge values
        DB_CONNECTION_POOL_SIZE.labels(state="idle").set(idle)
        DB_CONNECTION_POOL_SIZE.labels(state="active").set(active)
        DB_CONNECTION_POOL_SIZE.labels(state="total").set(total)

    def update_cache_size(self, cache_type: str, size_bytes: int):
        """
        Cập nhật metrics kích thước cache.

        Args:
            cache_type: Loại cache
            size_bytes: Kích thước (bytes)
        """
        if MetricsCategory.CACHE in self.disabled_metrics:
            return

        # No built-in Prometheus metric for this, use custom metric
        if "cache_size" not in self.metric_samples:
            self.metric_samples["cache_size"] = {}

        self.metric_samples["cache_size"][cache_type] = size_bytes

    def time_request(self, method: str, endpoint: str):
        """
        Context manager để đo thời gian request.

        Args:
            method: Phương thức HTTP
            endpoint: Endpoint API

        Returns:
            Timer context manager
        """

        class Timer:
            def __init__(self, metrics, method, endpoint):
                self.metrics = metrics
                self.method = method
                self.endpoint = endpoint
                self.start_time = None
                self.status_code = 200  # Default
                self.response_size = 0

            def __enter__(self):
                self.start_time = time.time()
                return self

            def set_status_code(self, status_code):
                self.status_code = status_code

            def set_response_size(self, size):
                self.response_size = size

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - self.start_time
                self.metrics.track_request(
                    method=self.method,
                    endpoint=self.endpoint,
                    status=self.status_code,
                    duration=duration,
                    size=self.response_size,
                )

        return Timer(self, method, endpoint)

    def time_db_query(self, operation: str, table: str):
        """
        Context manager để đo thời gian truy vấn DB.

        Args:
            operation: Loại truy vấn
            table: Tên bảng

        Returns:
            Timer context manager
        """

        class Timer:
            def __init__(self, metrics, operation, table):
                self.metrics = metrics
                self.operation = operation
                self.table = table
                self.start_time = None

            def __enter__(self):
                self.start_time = time.time()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - self.start_time

                # Track DB error if exception occurred
                if exc_type is not None:
                    error_type = exc_type.__name__
                    self.metrics.track_db_error(
                        operation=self.operation, error_type=error_type
                    )

                # Track DB query time
                self.metrics.track_db_query(
                    operation=self.operation, table=self.table, duration=duration
                )

        return Timer(self, operation, table)

    def time_cache_operation(self, operation: str, cache_type: str):
        """
        Context manager để đo thời gian thao tác cache.

        Args:
            operation: Thao tác cache
            cache_type: Loại cache

        Returns:
            Timer context manager
        """

        class Timer:
            def __init__(self, metrics, operation, cache_type):
                self.metrics = metrics
                self.operation = operation
                self.cache_type = cache_type
                self.start_time = None
                self.hit = False

            def __enter__(self):
                self.start_time = time.time()
                return self

            def set_hit(self, hit: bool):
                """Đánh dấu cache hit/miss"""
                self.hit = hit

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - self.start_time

                # Track cache operation
                self.metrics.track_cache_operation(
                    operation=self.operation,
                    cache_type=self.cache_type,
                    hit=self.hit,
                    duration=duration,
                )

        return Timer(self, operation, cache_type)

    def _sanitize_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Làm sạch dữ liệu nhạy cảm từ dictionary.

        Args:
            data: Dictionary dữ liệu

        Returns:
            Dictionary đã được làm sạch
        """
        if not isinstance(data, dict):
            return data

        sensitive_fields = [
            "password",
            "token",
            "secret",
            "key",
            "credential",
            "auth",
            "session",
            "cookie",
            "jwt",
        ]

        sanitized = {}
        for key, value in data.items():
            if any(field in key.lower() for field in sensitive_fields):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_sensitive_data(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    (
                        self._sanitize_sensitive_data(item)
                        if isinstance(item, dict)
                        else item
                    )
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    def _get_ip_prefix(self, ip_address: str) -> str:
        """
        Lấy IP prefix để bảo vệ quyền riêng tư.

        Args:
            ip_address: Địa chỉ IP đầy đủ

        Returns:
            IP prefix
        """
        if ":" in ip_address:  # IPv6
            parts = ip_address.split(":")
            return ":".join(parts[:4]) + ":***"
        else:  # IPv4
            parts = ip_address.split(".")
            return ".".join(parts[:3]) + ".***"

    def get_metrics(self) -> Dict[str, Any]:
        """
        Lấy tất cả metrics đã thu thập.

        Returns:
            Dictionary chứa metrics
        """
        # Trong ứng dụng thực, chúng ta sẽ tích hợp với thư viện client Prometheus
        # để lấy tất cả metrics. Đây là phiên bản đơn giản.

        result = {
            "app_name": self.app_name,
            "hostname": self.hostname,
            "uptime_seconds": time.time() - self.start_time,
            "custom_metrics": self.metric_samples,
        }

        # Cập nhật system metrics realtime
        self.collect_system_metrics()

        return result


# Decorator để theo dõi thời gian request
def track_request_time(endpoint: str = None):
    """
    Decorator để theo dõi thời gian xử lý request.

    Args:
        endpoint: Tên endpoint. Nếu None, sẽ dùng tên function

    Returns:
        Decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Xác định endpoint
            request = None
            for arg in args:
                if hasattr(arg, "method") and hasattr(arg, "url"):
                    request = arg
                    break

            # Tạo endpoint
            actual_endpoint = endpoint
            if not actual_endpoint and request:
                actual_endpoint = request.url.path
            if not actual_endpoint:
                actual_endpoint = func.__name__

            # Lấy method
            method = request.method if request else "UNKNOWN"

            # Get metrics instance
            metrics_instance = Metrics()

            # Measure time
            timer = metrics_instance.time_request(method, actual_endpoint)
            with timer:
                try:
                    response = await func(*args, **kwargs)

                    # Set status code và response size
                    if hasattr(response, "status_code"):
                        timer.set_status_code(response.status_code)

                    # Estimate response size - actual implementation would use real value
                    if hasattr(response, "body"):
                        timer.set_response_size(len(response.body))

                    return response

                except Exception as e:
                    # Set error status code
                    timer.set_status_code(500)
                    raise e

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Xác định endpoint
            request = None
            for arg in args:
                if hasattr(arg, "method") and hasattr(arg, "url"):
                    request = arg
                    break

            # Tạo endpoint
            actual_endpoint = endpoint
            if not actual_endpoint and request:
                actual_endpoint = request.url.path
            if not actual_endpoint:
                actual_endpoint = func.__name__

            # Lấy method
            method = request.method if request else "UNKNOWN"

            # Get metrics instance
            metrics_instance = Metrics()

            # Measure time
            timer = metrics_instance.time_request(method, actual_endpoint)
            with timer:
                try:
                    response = func(*args, **kwargs)

                    # Set status code và response size
                    if hasattr(response, "status_code"):
                        timer.set_status_code(response.status_code)

                    # Estimate response size
                    if hasattr(response, "body"):
                        timer.set_response_size(len(response.body))

                    return response

                except Exception as e:
                    # Set error status code
                    timer.set_status_code(500)
                    raise e

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Decorator để theo dõi thời gian truy vấn DB
def track_db_query_time(operation: str, table: str):
    """
    Decorator để theo dõi thời gian truy vấn DB.

    Args:
        operation: Loại truy vấn
        table: Tên bảng

    Returns:
        Decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get metrics instance
            metrics_instance = Metrics()

            # Measure time
            with metrics_instance.time_db_query(operation, table):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get metrics instance
            metrics_instance = Metrics()

            # Measure time
            with metrics_instance.time_db_query(operation, table):
                return func(*args, **kwargs)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Decorator để theo dõi thời gian thao tác cache
def track_cache_operation_time(operation: str, cache_type: str):
    """
    Decorator để theo dõi thời gian thao tác cache.

    Args:
        operation: Thao tác cache
        cache_type: Loại cache

    Returns:
        Decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get metrics instance
            metrics_instance = Metrics()

            # Measure time
            with metrics_instance.time_cache_operation(operation, cache_type) as timer:
                result = await func(*args, **kwargs)
                # Assume cache hit if result is not None (for get operations)
                if operation == "get":
                    timer.set_hit(result is not None)
                return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get metrics instance
            metrics_instance = Metrics()

            # Measure time
            with metrics_instance.time_cache_operation(operation, cache_type) as timer:
                result = func(*args, **kwargs)
                # Assume cache hit if result is not None (for get operations)
                if operation == "get":
                    timer.set_hit(result is not None)
                return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Singleton instance
metrics = Metrics()


class AppMetricsCollector:
    """
    Thu thập metrics về hiệu suất ứng dụng.
    """

    def __init__(self):
        """Khởi tạo collector."""
        global _app_metrics_initialized

        # Ensure this is always disabled in this run to avoid errors
        settings.PROMETHEUS_ENABLED = False
        self.enabled = False  # Force disable to avoid errors
        self.collection_interval = getattr(
            settings, "APP_METRICS_COLLECTION_INTERVAL", 15
        )
        self.process = psutil.Process(os.getpid())
        self.collection_thread = None
        self.stop_event = threading.Event()

        # Chỉ log một lần để tránh trùng lặp
        if not _app_metrics_initialized:
            logger.info(
                f"Khởi tạo AppMetricsCollector, enabled={self.enabled}, interval={self.collection_interval}s"
            )
            _app_metrics_initialized = True

    def start(self):
        """Bắt đầu thu thập metrics tự động."""
        # Always skip collection to avoid errors
        logger.debug("AppMetricsCollector đã bị tắt, không bắt đầu thu thập")
        return

    def stop(self):
        """Dừng thu thập metrics tự động."""
        if self.collection_thread is None or not self.collection_thread.is_alive():
            return

        # Set stop event
        self.stop_event.set()

        # Đợi thread kết thúc
        self.collection_thread.join(timeout=5)

        # Reset
        self.collection_thread = None

        logger.info("Đã dừng thu thập metrics ứng dụng")

    def _collection_loop(self):
        """Loop thu thập metrics."""
        try:
            while not self.stop_event.is_set():
                # Thu thập metrics
                self.collect_metrics()

                # Đợi interval
                self.stop_event.wait(self.collection_interval)

        except Exception as e:
            logger.error(f"Lỗi trong collection loop: {str(e)}")

    def collect_metrics(self):
        """Thu thập metrics hiện tại."""
        try:
            # Thu thập memory metrics
            memory_info = self.process.memory_info()
            memory_data = {"rss": memory_info.rss, "vms": memory_info.vms}

            # Thu thập CPU metrics
            cpu_percent = self.process.cpu_percent(interval=0.1)

            # Số lượng file descriptors
            try:
                num_fds = (
                    self.process.num_fds() if hasattr(self.process, "num_fds") else 0
                )
            except (AttributeError, NotImplementedError):
                num_fds = 0

            # Số lượng threads
            num_threads = self.process.num_threads()

            # Số lượng connections
            try:
                connections = len(self.process.connections())
            except (psutil.AccessDenied, NotImplementedError):
                connections = 0

            # Cập nhật system metrics
            metrics.update_system_metrics(memory_data, cpu_percent, num_fds)

            # Ghi log debug
            logger.debug(
                f"Metrics thu thập: CPU={cpu_percent}%, RSS={memory_info.rss/1024/1024:.2f}MB, "
                f"Threads={num_threads}, FDs={num_fds}, Connections={connections}"
            )

            return {
                "memory": memory_data,
                "cpu": cpu_percent,
                "num_fds": num_fds,
                "num_threads": num_threads,
                "connections": connections,
            }

        except Exception as e:
            logger.error(f"Lỗi khi thu thập metrics: {str(e)}")
            return {}


# Tạo singleton instance
app_metrics_collector = AppMetricsCollector()


def start_metrics_collection():
    """Bắt đầu thu thập metrics tự động."""
    app_metrics_collector.start()


def stop_metrics_collection():
    """Dừng thu thập metrics tự động."""
    app_metrics_collector.stop()


def collect_request_metrics():
    """Decorator để thu thập metrics cho API request."""

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Đo thời gian
            start_time = time.time()

            # Lấy request (thường là tham số đầu tiên trong FastAPI route)
            request = args[0] if args else None

            # Lấy thông tin method và path
            method = request.method if hasattr(request, "method") else "UNKNOWN"
            path = request.url.path if hasattr(request, "url") else "UNKNOWN"

            # Tăng request counter
            metrics.request_in_progress.labels(method=method).inc()

            try:
                # Gọi handler
                response = await func(*args, **kwargs)

                # Lấy status code
                status_code = (
                    response.status_code if hasattr(response, "status_code") else 200
                )

                # Lấy content length
                content_length = 0
                if (
                    hasattr(response, "headers")
                    and "content-length" in response.headers
                ):
                    content_length = int(response.headers["content-length"])
                elif hasattr(response, "body"):
                    content_length = len(response.body)

                # Ghi metrics
                metrics.track_request(
                    method, path, status_code, time.time() - start_time, content_length
                )

                return response

            except Exception as e:
                # Ghi metrics lỗi
                metrics.track_request(method, path, 500, time.time() - start_time, 0)

                # Re-raise exception
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Đo thời gian
            start_time = time.time()

            # Lấy request (thường là tham số đầu tiên trong FastAPI route)
            request = args[0] if args else None

            # Lấy thông tin method và path
            method = request.method if hasattr(request, "method") else "UNKNOWN"
            path = request.url.path if hasattr(request, "url") else "UNKNOWN"

            # Tăng request counter
            metrics.request_in_progress.labels(method=method).inc()

            try:
                # Gọi handler
                response = func(*args, **kwargs)

                # Lấy status code
                status_code = (
                    response.status_code if hasattr(response, "status_code") else 200
                )

                # Lấy content length
                content_length = 0
                if (
                    hasattr(response, "headers")
                    and "content-length" in response.headers
                ):
                    content_length = int(response.headers["content-length"])
                elif hasattr(response, "body"):
                    content_length = len(response.body)

                # Ghi metrics
                metrics.track_request(
                    method, path, status_code, time.time() - start_time, content_length
                )

                return response

            except Exception as e:
                # Ghi metrics lỗi
                metrics.track_request(method, path, 500, time.time() - start_time, 0)

                # Re-raise exception
                raise

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
