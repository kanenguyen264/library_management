"""
Metrics module for tracking application performance and business metrics.
"""

import logging
import time
from typing import Optional, Dict, Any, Callable
from functools import wraps

# Import settings
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Biến để theo dõi việc khởi tạo
_metrics_initialized = False

# Get settings once
settings = get_settings()

# Import the main Metrics class
try:
    from app.monitoring.metrics.metrics import metrics, Metrics
except ImportError as e:
    logger.warning(f"Could not import metrics: {e}")
    metrics = None

    # Create dummy class for compatibility
    class Metrics:
        """Dummy Metrics class for compatibility when real metrics are not available."""

        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: None


# Định nghĩa các hàm tiện ích trực tiếp trong __init__ để tránh vòng lặp import
def track_auth_request(user_id: Optional[int], success: bool, auth_type: str):
    """
    Theo dõi yêu cầu xác thực.

    Args:
        user_id: ID người dùng (nếu có)
        success: Thành công hay thất bại
        auth_type: Loại xác thực (password, token, social, etc.)
    """
    # Kiểm tra metrics tồn tại
    if metrics is None:
        return

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
    try:
        # Kiểm tra metrics tồn tại
        if metrics is None:
            return

        # Observe vào histogram
        if hasattr(metrics, "request_duration"):
            metrics.request_duration.labels(method="*", endpoint=endpoint).observe(
                duration
            )

        # Ghi log nếu request quá chậm
        slow_threshold = getattr(settings, "SLOW_REQUEST_THRESHOLD", 1.0)
        if duration > slow_threshold:
            logger.warning(
                f"Slow request to {endpoint}: {duration:.2f}s (threshold: {slow_threshold}s)"
            )
    except Exception as e:
        logger.error(f"Lỗi khi theo dõi thời gian xử lý request: {str(e)}")


def track_error_request(endpoint: str, status_code: int, error_type: str = None):
    """
    Theo dõi request lỗi.

    Args:
        endpoint: Endpoint của request
        status_code: Mã trạng thái HTTP
        error_type: Loại lỗi (nếu có)
    """
    # Kiểm tra metrics tồn tại
    if metrics is None:
        # Vẫn log lỗi
        logger.warning(f"Error request to {endpoint}: {status_code}")
        return

    # Ghi log lỗi
    log_data = {
        "endpoint": endpoint,
        "status_code": status_code,
        "error_type": error_type,
        "time": time.time(),
    }

    logger.warning(f"Error request to {endpoint}: {status_code}", extra=log_data)

    # Increment counter if exists
    if hasattr(metrics, "error_requests"):
        metrics.error_requests.labels(endpoint=endpoint, status=str(status_code)).inc()


def track_login(success: bool, provider: str = None, reason: str = None):
    """
    Theo dõi đăng nhập.

    Args:
        success: Thành công hay thất bại
        provider: Nhà cung cấp xác thực (nếu là social login)
        reason: Lý do thất bại (nếu thất bại)
    """
    # Kiểm tra metrics tồn tại
    provider_name = provider or "password"

    # Log thông tin đăng nhập (luôn thực hiện ngay cả khi không có metrics)
    log_data = {
        "success": success,
        "provider": provider_name,
        "reason": reason,
        "time": time.time(),
    }

    if not success:
        logger.warning(f"Login failed via {provider_name}: {reason}", extra=log_data)
    else:
        logger.info(f"Login success via {provider_name}", extra=log_data)

    # Bỏ qua nếu không có metrics
    if metrics is None:
        return

    # Đăng ký metrics nếu chưa có
    if hasattr(metrics, "login_attempts"):
        status = "success" if success else "failure"
        metrics.login_attempts.labels(status=status).inc()


# Các decorator từ metrics.py và app_metrics.py
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
        def wrapper(*args, **kwargs):
            # Kiểm tra metrics tồn tại
            if metrics is None:
                return func(*args, **kwargs)

            if hasattr(metrics, "time_request"):
                # Dùng metrics.time_request
                method = "UNKNOWN"
                _endpoint = endpoint or func.__name__
                with metrics.time_request(method, _endpoint) as timer:
                    response = func(*args, **kwargs)
                    return response
            else:
                # Fallback nếu không có metrics
                return func(*args, **kwargs)

        return wrapper

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
        def wrapper(*args, **kwargs):
            # Kiểm tra metrics tồn tại
            if metrics is None:
                return func(*args, **kwargs)

            if hasattr(metrics, "time_db_query"):
                with metrics.time_db_query(operation, table):
                    return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        return wrapper

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
        def wrapper(*args, **kwargs):
            # Kiểm tra metrics tồn tại
            if metrics is None:
                return func(*args, **kwargs)

            if hasattr(metrics, "time_cache_operation"):
                with metrics.time_cache_operation(operation, cache_type) as timer:
                    result = func(*args, **kwargs)
                    if operation == "get" and hasattr(timer, "set_hit"):
                        timer.set_hit(result is not None)
                    return result
            else:
                return func(*args, **kwargs)

        return wrapper

    return decorator


# Import utility functions from app_metrics
try:
    from app.monitoring.metrics.app_metrics import (
        collect_request_metrics,
        start_metrics_collection,
        stop_metrics_collection,
    )
except ImportError as e:
    # If app_metrics import fails, create stub functions
    logger.warning(f"App metrics import failed: {e}")

    def collect_request_metrics(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def start_metrics_collection():
        pass

    def stop_metrics_collection():
        pass


# Import business metrics tracking functions
try:
    from app.monitoring.metrics.business_metrics import (
        track_registration,
        track_login as business_track_login,
        track_book_view,
        track_search_metrics,
        track_subscription,
    )
except ImportError as e:
    # If business_metrics import fails, create stub functions
    logger.warning(f"Business metrics import failed: {e}")

    def track_registration(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def business_track_login(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def track_book_view(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def track_search_metrics(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def track_subscription(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


def increment_counter(counter_name: str):
    """
    Tăng giá trị của một counter trong hệ thống metrics.

    Args:
        counter_name: Tên của counter cần tăng
    """
    # Kiểm tra metrics tồn tại
    if metrics is None:
        logger.debug(f"Metrics không khả dụng, bỏ qua tăng counter: {counter_name}")
        return

    # Ghi log về việc tăng counter
    logger.debug(f"Increasing counter: {counter_name}")

    # Nếu metrics đã được khởi tạo, thử tăng counter
    if hasattr(metrics, counter_name):
        try:
            # Nếu counter đã tồn tại, tăng giá trị
            getattr(metrics, counter_name).inc()
        except Exception as e:
            logger.warning(f"Không thể tăng counter {counter_name}: {e}")
    else:
        # Nếu counter chưa tồn tại, ghi log cảnh báo
        logger.debug(f"Counter {counter_name} không tồn tại trong metrics")


# Export public interface
__all__ = [
    "metrics",
    "Metrics",
    "track_auth_request",
    "track_request_duration",
    "track_error_request",
    "track_login",
    "track_request_time",
    "track_db_query_time",
    "track_cache_operation_time",
    "collect_request_metrics",
    "start_metrics_collection",
    "stop_metrics_collection",
    "track_registration",
    "business_track_login",
    "track_book_view",
    "track_search_metrics",
    "track_subscription",
    "increment_counter",
]
