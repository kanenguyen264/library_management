import time
import functools
import json
import inspect
import asyncio
import os
from typing import Dict, List, Any, Optional, Callable, Set, Union
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Histogram, Summary, Counter
import logging
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import statistics
from functools import wraps
import traceback
from pathlib import Path
import random

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.performance.profiling.code_profiler import profile_function
from app.monitoring.metrics.app_metrics import metrics

settings = get_settings()
logger = get_logger(__name__)

# Prometheus metrics
ENDPOINT_LATENCY = Histogram(
    "api_endpoint_latency_seconds",
    "Thời gian xử lý API endpoint",
    ["endpoint", "method", "status_code"],
    buckets=[
        0.005,
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
    ],
)

DEPENDENCY_LATENCY = Histogram(
    "api_dependency_latency_seconds",
    "Thời gian xử lý dependency injection",
    ["dependency_name"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
)

SLOW_ENDPOINTS_COUNTER = Counter(
    "api_slow_endpoint_total",
    "Số lần endpoint chạy chậm hơn ngưỡng",
    ["endpoint", "method"],
)

ERROR_COUNTER = Counter(
    "api_error_total", "Số lỗi API theo endpoint", ["endpoint", "method", "error_type"]
)


class APIProfiler:
    """
    Phân tích hiệu suất API và xác định bottlenecks.

    Tính năng:
    - Thu thập thông tin thời gian xử lý của tất cả endpoints
    - Xác định các endpoint và dependency chậm
    - Theo dõi các lỗi và exception
    - Báo cáo những vấn đề hiệu suất
    - Gợi ý cải thiện hiệu suất
    """

    def __init__(
        self,
        app: Optional[FastAPI] = None,
        slow_endpoint_threshold: float = 1.0,  # seconds
        slow_dependency_threshold: float = 0.1,  # seconds
        sample_rate: float = 0.1,  # 10% requests
        trace_enabled: bool = True,
        detailed_tracing: bool = False,
        profile_enabled: bool = True,
        log_level: str = "INFO",
        output_dir: Optional[str] = None,
    ):
        """
        Khởi tạo API Profiler.

        Args:
            app: FastAPI app instance
            slow_endpoint_threshold: Ngưỡng endpoint chậm (giây)
            slow_dependency_threshold: Ngưỡng dependency chậm (giây)
            sample_rate: Tỷ lệ lấy mẫu (0.0-1.0)
            trace_enabled: Bật/tắt tracing
            detailed_tracing: Thu thập thông tin chi tiết hơn (chậm hơn)
            profile_enabled: Bật/tắt profiling
            log_level: Mức log (DEBUG, INFO, WARNING, ERROR)
            output_dir: Thư mục lưu trữ báo cáo
        """
        self.app = app
        self.slow_endpoint_threshold = slow_endpoint_threshold
        self.slow_dependency_threshold = slow_dependency_threshold
        self.sample_rate = sample_rate
        self.trace_enabled = trace_enabled
        self.detailed_tracing = detailed_tracing
        self.profile_enabled = profile_enabled

        # Setup logging
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger = logger

        # Data collection
        self.endpoints_data = defaultdict(list)  # {endpoint: [times]}
        self.dependency_data = defaultdict(list)  # {dependency: [times]}
        self.errors = defaultdict(list)  # {endpoint: [errors]}

        # Statistics
        self.slowest_endpoints = []
        self.slowest_dependencies = []
        self.error_rates = {}
        self.last_analysis_time = time.time()

        # Output settings
        self.output_dir = output_dir
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Register with app if provided
        if app:
            self.setup(app)

        self.logger.info(
            f"API Profiler khởi tạo với "
            f"slow_endpoint_threshold={slow_endpoint_threshold}s, "
            f"sample_rate={sample_rate*100}%, "
            f"trace_enabled={trace_enabled}"
        )

    def setup(self, app: FastAPI):
        """
        Thiết lập middleware và event handlers.

        Args:
            app: FastAPI app instance
        """
        # Thêm middleware để profile request
        app.add_middleware(APIProfilerMiddleware, profiler=self)

        # Gắn event handlers
        @app.on_event("startup")
        async def startup_profiler():
            self.logger.info("API Profiler starting up...")
            if self.profile_enabled:
                asyncio.create_task(self._periodic_analysis())

        @app.on_event("shutdown")
        async def shutdown_profiler():
            self.logger.info("API Profiler shutting down...")
            self._save_final_report()

        # Keep reference to app
        self.app = app

    async def _periodic_analysis(self):
        """Chạy phân tích hiệu suất định kỳ"""
        while True:
            await asyncio.sleep(900)  # 15 phút
            self._analyze_data()

    def _analyze_data(self):
        """Phân tích dữ liệu đã thu thập"""
        current_time = time.time()
        time_window = current_time - self.last_analysis_time

        # Skip if no data
        if not self.endpoints_data and not self.dependency_data:
            return

        # Phân tích thời gian endpoint
        self.slowest_endpoints = self._calculate_slowest_items(self.endpoints_data, 10)

        # Phân tích thời gian dependency
        self.slowest_dependencies = self._calculate_slowest_items(
            self.dependency_data, 5
        )

        # Phân tích lỗi
        self.error_rates = self._calculate_error_rates()

        # Log phân tích
        self._log_analysis_results(time_window)

        # Reset last analysis time
        self.last_analysis_time = current_time

    def _calculate_slowest_items(self, data_dict, limit):
        """Tính toán các items chậm nhất"""
        if not data_dict:
            return []

        results = []
        for name, times in data_dict.items():
            if not times:
                continue

            avg_time = statistics.mean(times)
            p95_time = (
                statistics.quantiles(times, n=20)[19]
                if len(times) >= 20
                else max(times)
            )
            p99_time = (
                statistics.quantiles(times, n=100)[99]
                if len(times) >= 100
                else max(times)
            )

            results.append(
                {
                    "name": name,
                    "avg_time": avg_time,
                    "p95_time": p95_time,
                    "p99_time": p99_time,
                    "min_time": min(times),
                    "max_time": max(times),
                    "count": len(times),
                }
            )

        # Sort by p95 time, descending
        results.sort(key=lambda x: x["p95_time"], reverse=True)
        return results[:limit]

    def _calculate_error_rates(self):
        """Tính toán tỷ lệ lỗi cho các endpoints"""
        error_rates = {}
        for endpoint, errors in self.errors.items():
            if endpoint not in self.endpoints_data:
                continue

            total_requests = len(self.endpoints_data[endpoint])
            error_count = len(errors)

            if total_requests > 0:
                error_rate = (error_count / total_requests) * 100
                error_rates[endpoint] = {
                    "error_rate": error_rate,
                    "error_count": error_count,
                    "total_requests": total_requests,
                    "common_errors": self._get_common_errors(errors),
                }

        return error_rates

    def _get_common_errors(self, errors, limit=3):
        """Lấy các lỗi phổ biến nhất"""
        if not errors:
            return []

        error_counts = defaultdict(int)
        for error in errors:
            error_type = error.get("error_type", "Unknown")
            error_counts[error_type] += 1

        # Sort by count
        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        return [
            {"type": err_type, "count": count}
            for err_type, count in sorted_errors[:limit]
        ]

    def _log_analysis_results(self, time_window):
        """Log kết quả phân tích"""
        # Log slowest endpoints
        if self.slowest_endpoints:
            self.logger.info(
                f"Top {len(self.slowest_endpoints)} endpoints chậm nhất (trong {time_window:.1f}s):"
            )
            for i, endpoint in enumerate(self.slowest_endpoints):
                self.logger.info(
                    f"{i+1}. {endpoint['name']}: "
                    f"avg={endpoint['avg_time']:.3f}s, "
                    f"p95={endpoint['p95_time']:.3f}s, "
                    f"count={endpoint['count']}"
                )

        # Log slowest dependencies
        if self.slowest_dependencies:
            self.logger.info(
                f"Top {len(self.slowest_dependencies)} dependencies chậm nhất:"
            )
            for i, dep in enumerate(self.slowest_dependencies):
                self.logger.info(
                    f"{i+1}. {dep['name']}: "
                    f"avg={dep['avg_time']:.3f}s, "
                    f"p95={dep['p95_time']:.3f}s, "
                    f"count={dep['count']}"
                )

        # Log error rates
        if self.error_rates:
            high_error_endpoints = {
                k: v for k, v in self.error_rates.items() if v["error_rate"] > 5
            }
            if high_error_endpoints:
                self.logger.warning(f"Endpoints có tỷ lệ lỗi cao (>5%):")
                for endpoint, data in high_error_endpoints.items():
                    self.logger.warning(
                        f"{endpoint}: {data['error_rate']:.1f}% "
                        f"({data['error_count']}/{data['total_requests']})"
                    )
                    for err in data["common_errors"]:
                        self.logger.warning(f"  - {err['type']}: {err['count']} lần")

    def _save_final_report(self):
        """Lưu báo cáo cuối cùng"""
        if not self.output_dir:
            return

        try:
            # Phân tích dữ liệu
            self._analyze_data()

            # Tạo báo cáo
            report = {
                "generated_at": datetime.now().isoformat(),
                "slowest_endpoints": self.slowest_endpoints,
                "slowest_dependencies": self.slowest_dependencies,
                "error_rates": self.error_rates,
                "optimization_suggestions": self._generate_optimization_suggestions(),
            }

            # Lưu báo cáo
            report_path = os.path.join(
                self.output_dir, f"api_profile_{int(time.time())}.json"
            )
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)

            self.logger.info(f"Đã lưu báo cáo API Profiler: {report_path}")

        except Exception as e:
            self.logger.error(f"Lỗi khi lưu báo cáo API Profiler: {str(e)}")

    def _generate_optimization_suggestions(self):
        """Tạo gợi ý tối ưu hóa dựa trên dữ liệu đã thu thập"""
        suggestions = []

        # Check for slow endpoints
        for endpoint in self.slowest_endpoints:
            if endpoint["p95_time"] > self.slow_endpoint_threshold:
                suggestions.append(
                    {
                        "target": endpoint["name"],
                        "issue": "Endpoint chậm",
                        "metric": f"P95 = {endpoint['p95_time']:.3f}s",
                        "suggestion": "Kiểm tra truy vấn DB và tối ưu cache cho endpoint này",
                    }
                )

        # Check for slow dependencies
        for dep in self.slowest_dependencies:
            if dep["avg_time"] > self.slow_dependency_threshold:
                suggestions.append(
                    {
                        "target": dep["name"],
                        "issue": "Dependency chậm",
                        "metric": f"Avg = {dep['avg_time']:.3f}s",
                        "suggestion": "Xem xét tối ưu hoặc cache kết quả của dependency này",
                    }
                )

        # Check for high error rates
        for endpoint, data in self.error_rates.items():
            if data["error_rate"] > 5:
                error_types = ", ".join([err["type"] for err in data["common_errors"]])
                suggestions.append(
                    {
                        "target": endpoint,
                        "issue": "Tỷ lệ lỗi cao",
                        "metric": f"{data['error_rate']:.1f}%",
                        "suggestion": f"Xử lý các lỗi {error_types} phát sinh trong endpoint này",
                    }
                )

        return suggestions

    def track_endpoint(
        self,
        endpoint: str,
        method: str,
        duration: float,
        status_code: int,
        error: Optional[Exception] = None,
    ):
        """
        Theo dõi thời gian xử lý endpoint.

        Args:
            endpoint: Đường dẫn endpoint
            method: Phương thức HTTP
            duration: Thời gian xử lý (seconds)
            status_code: Mã trạng thái HTTP
            error: Exception nếu xảy ra lỗi
        """
        # Skip nếu không bật profile hoặc không đạt sample rate
        if not self.profile_enabled or (
            self.sample_rate < 1 and random.random() > self.sample_rate
        ):
            return

        # Tạo endpoint key
        endpoint_key = f"{method} {endpoint}"

        # Lưu thời gian xử lý
        self.endpoints_data[endpoint_key].append(duration)

        # Giữ danh sách trong giới hạn hợp lý
        if len(self.endpoints_data[endpoint_key]) > 1000:
            self.endpoints_data[endpoint_key] = self.endpoints_data[endpoint_key][
                -1000:
            ]

        # Theo dõi trong Prometheus
        ENDPOINT_LATENCY.labels(
            endpoint=endpoint, method=method, status_code=str(status_code)
        ).observe(duration)

        # Ghi nhận endpoint chậm
        if duration > self.slow_endpoint_threshold:
            SLOW_ENDPOINTS_COUNTER.labels(endpoint=endpoint, method=method).inc()
            self.logger.warning(
                f"Slow endpoint: {method} {endpoint} took {duration:.3f}s "
                f"(threshold: {self.slow_endpoint_threshold}s)"
            )

        # Track errors
        if error or status_code >= 400:
            error_type = type(error).__name__ if error else f"HTTP{status_code}"

            # Add to errors collection
            self.errors[endpoint_key].append(
                {
                    "timestamp": time.time(),
                    "error_type": error_type,
                    "status_code": status_code,
                    "message": str(error) if error else None,
                }
            )

            # Giữ danh sách trong giới hạn hợp lý
            if len(self.errors[endpoint_key]) > 100:
                self.errors[endpoint_key] = self.errors[endpoint_key][-100:]

            # Prometheus counter
            ERROR_COUNTER.labels(
                endpoint=endpoint, method=method, error_type=error_type
            ).inc()

    def track_dependency(self, name: str, duration: float):
        """
        Theo dõi thời gian xử lý dependency.

        Args:
            name: Tên dependency
            duration: Thời gian xử lý (seconds)
        """
        if not self.profile_enabled or (
            self.sample_rate < 1 and random.random() > self.sample_rate
        ):
            return

        # Lưu thời gian xử lý
        self.dependency_data[name].append(duration)

        # Giữ danh sách trong giới hạn hợp lý
        if len(self.dependency_data[name]) > 1000:
            self.dependency_data[name] = self.dependency_data[name][-1000:]

        # Theo dõi trong Prometheus
        DEPENDENCY_LATENCY.labels(dependency_name=name).observe(duration)

        # Ghi nhận dependency chậm
        if duration > self.slow_dependency_threshold:
            self.logger.debug(
                f"Slow dependency: {name} took {duration:.3f}s "
                f"(threshold: {self.slow_dependency_threshold}s)"
            )

    def get_performance_report(self):
        """
        Lấy báo cáo hiệu suất.

        Returns:
            Dict chứa báo cáo hiệu suất
        """
        # Phân tích dữ liệu
        self._analyze_data()

        return {
            "generated_at": datetime.now().isoformat(),
            "slowest_endpoints": self.slowest_endpoints,
            "slowest_dependencies": self.slowest_dependencies,
            "error_rates": self.error_rates,
            "optimization_suggestions": self._generate_optimization_suggestions(),
        }

    def clear_data(self):
        """Xóa tất cả dữ liệu đã thu thập"""
        self.endpoints_data.clear()
        self.dependency_data.clear()
        self.errors.clear()
        self.slowest_endpoints = []
        self.slowest_dependencies = []
        self.error_rates = {}
        self.last_analysis_time = time.time()
        self.logger.info("Đã xóa tất cả dữ liệu API Profiler")


class APIProfilerMiddleware(BaseHTTPMiddleware):
    """Middleware để profile tất cả các requests API"""

    def __init__(self, app: FastAPI, profiler: APIProfiler):
        super().__init__(app)
        self.profiler = profiler

    async def dispatch(self, request: Request, call_next):
        # Lấy path và method
        path = request.url.path
        method = request.method

        # Bỏ qua metrics và health check endpoints
        if path in ["/metrics", "/health", "/favicon.ico"] or path.startswith(
            "/static/"
        ):
            return await call_next(request)

        # Bắt đầu đo thời gian
        start_time = time.time()
        error = None
        status_code = 200

        try:
            # Xử lý request
            response = await call_next(request)
            status_code = response.status_code
            return response

        except Exception as e:
            # Bắt lỗi
            error = e
            status_code = 500
            raise e

        finally:
            # Kết thúc đo thời gian
            duration = time.time() - start_time

            # Theo dõi endpoint
            self.profiler.track_endpoint(path, method, duration, status_code, error)


def profile_endpoint(name: Optional[str] = None):
    """
    Decorator để profile endpoint API.

    Args:
        name: Tên tùy chỉnh cho endpoint

    Returns:
        Decorated function
    """
    # Import ở đây để tránh circular import
    from app.performance.profiling.code_profiler import profile_function

    def decorator(func):

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Lấy tên endpoint
            func_name = name or func.__qualname__

            try:
                # Profile thời gian thực thi
                start_time = time.time()
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time

                # Log độ trễ
                if execution_time > 1.0:
                    logger.warning(
                        f"Endpoint {func_name} mất {execution_time:.2f}s để xử lý"
                    )
                else:
                    logger.debug(f"Endpoint {func_name}: {execution_time:.4f}s")

                # Đo lường metrics
                metrics.record_endpoint_latency(func_name, execution_time)

                return result

            except Exception as e:
                # Log và đếm lỗi
                logger.error(f"Lỗi endpoint {func_name}: {str(e)}")
                metrics.record_endpoint_error(func_name, type(e).__name__)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Tương tự như async_wrapper nhưng cho hàm đồng bộ
            func_name = name or func.__qualname__

            try:
                # Profile thời gian thực thi
                start_time = time.time()
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                # Log độ trễ
                if execution_time > 1.0:
                    logger.warning(
                        f"Endpoint {func_name} mất {execution_time:.2f}s để xử lý"
                    )
                else:
                    logger.debug(f"Endpoint {func_name}: {execution_time:.4f}s")

                # Đo lường metrics
                metrics.record_endpoint_latency(func_name, execution_time)

                return result

            except Exception as e:
                # Log và đếm lỗi
                logger.error(f"Lỗi endpoint {func_name}: {str(e)}")
                metrics.record_endpoint_error(func_name, type(e).__name__)
                raise

        # Chọn wrapper phù hợp với loại hàm
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    # Hỗ trợ @profile_endpoint và @profile_endpoint()
    if callable(name):
        func, name = name, None
        return decorator(func)

    return decorator


def profile_dependency(name: Optional[str] = None):
    """
    Decorator để profile hiệu suất dependency.

    Args:
        name: Tên dependency

    Returns:
        Decorator
    """

    def decorator(func):
        actual_name = name or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Try to get profiler from app
            profiler = None
            for app in args:
                if hasattr(app, "state") and hasattr(app.state, "profiler"):
                    profiler = app.state.profiler
                    break

            # If no profiler, call function directly
            if profiler is None:
                return await func(*args, **kwargs)

            # Start timing
            start_time = time.time()

            try:
                # Call function
                return await func(*args, **kwargs)
            finally:
                # End timing
                duration = time.time() - start_time

                # Track dependency
                profiler.track_dependency(actual_name, duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Similar to async_wrapper but for sync functions
            profiler = None
            for app in args:
                if hasattr(app, "state") and hasattr(app.state, "profiler"):
                    profiler = app.state.profiler
                    break

            if profiler is None:
                return func(*args, **kwargs)

            start_time = time.time()

            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                profiler.track_dependency(actual_name, duration)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def setup_api_profiler(
    app: FastAPI, config: Optional[Dict[str, Any]] = None
) -> APIProfiler:
    """
    Thiết lập API Profiler cho ứng dụng FastAPI.

    Args:
        app: FastAPI app
        config: Cấu hình tùy chọn

    Returns:
        APIProfiler instance
    """
    # Default config
    default_config = {
        "slow_endpoint_threshold": 1.0,
        "slow_dependency_threshold": 0.1,
        "sample_rate": 0.1,
        "trace_enabled": True,
        "detailed_tracing": settings.DEBUG if hasattr(settings, "DEBUG") else False,
        "profile_enabled": True,
        "log_level": "INFO",
        "output_dir": "logs/profiler" if os.path.exists("logs") else None,
    }

    # Merge config
    actual_config = {**default_config, **(config or {})}

    # Create profiler
    profiler = APIProfiler(app=app, **actual_config)

    # Store in app state
    app.state.profiler = profiler

    return profiler
