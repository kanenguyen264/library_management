from typing import Dict, List, Any, Optional, Union, Set, Tuple
import time
import asyncio
import logging
from functools import wraps
from enum import Enum
import json
from datetime import datetime

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.monitoring.metrics.metrics import Metrics, metrics


settings = get_settings()
logger = get_logger(__name__)

# Biến để theo dõi việc khởi tạo
_business_metrics_initialized = False


class BusinessMetrics:
    """
    Thu thập các metrics nghiệp vụ của ứng dụng.
    """

    def __init__(self):
        """Khởi tạo."""
        global _business_metrics_initialized

        # Cấu hình
        self.enabled = (
            settings.BUSINESS_METRICS_ENABLED
            if hasattr(settings, "BUSINESS_METRICS_ENABLED")
            else False
        )

        # Trạng thái
        self.metrics_data = {}

        # Chỉ log một lần để tránh trùng lặp
        if not _business_metrics_initialized:
            logger.info(f"Khởi tạo BusinessMetrics, enabled={self.enabled}")
            _business_metrics_initialized = True

    def track_user_registration(self):
        """Ghi nhận đăng ký người dùng mới."""
        if not self.enabled:
            return

        metrics.user_registrations.inc()

    def track_user_login(self, success: bool, reason: Optional[str] = None):
        """
        Ghi nhận đăng nhập.

        Args:
            success: True nếu đăng nhập thành công
            reason: Lý do đăng nhập thất bại
        """
        if not self.enabled:
            return

        metrics.track_login(success, reason)

        if success:
            metrics.active_users.inc()

    def track_user_logout(self):
        """Ghi nhận đăng xuất."""
        if not self.enabled:
            return

        metrics.active_users.dec()

    def track_book_view(self, book_id: str, user_type: str = "registered"):
        """
        Ghi nhận lượt xem sách.

        Args:
            book_id: ID sách
            user_type: Loại người dùng
        """
        if not self.enabled:
            return

        metrics.book_views.labels(book_id=book_id, user_type=user_type).inc()

    def track_book_rating(self, rating: int):
        """
        Ghi nhận đánh giá sách.

        Args:
            rating: Đánh giá (1-5)
        """
        if not self.enabled:
            return

        metrics.book_ratings.labels(rating=str(rating)).inc()

    def track_reading_session(self, device_type: str, duration: float, book_type: str):
        """
        Ghi nhận phiên đọc.

        Args:
            device_type: Loại thiết bị
            duration: Thời gian đọc (giây)
            book_type: Loại sách
        """
        if not self.enabled:
            return

        metrics.track_reading_session(device_type, duration, book_type)

    def track_book_activity(
        self,
        book_id: int,
        activity_type: str,
        user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Ghi nhận hoạt động liên quan đến sách.

        Args:
            book_id: ID của sách
            activity_type: Loại hoạt động (view, download, bookmark, share, etc.)
            user_id: ID người dùng (nếu có)
            metadata: Dữ liệu bổ sung về hoạt động
        """
        if not self.enabled:
            return

        # Đăng ký metric nếu chưa có
        if not hasattr(metrics, "book_activities"):
            from prometheus_client import Counter

            metrics.book_activities = Counter(
                "book_activities_total",
                "Tổng số hoạt động liên quan đến sách",
                ["book_id", "activity_type", "user_type"],
                registry=metrics.registry,
            )

        # Xác định loại người dùng
        user_type = "authenticated" if user_id else "anonymous"

        # Ghi metrics
        metrics.book_activities.labels(
            book_id=str(book_id), activity_type=activity_type, user_type=user_type
        ).inc()

        # Log hoạt động với metadata nếu debug
        if logger.isEnabledFor(logging.DEBUG) and metadata:
            logger.debug(
                f"Book activity: book_id={book_id}, activity={activity_type}, "
                f"user_id={user_id}, metadata={metadata}"
            )

    def track_purchase(self, amount: float, product_type: str):
        """
        Ghi nhận mua hàng.

        Args:
            amount: Số tiền
            product_type: Loại sản phẩm
        """
        if not self.enabled:
            return

        # Đăng ký metric nếu chưa có
        if not hasattr(metrics, "purchase_amount"):
            from prometheus_client import Counter

            metrics.purchase_amount = Counter(
                "purchase_amount_total",
                "Tổng số tiền giao dịch",
                ["product_type"],
                registry=metrics.registry,
            )

        metrics.purchase_amount.labels(product_type=product_type).inc(amount)

    def track_subscription_change(self, plan: str, action: str):
        """
        Ghi nhận thay đổi gói đăng ký.

        Args:
            plan: Tên gói
            action: Hành động (subscribe, upgrade, downgrade, cancel)
        """
        if not self.enabled:
            return

        # Đăng ký metric nếu chưa có
        if not hasattr(metrics, "subscription_changes"):
            from prometheus_client import Counter

            metrics.subscription_changes = Counter(
                "subscription_changes_total",
                "Tổng số thay đổi gói đăng ký",
                ["plan", "action"],
                registry=metrics.registry,
            )

        metrics.subscription_changes.labels(plan=plan, action=action).inc()

    def track_search(self, query_type: str, result_count: int, duration: float):
        """
        Ghi nhận tìm kiếm.

        Args:
            query_type: Loại truy vấn
            result_count: Số lượng kết quả
            duration: Thời gian thực hiện (giây)
        """
        if not self.enabled:
            return

        # Đăng ký metrics nếu chưa có
        if not hasattr(metrics, "search_count"):
            from prometheus_client import Counter, Histogram

            metrics.search_count = Counter(
                "search_count_total",
                "Tổng số tìm kiếm",
                ["query_type"],
                registry=metrics.registry,
            )

            metrics.search_results = Histogram(
                "search_results",
                "Số lượng kết quả tìm kiếm",
                ["query_type"],
                buckets=(0, 1, 5, 10, 20, 50, 100, 500, float("inf")),
                registry=metrics.registry,
            )

            metrics.search_duration = Histogram(
                "search_duration_seconds",
                "Thời gian thực hiện tìm kiếm",
                ["query_type"],
                buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf")),
                registry=metrics.registry,
            )

        # Ghi metrics
        metrics.search_count.labels(query_type=query_type).inc()
        metrics.search_results.labels(query_type=query_type).observe(result_count)
        metrics.search_duration.labels(query_type=query_type).observe(duration)

    def track_recommendation(
        self, recommendation_type: str, recommended_count: int, user_type: str
    ):
        """
        Ghi nhận gợi ý.

        Args:
            recommendation_type: Loại gợi ý
            recommended_count: Số lượng mục gợi ý
            user_type: Loại người dùng
        """
        if not self.enabled:
            return

        # Đăng ký metrics nếu chưa có
        if not hasattr(metrics, "recommendation_count"):
            from prometheus_client import Counter, Histogram

            metrics.recommendation_count = Counter(
                "recommendation_count_total",
                "Tổng số lần gợi ý",
                ["type", "user_type"],
                registry=metrics.registry,
            )

            metrics.recommendation_items = Histogram(
                "recommendation_items",
                "Số lượng mục gợi ý",
                ["type"],
                buckets=(1, 3, 5, 10, 20, 50, 100, float("inf")),
                registry=metrics.registry,
            )

        # Ghi metrics
        metrics.recommendation_count.labels(
            type=recommendation_type, user_type=user_type
        ).inc()
        metrics.recommendation_items.labels(type=recommendation_type).observe(
            recommended_count
        )

    def track_social_action(self, action_type: str, content_type: str):
        """
        Ghi nhận hành động xã hội.

        Args:
            action_type: Loại hành động (like, share, comment)
            content_type: Loại nội dung
        """
        if not self.enabled:
            return

        # Đăng ký metric nếu chưa có
        if not hasattr(metrics, "social_actions"):
            from prometheus_client import Counter

            metrics.social_actions = Counter(
                "social_actions_total",
                "Tổng số hành động xã hội",
                ["action", "content_type"],
                registry=metrics.registry,
            )

        # Ghi metrics
        metrics.social_actions.labels(
            action=action_type, content_type=content_type
        ).inc()

    def track_subscription(
        self, plan_id: str, action: str, user_id: str = None, amount: float = 0
    ):
        """
        Ghi nhận hành động đăng ký gói.

        Args:
            plan_id: ID gói đăng ký
            action: Loại hành động (subscribe, renew, upgrade, downgrade, cancel)
            user_id: ID người dùng (nếu có)
            amount: Số tiền giao dịch
        """
        if not self.enabled:
            return

        # Đăng ký metrics nếu chưa có
        if not hasattr(metrics, "subscription_actions"):
            from prometheus_client import Counter

            metrics.subscription_actions = Counter(
                "subscription_actions_total",
                "Tổng số hành động đăng ký gói",
                ["plan_id", "action"],
                registry=metrics.registry,
            )

            metrics.subscription_revenue = Counter(
                "subscription_revenue_total",
                "Tổng doanh thu từ đăng ký gói",
                ["plan_id", "action"],
                registry=metrics.registry,
            )

        # Ghi nhận hành động
        metrics.subscription_actions.labels(plan_id=plan_id, action=action).inc()

        # Ghi nhận doanh thu nếu có
        if amount > 0:
            metrics.subscription_revenue.labels(plan_id=plan_id, action=action).inc(
                amount
            )

        # Log hành động
        logger.info(
            f"Ghi nhận subscription: {action}",
            extra={
                "plan_id": plan_id,
                "action": action,
                "user_id": user_id,
                "amount": amount,
            },
        )


# Khởi tạo singleton instance
business_metrics = BusinessMetrics()


# Decorators tiện ích
def track_registration(func):
    """Decorator để ghi nhận đăng ký."""

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        business_metrics.track_user_registration()
        return result

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        business_metrics.track_user_registration()
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


def track_login(success_status="status"):
    """
    Decorator để ghi nhận đăng nhập.

    Args:
        success_status: Tên tham số trả về chứa trạng thái đăng nhập
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Lấy trạng thái đăng nhập từ kết quả
            success = False
            reason = None

            if isinstance(result, dict):
                success = result.get(success_status, False)
                reason = result.get("reason", None)
            elif hasattr(result, success_status):
                success = getattr(result, success_status)
                reason = (
                    getattr(result, "reason", None)
                    if hasattr(result, "reason")
                    else None
                )

            business_metrics.track_user_login(success, reason)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Lấy trạng thái đăng nhập từ kết quả
            success = False
            reason = None

            if isinstance(result, dict):
                success = result.get(success_status, False)
                reason = result.get("reason", None)
            elif hasattr(result, success_status):
                success = getattr(result, success_status)
                reason = (
                    getattr(result, "reason", None)
                    if hasattr(result, "reason")
                    else None
                )

            business_metrics.track_user_login(success, reason)
            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def track_book_view(book_id_param="book_id", user_type_param=None):
    """
    Decorator để ghi nhận lượt xem sách.

    Args:
        book_id_param: Tên tham số chứa book_id
        user_type_param: Tên tham số chứa user_type
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Lấy book_id
            book_id = kwargs.get(book_id_param)
            if book_id is None and args and len(args) > 1:
                book_id = args[1]  # Giả sử tham số thứ 2 là book_id

            # Lấy user_type
            user_type = "registered"
            if user_type_param and user_type_param in kwargs:
                user_type = kwargs[user_type_param]

            if book_id:
                business_metrics.track_book_view(str(book_id), user_type)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Lấy book_id
            book_id = kwargs.get(book_id_param)
            if book_id is None and args and len(args) > 1:
                book_id = args[1]  # Giả sử tham số thứ 2 là book_id

            # Lấy user_type
            user_type = "registered"
            if user_type_param and user_type_param in kwargs:
                user_type = kwargs[user_type_param]

            if book_id:
                business_metrics.track_book_view(str(book_id), user_type)

            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def track_search_metrics(query_type_param="query_type"):
    """
    Decorator để ghi nhận metrics tìm kiếm.

    Args:
        query_type_param: Tên tham số chứa loại truy vấn

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Lấy query_type
            query_type = kwargs.get(query_type_param, "unknown")

            # Thực hiện tìm kiếm và ghi nhận thời gian
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)

                # Tính toán số lượng kết quả và thời gian
                result_count = (
                    len(result.get("items", [])) if isinstance(result, dict) else 0
                )
                if isinstance(result, list):
                    result_count = len(result)

                duration = time.time() - start_time

                # Ghi nhận metrics
                business_metrics.track_search(query_type, result_count, duration)

                return result
            except Exception as e:
                # Vẫn ghi nhận metrics ngay cả khi có lỗi
                duration = time.time() - start_time
                business_metrics.track_search(query_type, 0, duration)
                raise e

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Lấy query_type
            query_type = kwargs.get(query_type_param, "unknown")

            # Thực hiện tìm kiếm và ghi nhận thời gian
            start_time = time.time()
            try:
                result = func(*args, **kwargs)

                # Tính toán số lượng kết quả và thời gian
                result_count = (
                    len(result.get("items", [])) if isinstance(result, dict) else 0
                )
                if isinstance(result, list):
                    result_count = len(result)

                duration = time.time() - start_time

                # Ghi nhận metrics
                business_metrics.track_search(query_type, result_count, duration)

                return result
            except Exception as e:
                # Vẫn ghi nhận metrics ngay cả khi có lỗi
                duration = time.time() - start_time
                business_metrics.track_search(query_type, 0, duration)
                raise e

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_subscription(
    plan_id_param="plan_id", action_param="action", amount_param=None
):
    """
    Decorator để ghi nhận đăng ký gói.

    Args:
        plan_id_param: Tên tham số chứa ID gói đăng ký
        action_param: Tên tham số chứa loại hành động
        amount_param: Tên tham số chứa số tiền (nếu có)

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Lấy thông tin từ kwargs
            plan_id = kwargs.get(plan_id_param, "unknown")
            action = kwargs.get(action_param, "unknown")
            amount = kwargs.get(amount_param, 0) if amount_param else 0

            # Gọi hàm gốc
            result = await func(*args, **kwargs)

            # Ghi nhận metrics
            user_id = result.get("user_id") if isinstance(result, dict) else None
            business_metrics.track_subscription(plan_id, action, user_id, amount)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Lấy thông tin từ kwargs
            plan_id = kwargs.get(plan_id_param, "unknown")
            action = kwargs.get(action_param, "unknown")
            amount = kwargs.get(amount_param, 0) if amount_param else 0

            # Gọi hàm gốc
            result = func(*args, **kwargs)

            # Ghi nhận metrics
            user_id = result.get("user_id") if isinstance(result, dict) else None
            business_metrics.track_subscription(plan_id, action, user_id, amount)

            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Export các functions hữu ích ở module level cho dễ sử dụng
def track_user_registration():
    """Ghi nhận đăng ký người dùng mới."""
    return business_metrics.track_user_registration()


def track_user_login(success: bool, reason: Optional[str] = None):
    """Ghi nhận đăng nhập."""
    return business_metrics.track_user_login(success, reason)


def track_user_logout():
    """Ghi nhận đăng xuất."""
    return business_metrics.track_user_logout()


def track_book_view(book_id: str, user_type: str = "registered"):
    """Ghi nhận lượt xem sách."""
    return business_metrics.track_book_view(book_id, user_type)


def track_book_activity(
    book_id: int,
    activity_type: str,
    user_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Ghi nhận hoạt động liên quan đến sách."""
    return business_metrics.track_book_activity(
        book_id, activity_type, user_id, metadata
    )


def track_book_rating(rating: int):
    """Ghi nhận đánh giá sách."""
    return business_metrics.track_book_rating(rating)


def track_reading_session(device_type: str, duration: float, book_type: str):
    """Ghi nhận phiên đọc."""
    return business_metrics.track_reading_session(device_type, duration, book_type)


def track_purchase(amount: float, product_type: str):
    """Ghi nhận mua hàng."""
    return business_metrics.track_purchase(amount, product_type)


def track_subscription_change(plan: str, action: str):
    """Ghi nhận thay đổi gói đăng ký."""
    return business_metrics.track_subscription_change(plan, action)


def track_search(query_type: str, result_count: int, duration: float):
    """Ghi nhận tìm kiếm."""
    return business_metrics.track_search(query_type, result_count, duration)


def track_recommendation(
    recommendation_type: str, recommended_count: int, user_type: str
):
    """Ghi nhận gợi ý."""
    return business_metrics.track_recommendation(
        recommendation_type, recommended_count, user_type
    )
