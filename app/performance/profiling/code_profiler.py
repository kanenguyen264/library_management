import time
import functools
import cProfile
import pstats
import io
import tracemalloc
import gc
import inspect
import asyncio
import os
from typing import Callable, Dict, List, Any, Optional, Union, Type
from contextvars import ContextVar
from prometheus_client import Histogram
import logging
from contextlib import asynccontextmanager
import random

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Singleton instance
_PROFILER_INSTANCE = None

# Biến theo dõi profile data hiện tại
_current_profiler_data: ContextVar[Dict[str, Any]] = ContextVar(
    "current_profiler_data", default={}
)

# Histogram cho thời gian thực thi hàm
FUNCTION_EXECUTION_TIME = Histogram(
    "function_execution_time_seconds",
    "Thời gian thực thi hàm",
    ["function_name", "module", "type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30],
)

try:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    SQLALCHEMY_ASYNC_AVAILABLE = True
except ImportError:
    SQLALCHEMY_ASYNC_AVAILABLE = False

    # Mock classes
    class AsyncSession:
        pass

    def create_async_engine(*args, **kwargs):
        raise ImportError("SQLAlchemy>=1.4.0 is required for async features")


class CodeProfiler:
    """
    Lớp cung cấp các công cụ đo đạc hiệu suất code.
    Hỗ trợ tính năng:
    - Đo thời gian thực thi hàm
    - Theo dõi sử dụng bộ nhớ
    - Profile CPU usage
    - Tracking SQL queries
    """

    def __init__(
        self,
        enabled: bool = None,
        log_level: int = logging.INFO,
        save_to_file: bool = False,
        profile_dir: str = None,
    ):
        """
        Khởi tạo profiler.

        Args:
            enabled: Bật/tắt profiling, mặc định theo APP_ENV
            log_level: Mức độ ghi log
            save_to_file: Lưu kết quả profile vào file
            profile_dir: Thư mục lưu profile files
        """
        # Tự động bật trong môi trường dev, tắt trong production
        if enabled is None:
            self.enabled = not settings.is_production
        else:
            self.enabled = enabled

        self.log_level = log_level
        self.save_to_file = save_to_file

        if profile_dir:
            self.profile_dir = profile_dir
        else:
            self.profile_dir = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                ),
                "logs",
                "profiling",
            )

        # Tạo thư mục profile nếu chưa tồn tại
        if self.save_to_file and not os.path.exists(self.profile_dir):
            os.makedirs(self.profile_dir, exist_ok=True)

    def _create_or_get_profiling_context(self) -> Dict[str, Any]:
        """
        Get or create profiling context data.

        Returns:
            Dict with profiling data
        """
        try:
            profile_data = _current_profiler_data.get()
        except LookupError:
            profile_data = {}
            _current_profiler_data.set(profile_data)
        return profile_data

    def _record_time_metrics(
        self,
        func_name: str,
        duration_ms: float,
        threshold_ms: Optional[float] = None,
        histogram: Optional[Histogram] = None,
    ) -> None:
        """
        Record time metrics and log if threshold exceeded.

        Args:
            func_name: Name of the function
            duration_ms: Duration in milliseconds
            threshold_ms: Threshold for logging (milliseconds)
            histogram: Optional Prometheus histogram to record metrics
        """
        # Log if threshold exceeded
        if threshold_ms and duration_ms > threshold_ms:
            logger.log(
                self.log_level,
                f"Function {func_name} took {duration_ms:.2f}ms (threshold: {threshold_ms:.2f}ms)",
            )
        elif self.enabled:
            logger.debug(f"Function {func_name} took {duration_ms:.2f}ms")

        # Record to histogram if provided
        if histogram:
            histogram.labels(function_name=func_name).observe(duration_ms / 1000.0)
        elif self.enabled:
            # Use default histogram
            module_name = func_name.split(".")[0] if "." in func_name else "unknown"
            try:
                FUNCTION_EXECUTION_TIME.labels(
                    function_name=func_name, module=module_name, type="sync"
                ).observe(
                    duration_ms / 1000.0
                )  # Histograms record in seconds
            except Exception as e:
                logger.warning(f"Failed to record metrics: {str(e)}")

    @classmethod
    def get_instance(cls):
        """
        Trả về instance singleton của CodeProfiler.

        Returns:
            CodeProfiler: Instance singleton
        """
        global _PROFILER_INSTANCE
        if _PROFILER_INSTANCE is None:
            _PROFILER_INSTANCE = cls()
        return _PROFILER_INSTANCE

    @classmethod
    def profile_time(
        cls,
        name: Optional[str] = None,
        threshold_ms: Optional[float] = None,
        threshold: Optional[float] = None,  # For backward compatibility
        histogram: Optional[Histogram] = None,
        sample_rate: float = 1.0,
    ) -> Callable:
        """
        Decorator to profile function execution time.
        Can be called as both class method and instance method.

        Args:
            name: Name for this profile, defaults to function name
            threshold_ms: Log if execution time exceeds this threshold (ms)
            threshold: Deprecated, use threshold_ms instead. Log if execution time exceeds this threshold (seconds)
            histogram: Optional Prometheus histogram to record the duration
            sample_rate: Rate at which to sample profiling (0.0 to 1.0)

        Returns:
            Decorated function
        """
        # If called as class method, get the instance and call the instance method
        if isinstance(cls, type):
            instance = cls.get_instance()
            return instance._profile_time_impl(
                name=name,
                threshold_ms=threshold_ms,
                threshold=threshold,
                histogram=histogram,
                sample_rate=sample_rate,
            )
        # If called as instance method, 'cls' is actually 'self'
        else:
            self = cls
            return self._profile_time_impl(
                name=name,
                threshold_ms=threshold_ms,
                threshold=threshold,
                histogram=histogram,
                sample_rate=sample_rate,
            )

    def _profile_time_impl(
        self,
        name: Optional[str] = None,
        threshold_ms: Optional[float] = None,
        threshold: Optional[float] = None,  # For backward compatibility
        histogram: Optional[Histogram] = None,
        sample_rate: float = 1.0,
    ) -> Callable:
        """
        Implementation of profile_time.

        Args:
            name: Name for this profile, defaults to function name
            threshold_ms: Log if execution time exceeds this threshold (ms)
            threshold: Deprecated, use threshold_ms instead. Log if execution time exceeds this threshold (seconds)
            histogram: Optional Prometheus histogram to record the duration
            sample_rate: Rate at which to sample profiling (0.0 to 1.0)

        Returns:
            Decorated function
        """
        # For backward compatibility, convert threshold to threshold_ms if provided
        if threshold is not None and threshold_ms is None:
            threshold_ms = threshold * 1000  # Convert seconds to milliseconds

        def decorator(func: Callable) -> Callable:
            # Determine function name
            func_name = name or func.__qualname__

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                # Sample rate implementation
                if sample_rate < 1.0 and random.random() > sample_rate:
                    return func(*args, **kwargs)

                # Get current profiling data context or create a new one
                profile_data = self._create_or_get_profiling_context()

                start_time = time.time()
                result = func(*args, **kwargs)
                end_time = time.time()

                duration_sec = end_time - start_time
                duration_ms = duration_sec * 1000.0

                # Record metrics
                self._record_time_metrics(
                    func_name, duration_ms, threshold_ms, histogram
                )

                # Save duration to profile data
                profile_data.setdefault("time", {})[func_name] = duration_ms

                return result

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Sample rate implementation
                if sample_rate < 1.0 and random.random() > sample_rate:
                    return await func(*args, **kwargs)

                # Get current profiling data context or create a new one
                profile_data = self._create_or_get_profiling_context()

                start_time = time.time()
                result = await func(*args, **kwargs)
                end_time = time.time()

                duration_sec = end_time - start_time
                duration_ms = duration_sec * 1000.0

                # Record metrics
                self._record_time_metrics(
                    func_name, duration_ms, threshold_ms, histogram
                )

                # Save duration to profile data
                profile_data.setdefault("time", {})[func_name] = duration_ms

                return result

            return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper

        return decorator

    @classmethod
    def profile_time_static(
        cls,
        func=None,
        name: Optional[str] = None,
        threshold_ms: Optional[float] = None,
        threshold: Optional[float] = None,
        histogram: Optional[Histogram] = None,
        sample_rate: float = 1.0,
    ) -> Callable:
        """
        Static class method version of profile_time to use without instance.

        Args:
            func: Function to profile
            name: Name for this profile, defaults to function name
            threshold_ms: Log if execution time exceeds this threshold (ms)
            threshold: Deprecated, use threshold_ms instead
            histogram: Optional Prometheus histogram to record the duration
            sample_rate: Rate at which to sample profiling (0.0 to 1.0)

        Returns:
            Decorated function
        """
        # Get or create the singleton instance
        instance = cls.get_instance()

        # Handle both decorator forms: @profile_time_static and @profile_time_static()
        if (
            func is not None
            and callable(func)
            and not any([name, threshold_ms, threshold, histogram, sample_rate != 1.0])
        ):
            # Used as @profile_time_static without parentheses
            return instance.profile_time()(func)
        else:
            # Used as @profile_time_static(name=...) or preparing to be called with a function
            # Call the instance method
            decorator = instance.profile_time(
                name=name,
                threshold_ms=threshold_ms,
                threshold=threshold,
                histogram=histogram,
                sample_rate=sample_rate,
            )

            if func is not None:
                return decorator(func)
            return decorator

    def profile_memory(self, func=None, *, detail: bool = False):
        """
        Decorator đo lượng bộ nhớ sử dụng trong hàm.

        Args:
            func: Hàm cần đo
            detail: Hiển thị chi tiết từng object

        Returns:
            Hàm đã được wrap để đo bộ nhớ
        """

        def decorator(func):
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not self.enabled:
                    return func(*args, **kwargs)

                func_name = func.__qualname__

                # Start tracking memory
                tracemalloc.start()
                gc.collect()

                # Execute function
                start_snapshot = tracemalloc.take_snapshot()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    # Calculate memory usage
                    gc.collect()
                    end_snapshot = tracemalloc.take_snapshot()
                    tracemalloc.stop()

                    # Compare snapshots
                    stats = end_snapshot.compare_to(start_snapshot, "lineno")

                    total_diff = sum(stat.size_diff for stat in stats)

                    # Log memory usage
                    if total_diff > 0:
                        msg = f"Hàm {func_name} sử dụng thêm {total_diff / 1024:.2f} KB bộ nhớ"
                        logger.info(msg)

                        if (
                            detail and total_diff > 500 * 1024
                        ):  # Only show details for >500KB
                            top_stats = stats[:10]
                            for stat in top_stats:
                                logger.info(
                                    f"  {stat.size_diff / 1024:.1f} KB: {stat.traceback.format()[0]}"
                                )
                    elif total_diff < 0:
                        logger.info(
                            f"Hàm {func_name} giải phóng {-total_diff / 1024:.2f} KB bộ nhớ"
                        )

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not self.enabled:
                    return await func(*args, **kwargs)

                func_name = func.__qualname__

                # Start tracking memory
                tracemalloc.start()
                gc.collect()

                # Execute function
                start_snapshot = tracemalloc.take_snapshot()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    # Calculate memory usage
                    gc.collect()
                    end_snapshot = tracemalloc.take_snapshot()
                    tracemalloc.stop()

                    # Compare snapshots
                    stats = end_snapshot.compare_to(start_snapshot, "lineno")

                    total_diff = sum(stat.size_diff for stat in stats)

                    # Log memory usage
                    if total_diff > 0:
                        msg = f"Hàm async {func_name} sử dụng thêm {total_diff / 1024:.2f} KB bộ nhớ"
                        logger.info(msg)

                        if (
                            detail and total_diff > 500 * 1024
                        ):  # Only show details for >500KB
                            top_stats = stats[:10]
                            for stat in top_stats:
                                logger.info(
                                    f"  {stat.size_diff / 1024:.1f} KB: {stat.traceback.format()[0]}"
                                )
                    elif total_diff < 0:
                        logger.info(
                            f"Hàm async {func_name} giải phóng {-total_diff / 1024:.2f} KB bộ nhớ"
                        )

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        if func is None:
            return decorator
        return decorator(func)

    @staticmethod
    def profile_memory_static(func=None, *, detail: bool = False):
        """
        Decorator tĩnh đo lượng bộ nhớ sử dụng trong hàm.
        Phiên bản tĩnh có thể gọi trực tiếp từ lớp: @CodeProfiler.profile_memory_static()

        Args:
            func: Hàm cần đo
            detail: Hiển thị chi tiết từng object

        Returns:
            Hàm đã được wrap để đo bộ nhớ
        """
        global _PROFILER_INSTANCE
        if _PROFILER_INSTANCE is None:
            _PROFILER_INSTANCE = CodeProfiler()

        # Gọi phương thức instance thông thường
        return _PROFILER_INSTANCE.profile_memory(func=func, detail=detail)

    def profile_cpu(self, func=None, *, top_n: int = 20, save_to_file: bool = None):
        """
        Decorator đo lường CPU usage của hàm.

        Args:
            func: Hàm cần đo
            top_n: Số lượng function call hiển thị
            save_to_file: Lưu kết quả vào file

        Returns:
            Hàm đã được wrap
        """

        def decorator(func):
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not self.enabled:
                    return func(*args, **kwargs)

                func_name = func.__qualname__
                should_save = (
                    self.save_to_file if save_to_file is None else save_to_file
                )

                # Tạo đường dẫn file profile
                if should_save:
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    profile_file = os.path.join(
                        self.profile_dir,
                        f"{func.__module__.replace('.', '_')}_{func_name}_{timestamp}.prof",
                    )

                # Profile the function
                profiler = cProfile.Profile()
                profiler.enable()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    profiler.disable()

                    # Process profile data
                    s = io.StringIO()
                    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
                    ps.print_stats(top_n)

                    # Log the profile results
                    logger.info(f"CPU Profile cho {func_name}:\n{s.getvalue()}")

                    # Save to file if configured
                    if should_save:
                        ps.dump_stats(profile_file)
                        logger.info(f"Đã lưu CPU profile vào {profile_file}")

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not self.enabled:
                    return await func(*args, **kwargs)

                func_name = func.__qualname__
                should_save = (
                    self.save_to_file if save_to_file is None else save_to_file
                )

                # Tạo đường dẫn file profile
                if should_save:
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    profile_file = os.path.join(
                        self.profile_dir,
                        f"{func.__module__.replace('.', '_')}_{func_name}_{timestamp}.prof",
                    )

                # Profile the function
                profiler = cProfile.Profile()
                profiler.enable()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    profiler.disable()

                    # Process profile data
                    s = io.StringIO()
                    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
                    ps.print_stats(top_n)

                    # Log the profile results
                    logger.info(f"CPU Profile cho async {func_name}:\n{s.getvalue()}")

                    # Save to file if configured
                    if should_save:
                        ps.dump_stats(profile_file)
                        logger.info(f"Đã lưu CPU profile vào {profile_file}")

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        if func is None:
            return decorator
        return decorator(func)

    @staticmethod
    def profile_cpu_static(func=None, *, top_n: int = 20, save_to_file: bool = None):
        """
        Decorator tĩnh đo CPU usage của hàm.
        Phiên bản tĩnh có thể gọi trực tiếp từ lớp: @CodeProfiler.profile_cpu_static()

        Args:
            func: Hàm cần đo
            top_n: Số lượng hàm hot nhất hiển thị
            save_to_file: Lưu profile vào file

        Returns:
            Hàm đã được wrap để đo CPU
        """
        global _PROFILER_INSTANCE
        if _PROFILER_INSTANCE is None:
            _PROFILER_INSTANCE = CodeProfiler()

        # Gọi phương thức instance thông thường
        return _PROFILER_INSTANCE.profile_cpu(
            func=func, top_n=top_n, save_to_file=save_to_file
        )


# Tạo singleton instance
profiler = CodeProfiler()

# Các decorator tiện ích ở cấp module
profile_time = profiler.profile_time
profile_memory = profiler.profile_memory
profile_cpu = profiler.profile_cpu


# Hàm tiện ích để export từ module
def profile_function(func=None, *, name=None, threshold=None, threshold_ms=None):
    """
    Decorator đo thời gian thực thi hàm.

    Args:
        func: Hàm cần đo
        name: Tên tùy chỉnh cho metric
        threshold: Ngưỡng cảnh báo (giây) - Deprecated, use threshold_ms instead
        threshold_ms: Ngưỡng cảnh báo (mili giây)

    Returns:
        Hàm đã được wrap để đo thời gian
    """
    # For backward compatibility, convert threshold to threshold_ms if provided
    if threshold is not None and threshold_ms is None:
        threshold_ms = threshold * 1000  # Convert seconds to milliseconds

    # Get or create the singleton instance
    instance = CodeProfiler.get_instance()

    # Handle both forms: @profile_function and @profile_function()
    if func is not None and callable(func) and not any([name, threshold_ms]):
        # Used directly as @profile_function
        return instance.profile_time()(func)
    else:
        # Used as @profile_function(name=...) or preparing to be called with a function
        decorator = instance.profile_time(name=name, threshold_ms=threshold_ms)

        if func is not None:
            return decorator(func)
        return decorator


def profile_memory(func=None, *, detail=False):
    """
    Decorator đo lường sử dụng bộ nhớ của hàm.

    Args:
        func: Hàm cần đo
        detail: Hiển thị chi tiết về việc sử dụng bộ nhớ

    Returns:
        Hàm đã được wrap để đo bộ nhớ
    """
    return CodeProfiler.profile_memory_static(func, detail=detail)


def profile_cpu(func=None, *, top_n=20, save_to_file=None):
    """
    Decorator đo lường CPU usage của hàm.

    Args:
        func: Hàm cần đo
        top_n: Số lượng hàm sử dụng nhiều CPU nhất để hiển thị
        save_to_file: Lưu kết quả vào file

    Returns:
        Hàm đã được wrap để đo CPU
    """
    return CodeProfiler.profile_cpu_static(func, top_n=top_n, save_to_file=save_to_file)


def _get_code_profiler_instance():
    """Trả về instance singleton của CodeProfiler"""
    global _PROFILER_INSTANCE
    if _PROFILER_INSTANCE is None:
        _PROFILER_INSTANCE = CodeProfiler()
    return _PROFILER_INSTANCE
