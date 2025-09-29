"""
Utility functions cho caching.
Module này cung cấp các wrapper function cho cache decorators từ app.cache.decorators.
"""

from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, cast
from functools import wraps
import inspect
import hashlib
import json

from app.logging.setup import get_logger
from app.cache.decorators import cached as _cached
from app.cache.decorators import invalidate_cache as _invalidate_cache
from app.cache import get_cache

logger = get_logger(__name__)

T = TypeVar("T")


def cached(
    ttl: int = 3600,
    namespace: Optional[str] = None,
    tags: Optional[List[str]] = None,
    key_builder: Optional[Callable] = None,
    key_prefix: Optional[str] = None,
):
    """
    Decorator để cache kết quả trả về của function.
    Đây là wrapper cho cached decorator từ app.cache.decorators.

    Args:
        ttl: Thời gian cache tồn tại (giây)
        namespace: Namespace cho cache
        tags: Tags cho cache, sử dụng cho invalidation
        key_builder: Function tùy chỉnh để tạo cache key
        key_prefix: Tiền tố cho cache key

    Returns:
        Decorated function
    """
    return _cached(
        ttl=ttl,
        namespace=namespace,
        tags=tags,
        key_builder=key_builder,
        key_prefix=key_prefix,
    )


def invalidate_cache(
    namespace: Optional[str] = None,
    tags: Optional[List[str]] = None,
    pattern: Optional[str] = None,
):
    """
    Decorator để vô hiệu hóa cache khi function được gọi.
    Đây là wrapper cho invalidate_cache decorator từ app.cache.decorators.

    Args:
        namespace: Namespace của cache cần vô hiệu hóa
        tags: Tags của cache cần vô hiệu hóa
        pattern: Pattern của cache keys cần vô hiệu hóa

    Returns:
        Decorated function
    """
    # Convert single pattern to a list for compatibility with _invalidate_cache
    patterns = [pattern] if pattern is not None else None

    return _invalidate_cache(namespace=namespace, tags=tags, patterns=patterns)


async def remove_cache(
    namespace: Optional[str] = None,
    tags: Optional[List[str]] = None,
    pattern: Optional[str] = None,
    keys: Optional[List[str]] = None,
):
    """
    Xóa cache theo namespace, tags, pattern hoặc keys.

    Args:
        namespace: Namespace của cache cần xóa
        tags: Tags của cache cần xóa
        pattern: Pattern của cache keys cần xóa
        keys: Danh sách cache keys cần xóa

    Returns:
        Số lượng cache bị xóa
    """
    cache = get_cache()
    count = 0

    try:
        if keys:
            # Xóa theo keys cụ thể
            for key in keys:
                await cache.delete(key)
                count += 1
        elif pattern:
            # Xóa theo pattern
            keys_to_delete = await cache.get_keys(pattern)
            for key in keys_to_delete:
                await cache.delete(key)
                count += len(keys_to_delete)
        elif tags:
            # Xóa theo tags
            count = await cache.invalidate_tags(tags, namespace)
        elif namespace:
            # Xóa toàn bộ namespace
            count = await cache.invalidate_namespace(namespace)
        else:
            logger.warning("Không có tham số nào được cung cấp cho remove_cache")
    except Exception as e:
        logger.error(f"Lỗi khi xóa cache: {str(e)}")

    return count


def cache_key(
    *args,
    prefix: Optional[str] = None,
    namespace: Optional[str] = None,
    include_args_types: bool = False,
) -> str:
    """
    Tạo cache key từ các tham số.

    Args:
        *args: Các tham số sử dụng để tạo key
        prefix: Tiền tố cho key
        namespace: Namespace cho key
        include_args_types: Bao gồm kiểu dữ liệu trong key

    Returns:
        Cache key
    """
    # Tạo danh sách các phần
    parts = []

    # Thêm prefix
    if prefix:
        parts.append(str(prefix))

    # Thêm namespace
    if namespace:
        parts.append(str(namespace))

    # Thêm các tham số
    for arg in args:
        # Chuyển đổi tham số thành chuỗi
        if isinstance(arg, (dict, list, tuple, set)):
            # Hash cho các cấu trúc dữ liệu phức tạp
            arg_str = hashlib.md5(
                json.dumps(arg, sort_keys=True, default=str).encode()
            ).hexdigest()
        else:
            # Chuyển đổi thành chuỗi
            arg_str = str(arg)

        # Thêm kiểu dữ liệu nếu cần
        if include_args_types:
            arg_str = f"{type(arg).__name__}:{arg_str}"

        parts.append(arg_str)

    # Tạo key từ các phần
    key = ":".join(parts)

    # Nếu key quá dài, hash để rút gọn
    if len(key) > 200:
        prefix_str = ""
        if prefix:
            prefix_str += f"{prefix}:"
        if namespace:
            prefix_str += f"{namespace}:"

        # Hash phần còn lại
        hash_part = hashlib.md5(key.encode()).hexdigest()

        # Tạo key mới
        key = f"{prefix_str}{hash_part}"

    return key
