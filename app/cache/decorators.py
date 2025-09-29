from typing import Dict, List, Any, Optional, Union, Set, Tuple, Callable
import inspect
import asyncio
import time
import functools
import json
import hashlib
from datetime import datetime, timedelta
from functools import wraps

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.cache.manager import cache_manager
from app.cache.keys import generate_cache_key
from app.monitoring.metrics import metrics

settings = get_settings()
logger = get_logger(__name__)


def cached(
    ttl: int = 3600,  # 1 giờ
    key_prefix: Optional[str] = None,
    namespace: Optional[str] = None,
    include_args_types: bool = False,
    key_builder: Optional[Callable] = None,
    invalidate_on_startup: bool = False,
    condition: Optional[Callable] = None,
    tags: Optional[List[str]] = None,
):
    """
    Decorator để cache kết quả của hàm.

    Args:
        ttl: Thời gian sống cache (giây)
        key_prefix: Tiền tố cho cache key
        namespace: Namespace cache
        include_args_types: Bao gồm kiểu dữ liệu trong key
        key_builder: Hàm tùy chỉnh để tạo cache key
        invalidate_on_startup: Vô hiệu hóa cache khi khởi động
        condition: Hàm điều kiện để quyết định có cache hay không
        tags: Tags để vô hiệu hóa cache theo nhóm

    Returns:
        Decorator function
    """
    # Đánh dấu cache key đã được vô hiệu hóa
    invalidated_keys = set()

    def decorator(func):
        # Tên function
        func_name = func.__qualname__

        # Tiền tố mặc định
        prefix = key_prefix or func_name

        # Khởi tạo
        if invalidate_on_startup:
            # Vô hiệu hóa cache khi khởi động
            asyncio.create_task(cache_manager.clear(f"{prefix}:*", namespace))

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Kiểm tra điều kiện
            if condition and not condition(*args, **kwargs):
                # Không cache, gọi trực tiếp
                return await func(*args, **kwargs)

            # Tạo cache key
            if key_builder:
                # Sử dụng hàm tùy chỉnh
                cache_key = key_builder(*args, **kwargs)
            else:
                # Tạo key từ tham số
                arg_values = list(args)

                # Thêm kwargs được sắp xếp
                kwarg_values = [(k, v) for k, v in sorted(kwargs.items())]
                if kwarg_values:
                    arg_values.append(kwarg_values)

                # Tạo key
                cache_key = generate_cache_key(
                    *arg_values, prefix=prefix, include_args_types=include_args_types
                )

            # Lấy từ cache
            cached_value = await cache_manager.get(cache_key, namespace)

            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value

            # Cache miss, gọi function
            result = await func(*args, **kwargs)

            # Lưu vào cache
            if result is not None:  # Không cache None
                await cache_manager.set(
                    cache_key, result, namespace=namespace, ttl=ttl, tags=tags
                )
                logger.debug(f"Cache miss: {cache_key}")

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Kiểm tra điều kiện
            if condition and not condition(*args, **kwargs):
                # Không cache, gọi trực tiếp
                return func(*args, **kwargs)

            # Tạo cache key
            if key_builder:
                # Sử dụng hàm tùy chỉnh
                cache_key = key_builder(*args, **kwargs)
            else:
                # Tạo key từ tham số
                arg_values = list(args)

                # Thêm kwargs được sắp xếp
                kwarg_values = [(k, v) for k, v in sorted(kwargs.items())]
                if kwarg_values:
                    arg_values.append(kwarg_values)

                # Tạo key
                cache_key = generate_cache_key(
                    *arg_values, prefix=prefix, include_args_types=include_args_types
                )

            # Kiểm tra xem key đã bị vô hiệu hóa chưa
            if invalidate_on_startup and cache_key in invalidated_keys:
                # Gọi function
                result = func(*args, **kwargs)

                # Lưu vào cache
                if result is not None:  # Không cache None
                    loop = asyncio.get_event_loop()
                    loop.create_task(
                        cache_manager.set(
                            cache_key, result, namespace=namespace, ttl=ttl, tags=tags
                        )
                    )
                    invalidated_keys.remove(cache_key)

                return result

            # Lấy từ cache
            loop = asyncio.get_event_loop()
            cached_value = loop.run_until_complete(
                cache_manager.get(cache_key, namespace)
            )

            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value

            # Cache miss, gọi function
            result = func(*args, **kwargs)

            # Lưu vào cache
            if result is not None:  # Không cache None
                loop.create_task(
                    cache_manager.set(
                        cache_key, result, namespace=namespace, ttl=ttl, tags=tags
                    )
                )
                logger.debug(f"Cache miss: {cache_key}")

            return result

        # Chọn wrapper phù hợp
        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        # Thêm phương thức để vô hiệu hóa cache
        async def invalidate_cache(*args, **kwargs):
            # Tạo cache key
            if key_builder:
                # Sử dụng hàm tùy chỉnh
                cache_key = key_builder(*args, **kwargs)
            else:
                # Tạo key từ tham số
                arg_values = list(args)

                # Thêm kwargs được sắp xếp
                kwarg_values = [(k, v) for k, v in sorted(kwargs.items())]
                if kwarg_values:
                    arg_values.append(kwarg_values)

                # Tạo key
                cache_key = generate_cache_key(
                    *arg_values, prefix=prefix, include_args_types=include_args_types
                )

            # Xóa khỏi cache
            success = await cache_manager.delete(cache_key, namespace)

            # Đánh dấu đã vô hiệu hóa
            if success and invalidate_on_startup:
                invalidated_keys.add(cache_key)

            return success

        async def invalidate_all():
            # Vô hiệu hóa tất cả cache của function này
            return await cache_manager.clear(f"{prefix}:*", namespace)

        async def invalidate_by_tags():
            # Vô hiệu hóa cache dựa trên tags
            if tags:
                return await cache_manager.invalidate_by_tags(tags)
            return 0

        # Thêm các phương thức vào wrapper
        wrapper.invalidate_cache = invalidate_cache
        wrapper.invalidate_all = invalidate_all
        wrapper.invalidate_by_tags = invalidate_by_tags

        return wrapper

    return decorator


def invalidate_cache(
    namespace: Optional[str] = None,
    tags: Optional[List[str]] = None,
    patterns: Optional[List[str]] = None,
):
    """
    Decorator để vô hiệu hóa cache sau khi function được gọi.

    Args:
        namespace: Namespace cache
        tags: Tags để vô hiệu hóa
        patterns: Patterns để vô hiệu hóa

    Returns:
        Decorator function
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Gọi function gốc
            result = await func(*args, **kwargs)

            # Vô hiệu hóa cache
            if tags:
                await cache_manager.invalidate_by_tags(tags)

            if patterns:
                for pattern in patterns:
                    await cache_manager.clear(pattern, namespace)

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Gọi function gốc
            result = func(*args, **kwargs)

            # Tạo và thực thi task vô hiệu hóa cache
            loop = asyncio.get_event_loop()

            if tags:
                loop.create_task(cache_manager.invalidate_by_tags(tags))

            if patterns:
                for pattern in patterns:
                    loop.create_task(cache_manager.clear(pattern, namespace))

            return result

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def cache_model(
    ttl: int = 3600,  # 1 giờ
    namespace: Optional[str] = None,
    model_name: Optional[str] = None,
    id_field: str = "id",
    tags: Optional[List[str]] = None,
):
    """
    Decorator để cache model objects.

    Args:
        ttl: Thời gian sống cache (giây)
        namespace: Namespace cache
        model_name: Tên model (mặc định lấy từ tên class)
        id_field: Tên field ID
        tags: Tags để vô hiệu hóa cache theo nhóm

    Returns:
        Decorator function
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Gọi function gốc
            result = await func(*args, **kwargs)

            # Không cache None
            if result is None:
                return None

            # Lấy model name
            _model_name = model_name
            if not _model_name:
                # Tìm model name từ kết quả
                if hasattr(result, "__class__"):
                    _model_name = result.__class__.__name__

            # Không thể cache nếu không có model name
            if not _model_name:
                return result

            # Xây dựng cache key
            if hasattr(result, id_field):
                obj_id = getattr(result, id_field)
                cache_key = f"{_model_name.lower()}:{obj_id}"

                # Lưu vào cache
                await cache_manager.set(
                    cache_key,
                    result,
                    namespace=namespace,
                    ttl=ttl,
                    tags=tags or [_model_name.lower()],
                )

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Gọi function gốc
            result = func(*args, **kwargs)

            # Không cache None
            if result is None:
                return None

            # Lấy model name
            _model_name = model_name
            if not _model_name:
                # Tìm model name từ kết quả
                if hasattr(result, "__class__"):
                    _model_name = result.__class__.__name__

            # Không thể cache nếu không có model name
            if not _model_name:
                return result

            # Xây dựng cache key
            if hasattr(result, id_field):
                obj_id = getattr(result, id_field)
                cache_key = f"{_model_name.lower()}:{obj_id}"

                # Lưu vào cache
                loop = asyncio.get_event_loop()
                loop.create_task(
                    cache_manager.set(
                        cache_key,
                        result,
                        namespace=namespace,
                        ttl=ttl,
                        tags=tags or [_model_name.lower()],
                    )
                )

            return result

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def cache_list(
    ttl: int = 1800,  # 30 phút
    namespace: Optional[str] = None,
    key_builder: Optional[Callable] = None,
    tags: Optional[List[str]] = None,
):
    """
    Decorator để cache danh sách model objects.

    Args:
        ttl: Thời gian sống cache (giây)
        namespace: Namespace cache
        key_builder: Hàm tùy chỉnh để tạo cache key
        tags: Tags để vô hiệu hóa cache theo nhóm

    Returns:
        Decorator function
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Xây dựng cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Mặc định sử dụng tên function và kwargs
                func_name = func.__qualname__

                # Lọc các tham số có giá trị
                filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}

                # Sắp xếp kwargs để đảm bảo key nhất quán
                sorted_kwargs = sorted(filtered_kwargs.items())

                # Tạo hash từ kwargs
                kwargs_str = json.dumps(sorted_kwargs, sort_keys=True)
                kwargs_hash = hashlib.md5(kwargs_str.encode()).hexdigest()

                cache_key = f"{func_name}:{kwargs_hash}"

            # Lấy từ cache
            cached_result = await cache_manager.get(cache_key, namespace)
            if cached_result is not None:
                return cached_result

            # Không có trong cache, gọi function
            result = await func(*args, **kwargs)

            # Lưu vào cache
            if result is not None:
                await cache_manager.set(
                    cache_key, result, namespace=namespace, ttl=ttl, tags=tags
                )

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Xây dựng cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Mặc định sử dụng tên function và kwargs
                func_name = func.__qualname__

                # Lọc các tham số có giá trị
                filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}

                # Sắp xếp kwargs để đảm bảo key nhất quán
                sorted_kwargs = sorted(filtered_kwargs.items())

                # Tạo hash từ kwargs
                kwargs_str = json.dumps(sorted_kwargs, sort_keys=True)
                kwargs_hash = hashlib.md5(kwargs_str.encode()).hexdigest()

                cache_key = f"{func_name}:{kwargs_hash}"

            # Lấy từ cache
            loop = asyncio.get_event_loop()
            cached_result = loop.run_until_complete(
                cache_manager.get(cache_key, namespace)
            )

            if cached_result is not None:
                return cached_result

            # Không có trong cache, gọi function
            result = func(*args, **kwargs)

            # Lưu vào cache
            if result is not None:
                loop.create_task(
                    cache_manager.set(
                        cache_key, result, namespace=namespace, ttl=ttl, tags=tags
                    )
                )

            return result

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def cache_paginated(
    ttl: int = 900,  # 15 phút
    namespace: Optional[str] = None,
    key_builder: Optional[Callable] = None,
    tags: Optional[List[str]] = None,
):
    """
    Decorator để cache kết quả phân trang.

    Args:
        ttl: Thời gian sống cache (giây)
        namespace: Namespace cache
        key_builder: Hàm tùy chỉnh để tạo cache key
        tags: Tags để vô hiệu hóa cache theo nhóm

    Returns:
        Decorator function
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Lấy tham số phân trang
            page = kwargs.get("page", 1)
            limit = kwargs.get("limit", 10)

            # Xây dựng cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Mặc định sử dụng tên function, page, limit và các tham số khác
                func_name = func.__qualname__

                # Lọc các tham số có giá trị và không phải page, limit
                filtered_kwargs = {
                    k: v
                    for k, v in kwargs.items()
                    if v is not None and k not in ("page", "limit")
                }

                # Sắp xếp kwargs để đảm bảo key nhất quán
                sorted_kwargs = sorted(filtered_kwargs.items())

                # Tạo hash từ kwargs
                kwargs_str = json.dumps(sorted_kwargs, sort_keys=True)
                kwargs_hash = hashlib.md5(kwargs_str.encode()).hexdigest()

                cache_key = f"{func_name}:{kwargs_hash}:page{page}:limit{limit}"

            # Lấy từ cache
            cached_result = await cache_manager.get(cache_key, namespace)
            if cached_result is not None:
                return cached_result

            # Không có trong cache, gọi function
            result = await func(*args, **kwargs)

            # Lưu vào cache
            if result is not None:
                await cache_manager.set(
                    cache_key, result, namespace=namespace, ttl=ttl, tags=tags
                )

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Lấy tham số phân trang
            page = kwargs.get("page", 1)
            limit = kwargs.get("limit", 10)

            # Xây dựng cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Mặc định sử dụng tên function, page, limit và các tham số khác
                func_name = func.__qualname__

                # Lọc các tham số có giá trị và không phải page, limit
                filtered_kwargs = {
                    k: v
                    for k, v in kwargs.items()
                    if v is not None and k not in ("page", "limit")
                }

                # Sắp xếp kwargs để đảm bảo key nhất quán
                sorted_kwargs = sorted(filtered_kwargs.items())

                # Tạo hash từ kwargs
                kwargs_str = json.dumps(sorted_kwargs, sort_keys=True)
                kwargs_hash = hashlib.md5(kwargs_str.encode()).hexdigest()

                cache_key = f"{func_name}:{kwargs_hash}:page{page}:limit{limit}"

            # Lấy từ cache
            loop = asyncio.get_event_loop()
            cached_result = loop.run_until_complete(
                cache_manager.get(cache_key, namespace)
            )

            if cached_result is not None:
                return cached_result

            # Không có trong cache, gọi function
            result = func(*args, **kwargs)

            # Lưu vào cache
            if result is not None:
                loop.create_task(
                    cache_manager.set(
                        cache_key, result, namespace=namespace, ttl=ttl, tags=tags
                    )
                )

            return result

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def track_request_time(endpoint: str = None, capture_params: bool = False):
    """
    Decorator để đo thời gian xử lý request và tích hợp với APM/tracing.

    Args:
        endpoint: Endpoint path (mặc định lấy từ tên function)
        capture_params: Có capture query params không

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

            # Tạo span context để tích hợp với tracing
            span_name = f"HTTP {method} {_endpoint}"
            span_attrs = {"http.method": method, "http.endpoint": _endpoint}

            # Thêm params nếu cần
            if capture_params and hasattr(request, "query_params"):
                span_attrs["http.query_params"] = str(dict(request.query_params))

            # Đo thời gian với tích hợp tracing
            with metrics.create_span_from_metrics(
                span_name, "http_request", span_attrs
            ):
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

                    # Capture APM metric
                    metrics.capture_apm_metric(
                        f"http.response.time.{_endpoint.replace('/', '_')}",
                        time.time() - timer.start_time,
                        {"method": method, "status": str(status)},
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

            # Tạo span context để tích hợp với tracing
            span_name = f"HTTP {method} {_endpoint}"
            span_attrs = {"http.method": method, "http.endpoint": _endpoint}

            # Thêm params nếu cần
            if capture_params and hasattr(request, "query_params"):
                span_attrs["http.query_params"] = str(dict(request.query_params))

            # Đo thời gian với tích hợp tracing
            with metrics.create_span_from_metrics(
                span_name, "http_request", span_attrs
            ):
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

                    # Capture APM metric
                    metrics.capture_apm_metric(
                        f"http.response.time.{_endpoint.replace('/', '_')}",
                        time.time() - timer.start_time,
                        {"method": method, "status": str(status)},
                    )

            return response

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def cache_response(
    ttl: int = 60,  # Default 60 seconds
    key_prefix: Optional[str] = None,
    namespace: Optional[str] = None,
    include_query_params: bool = True,
    include_user_id: bool = False,
    vary_by_headers: Optional[List[str]] = None,
    vary_by: Optional[List[str]] = None,  # Tương thích ngược với vary_by_headers
    skip_cache_for_status: Optional[List[int]] = None,
):
    """
    FastAPI route decorator để cache response.

    Args:
        ttl: Thời gian sống cache (giây)
        key_prefix: Tiền tố cho cache key
        namespace: Namespace cho cache
        include_query_params: Có bao gồm query params trong cache key
        include_user_id: Có bao gồm user_id trong cache key
        vary_by_headers: Danh sách headers để phân biệt cache
        vary_by: Tương thích ngược với vary_by_headers
        skip_cache_for_status: Danh sách status codes không cache

    Returns:
        Decorator function
    """
    if skip_cache_for_status is None:
        skip_cache_for_status = [400, 401, 403, 404, 500]

    # Sử dụng vary_by nếu vary_by_headers không được cung cấp
    actual_vary_by_headers = vary_by_headers if vary_by_headers is not None else vary_by

    def decorator(endpoint_func):
        @functools.wraps(endpoint_func)
        async def wrapper(*args, **kwargs):
            from fastapi import Request, Response
            from starlette.responses import JSONResponse

            # Tìm Request object trong args
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if request is None:
                # Nếu không tìm thấy request, gọi hàm gốc
                return await endpoint_func(*args, **kwargs)

            # Tạo cache key từ request
            method = request.method
            path = request.url.path

            # Chỉ cache GET requests
            if method.upper() != "GET":
                return await endpoint_func(*args, **kwargs)

            # Tạo cache key
            key_parts = [key_prefix or path]

            # Thêm query params nếu cần
            if include_query_params and request.query_params:
                query_dict = dict(request.query_params.items())
                query_str = "&".join(f"{k}={v}" for k, v in sorted(query_dict.items()))
                key_parts.append(query_str)

            # Thêm headers nếu cần vary by headers
            if actual_vary_by_headers:
                header_parts = []
                for header in actual_vary_by_headers:
                    header_value = request.headers.get(header)
                    if header_value:
                        header_parts.append(f"{header}={header_value}")
                if header_parts:
                    key_parts.append(",".join(header_parts))

            # Thêm user_id nếu cần
            if include_user_id:
                # Tìm user_id từ request hoặc session
                user_id = None

                # Kiểm tra nếu có thuộc tính user hoặc auth
                if hasattr(request, "user") and hasattr(request.user, "id"):
                    user_id = request.user.id
                elif hasattr(request, "auth") and hasattr(request.auth, "id"):
                    user_id = request.auth.id
                elif "user_id" in request.session:
                    user_id = request.session["user_id"]

                if user_id:
                    key_parts.append(f"user={user_id}")

            # Tạo cache key
            cache_key = "response:" + ":".join(str(part) for part in key_parts)

            # Tìm cache
            cached_data = await cache_manager.get(cache_key, namespace)

            if cached_data is not None:
                # Return cached response
                headers = cached_data.get("headers", {})
                status_code = cached_data.get("status_code", 200)
                content = cached_data.get("content", {})
                return JSONResponse(
                    content=content, status_code=status_code, headers=dict(headers)
                )

            # Cache miss, gọi endpoint
            response = await endpoint_func(*args, **kwargs)

            # Không cache nếu status không cần cache
            if (
                hasattr(response, "status_code")
                and response.status_code in skip_cache_for_status
            ):
                return response

            # Cache response
            if isinstance(response, JSONResponse) or hasattr(response, "body"):
                try:
                    cache_data = {
                        "content": (
                            response.body.decode()
                            if hasattr(response, "body")
                            else response.body
                        ),
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                    }

                    # Giải mã JSON nếu nó là chuỗi
                    if isinstance(cache_data["content"], str):
                        try:
                            cache_data["content"] = json.loads(cache_data["content"])
                        except:
                            pass

                    # Lưu vào cache
                    await cache_manager.set(
                        cache_key, cache_data, namespace=namespace, ttl=ttl
                    )
                except Exception as e:
                    logger.error(f"Error caching response: {str(e)}")

            return response

        return wrapper

    return decorator


def cache_with_query_hash(ttl: int = 300, namespace: Optional[str] = None):
    """
    Decorator để cache response dựa trên hash của request body.
    Hữu ích cho các endpoint POST có request body lớn.

    Args:
        ttl: Thời gian sống cache (giây)
        namespace: Namespace cho cache

    Returns:
        Decorator function
    """

    def decorator(endpoint_func):
        @functools.wraps(endpoint_func)
        async def wrapper(*args, **kwargs):
            from fastapi import Request, Response
            from starlette.responses import JSONResponse
            import hashlib

            # Tìm Request object trong args
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if request is None:
                # Nếu không tìm thấy request, gọi hàm gốc
                return await endpoint_func(*args, **kwargs)

            # Đọc body request
            body = await request.body()

            # Tạo hash từ body
            query_hash = hashlib.md5(body).hexdigest()

            # Tạo key từ path và hash
            path = request.url.path
            key = f"response:{path}:{query_hash}"

            # Tìm trong cache
            cached_data = await cache_manager.get(key, namespace)

            if cached_data is not None:
                # Return cached response
                headers = cached_data.get("headers", {})
                status_code = cached_data.get("status_code", 200)
                content = cached_data.get("content", {})
                return JSONResponse(
                    content=content, status_code=status_code, headers=dict(headers)
                )

            # Đặt body lại vào request để endpoint có thể đọc
            await request._receive()

            # Cache miss, gọi endpoint
            response = await endpoint_func(*args, **kwargs)

            # Cache response nếu là JSONResponse
            if isinstance(response, JSONResponse):
                try:
                    cache_data = {
                        "content": response.body.decode(),
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                    }

                    # Lưu vào cache
                    await cache_manager.set(
                        key, cache_data, namespace=namespace, ttl=ttl
                    )
                except Exception as e:
                    logger.error(f"Error caching response: {str(e)}")

            return response

        return wrapper

    return decorator
