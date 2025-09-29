from typing import Optional, Dict, Any, Union
import logging
from enum import Enum

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)


class CacheBackendType(str, Enum):
    """Các loại backend cache."""

    REDIS = "redis"
    MEMORY = "memory"
    MULTI = "multi_level"
    DUMMY = "dummy"


async def get_cache_backend(backend_name: Optional[str] = None, **kwargs):
    """
    Tạo cache backend dựa trên tên.

    Args:
        backend_name: Tên backend cache
        **kwargs: Các tham số bổ sung cho backend

    Returns:
        Cache backend object
    """
    # Xác định loại backend
    backend_type = backend_name or settings.CACHE_BACKEND

    try:
        if backend_type == CacheBackendType.REDIS:
            from app.cache.backends.redis import RedisCache

            # Sử dụng redis_client từ kwargs nếu có
            redis_client = kwargs.get("redis_client", None)
            default_ttl = kwargs.get("default_ttl", settings.CACHE_DEFAULT_TTL)

            if redis_client:
                return RedisCache(
                    client=redis_client,
                    prefix=settings.CACHE_KEY_PREFIX,
                    default_ttl=default_ttl,
                )
            else:
                return RedisCache(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_CACHE_DB,
                    password=settings.REDIS_PASSWORD,
                    prefix=settings.CACHE_KEY_PREFIX,
                    default_ttl=default_ttl,
                )

        elif backend_type == CacheBackendType.MEMORY:
            from app.cache.backends.memory import MemoryCache

            default_ttl = kwargs.get("default_ttl", settings.MEMORY_CACHE_DEFAULT_TTL)
            max_size = kwargs.get("max_size", settings.MEMORY_CACHE_MAX_SIZE)

            return MemoryCache(max_size=max_size, default_ttl=default_ttl)

        elif backend_type == CacheBackendType.MULTI:
            from app.cache.backends.multi_level import MultiLevelCache
            from app.cache.backends.memory import MemoryCache
            from app.cache.backends.redis import RedisCache

            # Tạo memory cache layer
            memory_cache = MemoryCache(
                max_size=settings.MEMORY_CACHE_MAX_SIZE,
                default_ttl=settings.MEMORY_CACHE_DEFAULT_TTL,
            )

            # Tạo redis cache layer
            redis_cache = RedisCache(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_CACHE_DB,
                password=settings.REDIS_PASSWORD,
                prefix=settings.CACHE_KEY_PREFIX,
            )

            # Tạo multi-level cache
            return MultiLevelCache(memory_cache=memory_cache, redis_cache=redis_cache)

        else:
            # Dummy cache (không cache)
            from app.cache.backends.memory import MemoryCache

            logger.warning(
                f"Sử dụng dummy cache vì không tìm thấy backend '{backend_type}'"
            )
            return MemoryCache(max_size=1, default_ttl=1)  # Dummy cache

    except Exception as e:
        logger.error(f"Lỗi khi tạo cache backend '{backend_type}': {str(e)}")

        # Fallback to dummy cache
        from app.cache.backends.memory import MemoryCache

        return MemoryCache(max_size=1, default_ttl=1)  # Dummy cache
