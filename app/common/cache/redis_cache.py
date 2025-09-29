"""
Redis cache decorator for function results.

Decorator để cache kết quả của các hàm, sử dụng Redis làm backend.
"""

import functools
import hashlib
import json
import time
from typing import Any, Callable, Dict, List, Optional, Union, cast
import inspect
import asyncio

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

try:
    import redis
    from redis import Redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis không được cài đặt, sử dụng memory cache thay thế")

# Tạo kết nối Redis singleton
_redis_client = None


def get_redis_client() -> Optional["Redis"]:
    """
    Lấy Redis client đã được khởi tạo sẵn.

    Returns:
        Redis client hoặc None nếu không thể kết nối
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    if not REDIS_AVAILABLE:
        return None

    try:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
        # Kiểm tra kết nối
        _redis_client.ping()
        logger.debug(
            f"Đã kết nối đến Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}"
        )
        return _redis_client
    except Exception as e:
        logger.error(f"Không thể kết nối đến Redis: {str(e)}")
        return None


def _make_cache_key(func: Callable, args: tuple, kwargs: Dict[str, Any]) -> str:
    """
    Tạo cache key từ tên hàm và tham số.

    Args:
        func: Hàm cần cache
        args: Tham số vị trí
        kwargs: Tham số từ khóa

    Returns:
        Cache key dưới dạng chuỗi
    """
    # Lấy tên module và tên hàm
    module = func.__module__
    func_name = func.__name__

    # Serialize tham số
    serialized_params = []

    # Thêm args
    for arg in args:
        try:
            serialized_params.append(str(arg))
        except Exception:
            serialized_params.append(repr(arg))

    # Thêm kwargs, được sắp xếp để đảm bảo key nhất quán
    for k in sorted(kwargs.keys()):
        try:
            serialized_params.append(f"{k}={str(kwargs[k])}")
        except Exception:
            serialized_params.append(f"{k}={repr(kwargs[k])}")

    # Tạo cache key từ tên module, tên hàm và tham số
    params_str = ",".join(serialized_params)
    cache_key = f"{module}.{func_name}:{hashlib.md5(params_str.encode()).hexdigest()}"

    return cache_key


def _serialize_result(result: Any) -> str:
    """
    Serialize kết quả thành chuỗi JSON.

    Args:
        result: Kết quả cần serialize

    Returns:
        Chuỗi JSON
    """
    try:
        return json.dumps(result)
    except Exception as e:
        logger.error(f"Không thể serialize kết quả: {str(e)}")
        return json.dumps(str(result))


def _deserialize_result(data: str) -> Any:
    """
    Deserialize chuỗi JSON thành kết quả.

    Args:
        data: Chuỗi JSON

    Returns:
        Kết quả đã deserialize
    """
    try:
        return json.loads(data)
    except Exception as e:
        logger.error(f"Không thể deserialize dữ liệu: {str(e)}")
        return data


def cached(
    ttl: int = 3600,
    prefix: str = "cache",
    invalidate_on_change: bool = False,
    key_prefix: str = None,
):
    """
    Decorator để cache kết quả của một hàm.

    Args:
        ttl: Thời gian cache (giây)
        prefix: Tiền tố cho cache key
        invalidate_on_change: Có vô hiệu hóa cache khi dữ liệu thay đổi không
        key_prefix: Tiền tố bổ sung cho cache key (tương thích ngược)

    Returns:
        Decorated function
    """
    # Nếu key_prefix được cung cấp, sử dụng key_prefix thay vì prefix
    actual_prefix = key_prefix if key_prefix is not None else prefix

    def decorator(func: Callable) -> Callable:
        # Kiểm tra xem func có phải là coroutine hay không
        is_coroutine = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            # Lấy cache client
            cache = get_redis_client()

            # Nếu không có cache client, gọi hàm trực tiếp
            if cache is None:
                return await func(*args, **kwargs)

            # Tạo cache key
            cache_key = f"{actual_prefix}:{_make_cache_key(func, args, kwargs)}"

            # Thử lấy từ cache
            try:
                cached_result = cache.get(cache_key)
                if cached_result is not None:
                    return _deserialize_result(cached_result)
            except Exception as e:
                logger.error(f"Lỗi khi lấy dữ liệu từ cache: {str(e)}")

            # Nếu không có trong cache, gọi hàm
            result = await func(*args, **kwargs)

            # Lưu kết quả vào cache
            try:
                cache.setex(cache_key, ttl, _serialize_result(result))
            except Exception as e:
                logger.error(f"Lỗi khi lưu dữ liệu vào cache: {str(e)}")

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            # Lấy cache client
            cache = get_redis_client()

            # Nếu không có cache client, gọi hàm trực tiếp
            if cache is None:
                return func(*args, **kwargs)

            # Tạo cache key
            cache_key = f"{actual_prefix}:{_make_cache_key(func, args, kwargs)}"

            # Thử lấy từ cache
            try:
                cached_result = cache.get(cache_key)
                if cached_result is not None:
                    return _deserialize_result(cached_result)
            except Exception as e:
                logger.error(f"Lỗi khi lấy dữ liệu từ cache: {str(e)}")

            # Nếu không có trong cache, gọi hàm
            result = func(*args, **kwargs)

            # Lưu kết quả vào cache
            try:
                cache.setex(cache_key, ttl, _serialize_result(result))
            except Exception as e:
                logger.error(f"Lỗi khi lưu dữ liệu vào cache: {str(e)}")

            return result

        return async_wrapper if is_coroutine else sync_wrapper

    return decorator


def invalidate_cache(keys: List[str], prefix: str = "cache") -> bool:
    """
    Vô hiệu hóa cache bằng cách xóa các key.

    Args:
        keys: Danh sách key cần xóa
        prefix: Tiền tố cho cache key

    Returns:
        True nếu thành công
    """
    cache = get_redis_client()
    if cache is None:
        return False

    # Thêm prefix
    prefixed_keys = [f"{prefix}:{key}" for key in keys]

    # Xóa các key
    try:
        if prefixed_keys:
            cache.delete(*prefixed_keys)
        return True
    except Exception as e:
        logger.error(f"Lỗi khi vô hiệu hóa cache: {str(e)}")
        return False
