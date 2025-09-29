from typing import Dict, List, Any, Optional, Union, Set, Tuple
import time
import asyncio
import logging
import threading
from functools import wraps
from enum import Enum

# Import logger và settings một lần duy nhất
from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Biến singleton để theo dõi việc khởi tạo
_metrics_instance = None
_metrics_log_done = False

# Thử import Prometheus client, nếu không có thì tạo mock objects
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Summary,
        REGISTRY,
        CollectorRegistry,
        push_to_gateway,
    )
    from prometheus_client import start_http_server as start_prom_http_server

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning(
        "Prometheus client không được cài đặt. Metrics sẽ không được export."
    )

    # Tạo mock classes để tránh lỗi khi không có thư viện
    class MockMetric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def inc(self, amount=1):
            pass

        def dec(self, amount=1):
            pass

        def set(self, value):
            pass

        def observe(self, value):
            pass

    class Counter(MockMetric):
        pass

    class Gauge(MockMetric):
        pass

    class Histogram(MockMetric):
        pass

    class Summary(MockMetric):
        pass

    class CollectorRegistry:
        def __init__(self):
            pass

    def push_to_gateway(*args, **kwargs):
        pass

    def start_prom_http_server(*args, **kwargs):
        pass


class MetricsCategory(str, Enum):
    """Danh mục metrics."""

    HTTP = "http"
    DATABASE = "database"
    CACHE = "cache"
    SYSTEM = "system"
    BUSINESS = "business"
    AUTH = "auth"


class Metrics:
    """
    Metrics cho giám sát ứng dụng.
    Cung cấp:
    - HTTP metrics
    - Database metrics
    - Cache metrics
    - System metrics
    - Business metrics
    """

    def __init__(self, app_name: str = "api_readingbook"):
        """
        Khởi tạo metrics.

        Args:
            app_name: Tên ứng dụng
        """
        global _metrics_instance, _metrics_log_done

        # Singleton pattern - nếu đã khởi tạo, trả về instance hiện tại
        if _metrics_instance is not None:
            # Sao chép các thuộc tính từ instance hiện tại
            self.__dict__ = _metrics_instance.__dict__
            return

        self.app_name = app_name

        if not PROMETHEUS_AVAILABLE:
            logger.warning(
                "Prometheus client không có sẵn. Metrics sẽ chỉ được ghi log mà không được export."
            )

        self.registry = CollectorRegistry()

        # HTTP metrics
        self.request_counter = Counter(
            "http_requests_total",
            "Tổng số HTTP requests",
            ["method", "endpoint", "status"],
            registry=self.registry,
        )

        self.request_duration = Histogram(
            "http_request_duration_seconds",
            "Thời gian xử lý HTTP request",
            ["method", "endpoint"],
            buckets=(
                0.01,
                0.025,
                0.05,
                0.075,
                0.1,
                0.25,
                0.5,
                0.75,
                1.0,
                2.5,
                5.0,
                7.5,
                10.0,
                30.0,
                60.0,
                float("inf"),
            ),
            registry=self.registry,
        )

        self.request_in_progress = Gauge(
            "http_requests_in_progress",
            "Số lượng HTTP requests đang xử lý",
            ["method"],
            registry=self.registry,
        )

        self.response_size = Histogram(
            "http_response_size_bytes",
            "Kích thước phản hồi HTTP",
            ["method", "endpoint"],
            buckets=(100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000, float("inf")),
            registry=self.registry,
        )

        # Database metrics
        self.db_query_counter = Counter(
            "db_queries_total",
            "Tổng số truy vấn cơ sở dữ liệu",
            ["operation", "table"],
            registry=self.registry,
        )

        self.db_query_duration = Histogram(
            "db_query_duration_seconds",
            "Thời gian thực hiện truy vấn cơ sở dữ liệu",
            ["operation", "table"],
            buckets=(
                0.001,
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
                float("inf"),
            ),
            registry=self.registry,
        )

        self.db_error_counter = Counter(
            "db_errors_total",
            "Tổng số lỗi cơ sở dữ liệu",
            ["operation", "error_type"],
            registry=self.registry,
        )

        self.db_pool_connections = Gauge(
            "db_pool_connections",
            "Số lượng kết nối trong pool",
            ["state"],  # idle, active, total
            registry=self.registry,
        )

        # Cache metrics
        self.cache_hit_count = Counter(
            "cache_hits_total",
            "Tổng số cache hits",
            ["cache_type"],  # redis, memory, etc.
            registry=self.registry,
        )

        self.cache_miss_count = Counter(
            "cache_misses_total",
            "Tổng số cache misses",
            ["cache_type"],  # redis, memory, etc.
            registry=self.registry,
        )

        self.cache_request_duration = Histogram(
            "cache_request_duration_seconds",
            "Thời gian xử lý yêu cầu cache",
            ["operation", "cache_type"],  # get, set, etc.
            buckets=(
                0.0001,
                0.0005,
                0.001,
                0.0025,
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                float("inf"),
            ),
            registry=self.registry,
        )

        self.cache_size = Gauge(
            "cache_size_bytes",
            "Kích thước cache",
            ["cache_type"],
            registry=self.registry,
        )

        self.cache_invalidation_count = Counter(
            "cache_invalidations_total",
            "Tổng số vô hiệu hóa cache",
            ["reason"],  # api_call, ttl, manual, etc.
            registry=self.registry,
        )

        # System metrics
        self.memory_usage = Gauge(
            "memory_usage_bytes",
            "Sử dụng bộ nhớ",
            ["type"],  # total, rss, heap, stack
            registry=self.registry,
        )

        self.cpu_usage = Gauge(
            "cpu_usage_percent", "Phần trăm sử dụng CPU", registry=self.registry
        )

        self.process_startup_time = Gauge(
            "process_startup_time_seconds",
            "Thời gian khởi động quy trình UNIX",
            registry=self.registry,
        )

        self.open_file_descriptors = Gauge(
            "open_file_descriptors",
            "Số lượng file descriptors đang mở",
            registry=self.registry,
        )

        # Business metrics
        self.user_registrations = Counter(
            "user_registrations_total",
            "Tổng số đăng ký người dùng",
            registry=self.registry,
        )

        self.active_users = Gauge(
            "active_users", "Số lượng người dùng đang hoạt động", registry=self.registry
        )

        self.book_views = Counter(
            "book_views_total",
            "Tổng số lượt xem sách",
            ["book_id", "user_type"],  # user_type: guest, registered, premium
            registry=self.registry,
        )

        self.book_ratings = Counter(
            "book_ratings_total",
            "Tổng số đánh giá sách",
            ["rating"],  # 1, 2, 3, 4, 5
            registry=self.registry,
        )

        self.reading_sessions = Counter(
            "reading_sessions_total",
            "Tổng số phiên đọc",
            ["device_type"],
            registry=self.registry,
        )

        self.reading_time = Counter(
            "reading_time_seconds_total",
            "Tổng thời gian đọc",
            ["book_type"],  # fiction, non-fiction, etc.
            registry=self.registry,
        )

        # Authorization metrics
        self.login_attempts = Counter(
            "login_attempts_total",
            "Tổng số lần đăng nhập",
            ["status"],  # success, failure
            registry=self.registry,
        )

        self.failed_login_reasons = Counter(
            "failed_login_reasons_total",
            "Lý do đăng nhập thất bại",
            ["reason"],  # invalid_password, user_not_found, account_locked, etc.
            registry=self.registry,
        )

        self.token_validations = Counter(
            "token_validations_total",
            "Tổng số lần xác thực token",
            ["status"],  # valid, invalid, expired
            registry=self.registry,
        )

        # Khởi tạo
        self.process_startup_time.set(time.time())

        # Start và export metrics tự động nếu cần
        self._start_exporter()

        # Lưu singleton instance
        _metrics_instance = self

        # Chỉ log một lần để tránh trùng lặp
        if not _metrics_log_done:
            # Ghi log khởi tạo một lần duy nhất
            logger.info(f"Khởi tạo Metrics cho ứng dụng '{self.app_name}'")
            _metrics_log_done = True

    def _start_exporter(self):
        """Khởi động exporter metrics."""
        # Biến tĩnh để theo dõi trạng thái HTTP server
        if not hasattr(Metrics, "_http_server_started"):
            Metrics._http_server_started = False

        # Khởi động Prometheus HTTP server
        try:
            # Khởi tạo các biến cần thiết
            self.exporter_running = False
            self.exporter_interval = getattr(settings, "PROMETHEUS_PUSH_INTERVAL", 15)
            self._apm_client = None

            # Kiểm tra nếu Prometheus được bật
            if getattr(settings, "PROMETHEUS_ENABLED", False) and PROMETHEUS_AVAILABLE:
                prometheus_port = getattr(settings, "PROMETHEUS_PORT", 9090)

                # Chỉ khởi động HTTP server nếu chưa được khởi động
                if not Metrics._http_server_started:
                    start_prom_http_server(prometheus_port)
                    logger.info(
                        f"Prometheus HTTP server đã khởi động tại cổng {prometheus_port}"
                    )
                    Metrics._http_server_started = True
                else:
                    logger.debug(f"Prometheus HTTP server đã khởi động trước đó")

                # Khởi tạo push gateway nếu được cấu hình
                push_gateway = getattr(settings, "PROMETHEUS_PUSH_GATEWAY", None)
                if push_gateway:
                    # Khởi động thread riêng để push metrics
                    if not self.exporter_running:
                        self.exporter_running = True

                        def push_metrics():
                            while self.exporter_running:
                                try:
                                    push_to_gateway(
                                        push_gateway,
                                        job=self.app_name,
                                        registry=self.registry,
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to push metrics: {e}")
                                time.sleep(self.exporter_interval)

                        # Khởi động thread push metrics
                        self.exporter_thread = threading.Thread(
                            target=push_metrics, daemon=True
                        )
                        self.exporter_thread.start()
        except Exception as e:
            logger.error(f"Error starting metrics exporter: {e}")

    def track_request(
        self, method: str, endpoint: str, status: int, duration: float, size: int
    ):
        """
        Ghi metrics cho HTTP request.

        Args:
            method: HTTP method
            endpoint: Endpoint path
            status: HTTP status code
            duration: Thời gian xử lý (giây)
            size: Kích thước phản hồi (bytes)
        """
        try:
            self.request_counter.labels(
                method=method, endpoint=endpoint, status=status
            ).inc()
            self.request_duration.labels(method=method, endpoint=endpoint).observe(
                duration
            )
            self.response_size.labels(method=method, endpoint=endpoint).observe(size)

            # Thêm code mới - ghi log các request chậm
            try:
                slow_threshold = getattr(settings, "SLOW_REQUEST_THRESHOLD", 1.0)
                if duration > slow_threshold:
                    self.log_important_metric(
                        metric_type="slow_request_duration",
                        value=duration,
                        metadata={
                            "method": method,
                            "endpoint": endpoint,
                            "status": status,
                            "size": size,
                        },
                    )
            except (AttributeError, ValueError) as e:
                # Bỏ qua nếu SLOW_REQUEST_THRESHOLD không tồn tại
                logger.debug(f"Không thể kiểm tra slow request: {e}")
        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho request: {str(e)}")

    def track_db_query(self, operation: str, table: str, duration: float):
        """
        Ghi metrics cho truy vấn cơ sở dữ liệu.

        Args:
            operation: Loại truy vấn (SELECT, INSERT, etc.)
            table: Tên bảng
            duration: Thời gian thực hiện (giây)
        """
        try:
            self.db_query_counter.labels(operation=operation, table=table).inc()
            self.db_query_duration.labels(operation=operation, table=table).observe(
                duration
            )
        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho truy vấn DB: {str(e)}")

    def track_db_error(self, operation: str, error_type: str):
        """
        Ghi metrics cho lỗi cơ sở dữ liệu.

        Args:
            operation: Loại truy vấn (SELECT, INSERT, etc.)
            error_type: Loại lỗi
        """
        try:
            self.db_error_counter.labels(
                operation=operation, error_type=error_type
            ).inc()
        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho lỗi DB: {str(e)}")

    def track_cache_operation(
        self, operation: str, cache_type: str, hit: bool, duration: float
    ):
        """
        Ghi metrics cho thao tác cache.

        Args:
            operation: Loại thao tác (get, set, etc.)
            cache_type: Loại cache (redis, memory, etc.)
            hit: True nếu cache hit, False nếu miss
            duration: Thời gian thực hiện (giây)
        """
        try:
            if hit:
                self.cache_hit_count.labels(cache_type=cache_type).inc()
            else:
                self.cache_miss_count.labels(cache_type=cache_type).inc()

            self.cache_request_duration.labels(
                operation=operation, cache_type=cache_type
            ).observe(duration)
        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho thao tác cache: {str(e)}")

    def track_login(self, success: bool, reason: Optional[str] = None):
        """
        Ghi metrics cho đăng nhập.

        Args:
            success: True nếu đăng nhập thành công
            reason: Lý do đăng nhập thất bại
        """
        try:
            status = "success" if success else "failure"
            self.login_attempts.labels(status=status).inc()

            if not success and reason:
                self.failed_login_reasons.labels(reason=reason).inc()

        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho đăng nhập: {str(e)}")

    def track_token_validation(self, status: str):
        """
        Ghi metrics cho xác thực token.

        Args:
            status: Trạng thái token (valid, invalid, expired)
        """
        try:
            self.token_validations.labels(status=status).inc()
        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho xác thực token: {str(e)}")

    def track_user_activity(self, action: str, user_type: str = "registered"):
        """
        Ghi metrics cho hoạt động người dùng.

        Args:
            action: Loại hoạt động
            user_type: Loại người dùng
        """
        try:
            if action == "register":
                self.user_registrations.inc()
            elif action == "login":
                self.active_users.inc()
            elif action == "logout":
                self.active_users.dec()
        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho hoạt động người dùng: {str(e)}")

    def track_book_activity(
        self,
        action: str,
        book_id: str,
        user_type: str = "registered",
        rating: Optional[int] = None,
    ):
        """
        Ghi metrics cho hoạt động đọc sách.

        Args:
            action: Loại hoạt động (view, rate, etc.)
            book_id: ID sách
            user_type: Loại người dùng
            rating: Đánh giá (1-5)
        """
        try:
            if action == "view":
                self.book_views.labels(book_id=book_id, user_type=user_type).inc()
            elif action == "rate" and rating:
                self.book_ratings.labels(rating=str(rating)).inc()
        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho hoạt động đọc sách: {str(e)}")

    def track_reading_session(self, device_type: str, duration: float, book_type: str):
        """
        Ghi metrics cho phiên đọc.

        Args:
            device_type: Loại thiết bị
            duration: Thời gian đọc (giây)
            book_type: Loại sách
        """
        try:
            self.reading_sessions.labels(device_type=device_type).inc()
            self.reading_time.labels(book_type=book_type).inc(duration)
        except Exception as e:
            logger.error(f"Lỗi khi ghi metrics cho phiên đọc: {str(e)}")

    def update_system_metrics(
        self, memory_data: Dict[str, float], cpu_percent: float, num_fds: int
    ):
        """
        Cập nhật system metrics.

        Args:
            memory_data: Dữ liệu sử dụng bộ nhớ
            cpu_percent: Phần trăm sử dụng CPU
            num_fds: Số lượng file descriptors
        """
        try:
            # Cập nhật memory metrics
            for mem_type, value in memory_data.items():
                self.memory_usage.labels(type=mem_type).set(value)

            # Cập nhật CPU usage
            self.cpu_usage.set(cpu_percent)

            # Cập nhật file descriptors
            self.open_file_descriptors.set(num_fds)
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật system metrics: {str(e)}")

    def update_db_pool_metrics(self, idle: int, active: int, total: int):
        """
        Cập nhật metrics cho connection pool.

        Args:
            idle: Số kết nối idle
            active: Số kết nối active
            total: Tổng số kết nối
        """
        try:
            # Cập nhật gauge cho từng trạng thái
            self.db_pool_connections.labels(state="idle").set(idle)
            self.db_pool_connections.labels(state="active").set(active)
            self.db_pool_connections.labels(state="total").set(total)
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật metrics cho DB pool: {str(e)}")

    def update_cache_size(self, cache_type: str, size_bytes: int):
        """
        Cập nhật kích thước cache.

        Args:
            cache_type: Loại cache (redis, memory, etc.)
            size_bytes: Kích thước cache (bytes)
        """
        try:
            self.cache_size.labels(cache_type=cache_type).set(size_bytes)
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật kích thước cache: {str(e)}")

    def time_request(self, method: str, endpoint: str):
        """
        Context manager để đo thời gian xử lý request.

        Args:
            method: HTTP method
            endpoint: Endpoint path

        Returns:
            Context manager
        """

        class Timer:
            def __init__(self, metrics, method, endpoint):
                self.metrics = metrics
                self.method = method
                self.endpoint = endpoint
                self.start_time = None

            def __enter__(self):
                self.start_time = time.time()
                self.metrics.request_in_progress.labels(method=self.method).inc()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - self.start_time
                self.metrics.request_in_progress.labels(method=self.method).dec()
                # Không ghi duration ở đây, vì còn thiếu status và size
                # Được ghi bởi track_request sau này

        return Timer(self, method, endpoint)

    def time_db_query(self, operation: str, table: str):
        """
        Context manager để đo thời gian thực hiện truy vấn DB.

        Args:
            operation: Loại truy vấn (SELECT, INSERT, etc.)
            table: Tên bảng

        Returns:
            Context manager
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

                if exc_type is not None:
                    # Có lỗi xảy ra
                    error_type = exc_type.__name__
                    self.metrics.track_db_error(self.operation, error_type)
                else:
                    # Truy vấn thành công
                    self.metrics.track_db_query(self.operation, self.table, duration)

        return Timer(self, operation, table)

    def time_cache_operation(self, operation: str, cache_type: str):
        """
        Context manager để đo thời gian thực hiện thao tác cache.

        Args:
            operation: Loại thao tác (get, set, etc.)
            cache_type: Loại cache (redis, memory, etc.)

        Returns:
            Context manager
        """

        class Timer:
            def __init__(self, metrics, operation, cache_type):
                self.metrics = metrics
                self.operation = operation
                self.cache_type = cache_type
                self.start_time = None
                self.hit = None

            def __enter__(self):
                self.start_time = time.time()
                return self

            def set_hit(self, hit: bool):
                # Đánh dấu cache hit/miss
                self.hit = hit

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - self.start_time

                if exc_type is None and self.hit is not None:
                    # Thao tác thành công và đã đánh dấu hit/miss
                    self.metrics.track_cache_operation(
                        self.operation, self.cache_type, self.hit, duration
                    )

        return Timer(self, operation, cache_type)

    def create_span_from_metrics(
        self, name: str, operation: str, attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Tạo span từ metrics operation để tích hợp với tracing.

        Args:
            name: Tên span
            operation: Loại operation
            attributes: Thuộc tính bổ sung

        Returns:
            Context manager tương thích với các span từ tracing
        """
        # Import tracer từ module tracing
        try:
            from app.monitoring.tracing import tracer

            # Tạo span attributes từ metrics
            span_attributes = attributes or {}
            span_attributes.update(
                {"metrics.operation": operation, "metrics.source": self.app_name}
            )

            # Tạo span từ tracer
            return tracer.create_span(name=name, attributes=span_attributes)
        except ImportError:
            # Nếu không có tracing, tạo dummy context manager
            class DummySpan:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass

                def set_attribute(self, key, value):
                    pass

            return DummySpan()

    def capture_apm_metric(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ):
        """
        Capture metric cho APM.

        Args:
            name: Tên metric
            value: Giá trị metric
            tags: Tags cho metric
        """
        try:
            from app.monitoring.apm import apm_agent

            apm_agent.custom_metric(name, value, tags)
        except (ImportError, AttributeError):
            # Bỏ qua nếu không có APM hoặc method không tồn tại
            pass

    def log_important_metric(
        self, metric_type: str, value: float, metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Ghi log một metric quan trọng.

        Args:
            metric_type: Loại metric
            value: Giá trị metric
            metadata: Thông tin bổ sung
        """
        if metadata is None:
            metadata = {}

        # Thêm metadata cơ bản
        metadata.update(
            {
                "app_name": self.app_name,
                "metric_type": metric_type,
                "value": value,
                "time": time.time(),
            }
        )

        # Kiểm tra nếu có thể gửi đến APM system
        if hasattr(self, "_apm_client") and self._apm_client:
            try:
                self._apm_client.capture_metric(
                    f"{metric_type}.value", value, metadata=metadata
                )
            except Exception as e:
                logger.error(f"Lỗi khi gửi metric đến APM: {str(e)}")

        # Ghi log quan trọng
        try:
            log_structured = getattr(settings, "LOG_STRUCTURED", False)
            if log_structured:
                # Log dưới dạng structured
                log_data = {
                    "message": f"Important metric: {metric_type}",
                    "metric_type": metric_type,
                    "value": value,
                    **metadata,
                }

                # Sử dụng asyncio để tránh chặn luồng chính
                try:
                    if asyncio.get_event_loop().is_running():
                        self._log_info_async(log_data)
                    else:
                        logger.info(log_data)
                except (RuntimeError, ValueError) as e:
                    # Không có event loop hoặc đã đóng
                    logger.info(log_data)
            else:
                # Log dưới dạng text
                metadata_str = ", ".join(f"{k}={v}" for k, v in metadata.items())
                logger.info(
                    f"Important metric: {metric_type} = {value} ({metadata_str})"
                )
        except Exception as e:
            logger.error(f"Lỗi khi ghi log metric: {str(e)}")

    def _log_info_async(self, log_data):
        """Tạo task bất đồng bộ để ghi log."""
        try:
            asyncio.create_task(self._log_async(log_data))
        except Exception as e:
            logger.error(f"Lỗi khi tạo task log bất đồng bộ: {str(e)}")
            # Fallback to sync logging
            logger.info(log_data)

    async def _log_async(self, log_data):
        """Ghi log bất đồng bộ."""
        try:
            logger.info(log_data)
        except Exception as e:
            logger.error(f"Lỗi khi ghi log bất đồng bộ: {str(e)}")


# Tạo singleton instance
metrics = Metrics()

# Export for use in other modules
__all__ = ["Metrics", "metrics", "MetricsCategory"]


# Decorators tiện ích
def track_request_time(endpoint: str = None):
    """
    Decorator để đo thời gian xử lý request.

    Args:
        endpoint: Endpoint path (mặc định lấy từ tên function)

    Returns:
        Decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Xác định endpoint
            _endpoint = endpoint
            if _endpoint is None:
                _endpoint = func.__name__

            # Lấy request object (thường là tham số đầu tiên trong FastAPI route)
            request = args[0] if args else None
            method = request.method if hasattr(request, "method") else "UNKNOWN"

            # Đo thời gian
            with metrics.time_request(method, _endpoint) as timer:
                # Gọi function
                response = await func(*args, **kwargs)

                # Lấy status và size
                status = getattr(response, "status_code", 200)

                # Ước tính kích thước phản hồi
                size = 0
                if hasattr(response, "body"):
                    size = len(response.body)
                elif hasattr(response, "render"):
                    # Template response
                    size = len(response.render())
                elif hasattr(response, "__len__"):
                    size = len(response)

                # Ghi metrics
                metrics.track_request(
                    method, _endpoint, status, time.time() - timer.start_time, size
                )

            return response

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Xác định endpoint
            _endpoint = endpoint
            if _endpoint is None:
                _endpoint = func.__name__

            # Lấy request object (thường là tham số đầu tiên trong FastAPI route)
            request = args[0] if args else None
            method = request.method if hasattr(request, "method") else "UNKNOWN"

            # Đo thời gian
            with metrics.time_request(method, _endpoint) as timer:
                # Gọi function
                response = func(*args, **kwargs)

                # Lấy status và size
                status = getattr(response, "status_code", 200)

                # Ước tính kích thước phản hồi
                size = 0
                if hasattr(response, "body"):
                    size = len(response.body)
                elif hasattr(response, "render"):
                    # Template response
                    size = len(response.render())
                elif hasattr(response, "__len__"):
                    size = len(response)

                # Ghi metrics
                metrics.track_request(
                    method, _endpoint, status, time.time() - timer.start_time, size
                )

            return response

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def track_db_query_time(operation: str, table: str):
    """
    Decorator để đo thời gian thực hiện truy vấn DB.

    Args:
        operation: Loại truy vấn (SELECT, INSERT, etc.)
        table: Tên bảng

    Returns:
        Decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with metrics.time_db_query(operation, table):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with metrics.time_db_query(operation, table):
                return func(*args, **kwargs)

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def track_cache_operation_time(operation: str, cache_type: str):
    """
    Decorator để đo thời gian thực hiện thao tác cache.

    Args:
        operation: Loại thao tác (get, set, etc.)
        cache_type: Loại cache (redis, memory, etc.)

    Returns:
        Decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with metrics.time_cache_operation(operation, cache_type) as timer:
                result = await func(*args, **kwargs)

                # Đánh dấu cache hit/miss (cho thao tác get)
                if operation == "get":
                    timer.set_hit(result is not None)

                return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with metrics.time_cache_operation(operation, cache_type) as timer:
                result = func(*args, **kwargs)

                # Đánh dấu cache hit/miss (cho thao tác get)
                if operation == "get":
                    timer.set_hit(result is not None)

                return result

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Hàm tiện ích để track các loại request khác nhau


def track_auth_request(user_id: Optional[int], success: bool, auth_type: str):
    """
    Theo dõi yêu cầu xác thực.

    Args:
        user_id: ID người dùng (nếu có)
        success: Thành công hay thất bại
        auth_type: Loại xác thực (password, token, social, etc.)
    """
    from app.monitoring.metrics import metrics

    status = "success" if success else "failure"

    if hasattr(metrics, "auth_requests"):
        metrics.auth_requests.labels(auth_type=auth_type, status=status).inc()

    # Log thông tin xác thực
    log_data = {
        "user_id": user_id,
        "auth_type": auth_type,
        "success": success,
        "time": time.time(),
    }

    if not success:
        logger.warning(f"Auth request failed: {auth_type}", extra=log_data)
    else:
        logger.debug(f"Auth request success: {auth_type}", extra=log_data)


def track_request_duration(endpoint: str, duration: float):
    """
    Theo dõi thời gian xử lý request.

    Args:
        endpoint: Endpoint của request
        duration: Thời gian xử lý (giây)
    """
    from app.monitoring.metrics import metrics

    try:
        # Observe vào histogram
        metrics.request_duration.labels(method="*", endpoint=endpoint).observe(duration)

        # Ghi log nếu request quá chậm
        slow_threshold = getattr(settings, "SLOW_REQUEST_THRESHOLD", 1.0)
        if duration > slow_threshold:
            logger.warning(
                f"Slow request to {endpoint}: {duration:.2f}s (threshold: {slow_threshold}s)"
            )
    except Exception as e:
        logger.error(f"Lỗi khi theo dõi thời gian xử lý request: {str(e)}")


def track_login(success: bool, provider: str = None, reason: str = None):
    """
    Theo dõi đăng nhập.

    Args:
        success: Thành công hay thất bại
        provider: Nhà cung cấp xác thực (nếu là social login)
        reason: Lý do thất bại (nếu thất bại)
    """
    from app.monitoring.metrics import metrics

    # Đăng ký metrics nếu chưa có
    if not hasattr(metrics, "logins"):
        from prometheus_client import Counter

        metrics.logins = Counter(
            "logins_total",
            "Tổng số lần đăng nhập",
            ["status", "provider"],
            registry=metrics.registry,
        )

    status = "success" if success else "failure"
    provider = provider or "password"

    # Tăng counter
    metrics.logins.labels(status=status, provider=provider).inc()

    # Log thông tin đăng nhập
    log_data = {
        "success": success,
        "provider": provider,
        "reason": reason,
        "time": time.time(),
    }

    if not success:
        logger.warning(f"Login failed via {provider}: {reason}", extra=log_data)
    else:
        logger.info(f"Login success via {provider}", extra=log_data)
