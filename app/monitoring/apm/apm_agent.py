from typing import Dict, List, Any, Optional, Union
import logging
import os
import sys
import traceback
from functools import wraps
import asyncio
import time

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

try:
    import ddtrace
    from ddtrace.profiling import Profiler

    DDTRACE_AVAILABLE = True
except ImportError:
    DDTRACE_AVAILABLE = False

    # Tạo mock class và objects
    class MockConfig:
        def __init__(self):
            self.service = None
            self.env = None
            self.version = None

    class MockTracer:
        def trace(self, name, service=None, resource=None, span_type=None):
            class MockSpan:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass

                def set_tag(self, key, value):
                    pass

            return MockSpan()

    class MockDDTrace:
        def __init__(self):
            self.config = MockConfig()
            self.tracer = MockTracer()

    ddtrace = MockDDTrace()

    class Profiler:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass


class APMAgent:
    """
    Agent Application Performance Monitoring (APM).
    Tích hợp với các dịch vụ APM như New Relic, Elastic APM, etc.
    """

    def __init__(self, service_name: str = "api_readingbook"):
        """
        Khởi tạo APM agent.

        Args:
            service_name: Tên dịch vụ
        """
        self.service_name = service_name
        self.enabled = getattr(settings, "TRACING_ENABLED", False)
        self.provider = getattr(settings, "APM_PROVIDER", "elastic")
        self.agent = None

        # Khởi tạo APM client
        if self.enabled:
            self._initialize_agent()

    def _initialize_agent(self):
        """Khởi tạo APM client dựa trên provider."""
        try:
            if self.provider == "elastic":
                self._initialize_elastic_apm()
            elif self.provider == "newrelic":
                self._initialize_newrelic_apm()
            elif self.provider == "datadog":
                self._initialize_datadog_apm()
            else:
                logger.warning(f"Không hỗ trợ APM provider: {self.provider}")

        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo APM agent ({self.provider}): {str(e)}")
            self.enabled = False

    def _initialize_elastic_apm(self):
        """Khởi tạo Elastic APM client."""
        try:
            import elasticapm
            from elasticapm.contrib.starlette import ElasticAPM

            self.agent = elasticapm.Client(
                service_name=self.service_name,
                server_url=getattr(settings, "APM_SERVER_URL", None),
                environment=getattr(settings, "ENVIRONMENT", "development"),
                # Additional Elastic APM settings
                transaction_sample_rate=getattr(
                    settings, "APM_TRANSACTION_SAMPLE_RATE", 1.0
                ),
                enabled=True,
            )

            logger.info("Đã khởi tạo Elastic APM agent")

        except ImportError:
            logger.error(
                "Không thể import elasticapm. Hãy cài đặt: pip install elastic-apm"
            )
            self.enabled = False

    def _initialize_newrelic_apm(self):
        """Khởi tạo New Relic APM client."""
        try:
            import newrelic.agent

            newrelic.agent.initialize(
                getattr(settings, "APM_CONFIG_FILE_PATH", "newrelic.ini"),
                environment=getattr(settings, "ENVIRONMENT", "development"),
            )

            self.agent = newrelic.agent

            logger.info("Đã khởi tạo New Relic APM agent")

        except ImportError:
            logger.error("Không thể import newrelic. Hãy cài đặt: pip install newrelic")
            self.enabled = False

    def _initialize_datadog_apm(self):
        """Khởi tạo Datadog APM client."""
        try:
            import ddtrace

            ddtrace.patch_all()
            self.agent = ddtrace

            logger.info("Đã khởi tạo Datadog APM agent")

        except ImportError:
            logger.error("Không thể import ddtrace. Hãy cài đặt: pip install ddtrace")
            self.enabled = False

    def capture_exception(self, exc: Exception = None, **kwargs):
        """
        Capture exception for APM.

        Args:
            exc: Ngoại lệ cần capture
            **kwargs: Thông tin bổ sung
        """
        if not self.enabled or not self.agent:
            return

        try:
            if self.provider == "elastic":
                self.agent.capture_exception(
                    exc_info=(
                        sys.exc_info()
                        if exc is None
                        else (type(exc), exc, exc.__traceback__)
                    ),
                    custom=kwargs,
                )
            elif self.provider == "newrelic":
                self.agent.record_exception(exc=exc, params=kwargs)
            elif self.provider == "datadog":
                # Datadog tự động capture exceptions
                pass

        except Exception as e:
            logger.error(f"Lỗi khi capture exception trong APM: {str(e)}")

    def set_custom_context(self, name: str, value: Any):
        """
        Thiết lập custom context cho transaction hiện tại.

        Args:
            name: Tên context
            value: Giá trị context
        """
        if not self.enabled or not self.agent:
            return

        try:
            if self.provider == "elastic":
                self.agent.set_custom_context({name: value})
            elif self.provider == "newrelic":
                self.agent.add_custom_parameter(name, value)
            elif self.provider == "datadog":
                from ddtrace import tracer

                span = tracer.current_span()
                if span:
                    span.set_tag(name, value)

        except Exception as e:
            logger.error(f"Lỗi khi set custom context trong APM: {str(e)}")

    def set_user_context(
        self, user_id: str, username: Optional[str] = None, email: Optional[str] = None
    ):
        """
        Thiết lập user context cho transaction hiện tại.

        Args:
            user_id: ID người dùng
            username: Tên người dùng
            email: Email người dùng
        """
        if not self.enabled or not self.agent:
            return

        try:
            if self.provider == "elastic":
                self.agent.set_user_context(
                    username=username, email=email, user_id=user_id
                )
            elif self.provider == "newrelic":
                self.agent.add_custom_parameter("user_id", user_id)
                if username:
                    self.agent.add_custom_parameter("username", username)
                if email:
                    self.agent.add_custom_parameter("email", email)
            elif self.provider == "datadog":
                from ddtrace import tracer

                span = tracer.current_span()
                if span:
                    span.set_tag("user.id", user_id)
                    if username:
                        span.set_tag("user.username", username)
                    if email:
                        span.set_tag("user.email", email)

        except Exception as e:
            logger.error(f"Lỗi khi set user context trong APM: {str(e)}")

    def start_transaction(self, name: str, transaction_type: str = "custom"):
        """
        Bắt đầu một custom transaction.

        Args:
            name: Tên transaction
            transaction_type: Loại transaction

        Returns:
            Transaction object
        """
        if not self.enabled or not self.agent:
            # Return dummy transaction
            return DummyTransaction()

        try:
            if self.provider == "elastic":
                return self.agent.begin_transaction(transaction_type, trace_parent=None)
            elif self.provider == "newrelic":
                return self.agent.background_task(name=name)(lambda: None)
            elif self.provider == "datadog":
                from ddtrace import tracer

                return tracer.trace(name, service=self.service_name)

        except Exception as e:
            logger.error(f"Lỗi khi bắt đầu transaction trong APM: {str(e)}")

        # Return dummy transaction nếu có lỗi
        return DummyTransaction()

    def end_transaction(self, name: Optional[str] = None, result: str = "success"):
        """
        Kết thúc transaction hiện tại.

        Args:
            name: Tên transaction
            result: Kết quả transaction
        """
        if not self.enabled or not self.agent:
            return

        try:
            if self.provider == "elastic":
                self.agent.end_transaction(name, result)
            elif self.provider == "newrelic":
                # New Relic tự động end transactions
                pass
            elif self.provider == "datadog":
                # Datadog tự động end transactions khi context manager kết thúc
                pass

        except Exception as e:
            logger.error(f"Lỗi khi kết thúc transaction trong APM: {str(e)}")

    def custom_metric(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ):
        """
        Ghi custom metric.

        Args:
            name: Tên metric
            value: Giá trị metric
            tags: Tags cho metric
        """
        if not self.enabled or not self.agent:
            return

        try:
            if self.provider == "elastic":
                # Elastic APM không hỗ trợ custom metrics trực tiếp
                self.set_custom_context(name, value)
            elif self.provider == "newrelic":
                self.agent.record_custom_metric(name, value)
            elif self.provider == "datadog":
                from ddtrace import tracer

                span = tracer.current_span()
                if span:
                    span.set_metric(name, value)
                    if tags:
                        for key, val in tags.items():
                            span.set_tag(key, val)

        except Exception as e:
            logger.error(f"Lỗi khi ghi custom metric trong APM: {str(e)}")


class DummyTransaction:
    """Dummy transaction object khi APM không được bật."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


# Tạo singleton instance
apm_agent = APMAgent()


# Decorators tiện ích
def trace_function(name: Optional[str] = None, transaction_type: str = "function"):
    """
    Decorator để trace function.

    Args:
        name: Tên transaction (mặc định là tên function)
        transaction_type: Loại transaction

    Returns:
        Decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Xác định tên transaction
            transaction_name = name or func.__qualname__

            # Bắt đầu transaction
            with apm_agent.start_transaction(transaction_name, transaction_type):
                try:
                    # Thực hiện function
                    return await func(*args, **kwargs)
                except Exception as exc:
                    # Capture exception
                    apm_agent.capture_exception(exc)
                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Xác định tên transaction
            transaction_name = name or func.__qualname__

            # Bắt đầu transaction
            with apm_agent.start_transaction(transaction_name, transaction_type):
                try:
                    # Thực hiện function
                    return func(*args, **kwargs)
                except Exception as exc:
                    # Capture exception
                    apm_agent.capture_exception(exc)
                    raise

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def initialize_apm(service_name: str, env: str) -> None:
    """
    Khởi tạo APM agent.

    Args:
        service_name: Tên service
        env: Môi trường (dev, staging, production)
    """
    if not DDTRACE_AVAILABLE:
        logger.warning("ddtrace không được cài đặt. APM sẽ không hoạt động.")
        return

    # Thiết lập cấu hình cơ bản
    ddtrace.config.service = service_name
    ddtrace.config.env = env
    ddtrace.config.version = get_settings().VERSION

    # Bắt đầu profiler
    profiler = Profiler(service=service_name, env=env, version=get_settings().VERSION)
    profiler.start()

    logger.info(
        f"Đã khởi tạo APM agent cho service {service_name} trong môi trường {env}"
    )
