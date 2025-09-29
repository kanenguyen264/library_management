"""
Module phân tích hiệu năng (Profiling) - Cung cấp công cụ đo lường và phân tích hiệu năng.

Module này cung cấp:
- API Profiler: Đo lường và phân tích hiệu năng của các API endpoint
- Code Profiler: Phân tích hiệu năng của các hàm và code blocks
- Các decorator cho phép dễ dàng profile các phần khác nhau của ứng dụng
"""

from app.performance.profiling.api_profiler import (
    APIProfiler,
    APIProfilerMiddleware,
    profile_endpoint,
    profile_dependency,
)

from app.performance.profiling.code_profiler import (
    CodeProfiler,
    profile_function,
    profile_memory,
    profile_cpu,
)

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo singleton instances
_api_profiler = None
_code_profiler = None


def get_api_profiler():
    """
    Lấy hoặc khởi tạo API Profiler.

    Returns:
        APIProfiler instance
    """
    global _api_profiler
    if _api_profiler is None:
        _api_profiler = APIProfiler(
            slow_endpoint_threshold=settings.SLOW_ENDPOINT_THRESHOLD,
            slow_dependency_threshold=settings.SLOW_DEPENDENCY_THRESHOLD,
            sample_rate=settings.PROFILER_SAMPLE_RATE,
            trace_enabled=settings.TRACING_ENABLED,
            profile_enabled=settings.PROFILER_ENABLED,
        )
        logger.info("Đã khởi tạo API Profiler")
    return _api_profiler


def get_code_profiler():
    """
    Lấy hoặc khởi tạo Code Profiler.

    Returns:
        CodeProfiler instance
    """
    global _code_profiler
    if _code_profiler is None:
        _code_profiler = CodeProfiler(
            enabled=settings.PROFILER_ENABLED,
            save_to_file=settings.PROFILER_SAVE_TO_FILE,
            profile_dir=settings.PROFILER_DIR,
        )
        logger.info("Đã khởi tạo Code Profiler")
    return _code_profiler


def setup_api_profiler(app=None):
    """
    Thiết lập API Profiler cho ứng dụng.

    Args:
        app: Ứng dụng FastAPI (tùy chọn)

    Returns:
        APIProfiler instance
    """
    profiler = get_api_profiler()

    if app and settings.PROFILER_ENABLED:
        # Thêm middleware profiling
        app.add_middleware(APIProfilerMiddleware, profiler=profiler)

        # Thiết lập các handlers
        profiler.setup(app)

        logger.info("Đã thiết lập API Profiler Middleware")

    return profiler


def profile_code_block(name=None, threshold=0.1):
    """
    Tạo context manager để profile một đoạn code.

    Args:
        name: Tên của code block (tùy chọn)
        threshold: Ngưỡng thời gian để log warning (giây)

    Returns:
        Context manager để profile code
    """
    profiler = get_code_profiler()
    # Convert threshold from seconds to milliseconds
    threshold_ms = threshold * 1000 if threshold is not None else None
    return profiler.profile_time(name=name, threshold_ms=threshold_ms)


# Export các components
__all__ = [
    "APIProfiler",
    "APIProfilerMiddleware",
    "profile_endpoint",
    "profile_dependency",
    "CodeProfiler",
    "profile_function",
    "profile_memory",
    "profile_cpu",
    "get_api_profiler",
    "get_code_profiler",
    "setup_api_profiler",
    "profile_code_block",
]
