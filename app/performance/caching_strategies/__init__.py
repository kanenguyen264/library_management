"""
Module chiến lược cache (Caching Strategies) - Cung cấp các giải pháp cache nhiều tầng và phân tán.

Module này cung cấp:
- Layered Cache: Cache nhiều tầng (memory, redis) để tối ưu tốc độ và phân tán
- Distributed Cache: Cache phân tán với Redis để chia sẻ giữa nhiều instance
- Invalidation Strategies: Các chiến lược vô hiệu hóa cache dựa trên tag, pattern, sự kiện
"""

from app.performance.caching_strategies.layered_cache import (
    LayeredCache,
    CacheLayer,
    CacheStrategy,
    CacheTier,
    cached,
)

from app.performance.caching_strategies.distributed_cache import (
    DistributedCache,
    LockAcquisitionError,
)

from app.performance.caching_strategies.invalidation import (
    InvalidationManager,
    InvalidationStrategy,
)


# Tiện ích Factory để tạo cache instance phù hợp
def create_cache(cache_type: str = "layered", **kwargs):
    """
    Tạo instance cache với loại được chỉ định.

    Args:
        cache_type: Loại cache ("layered", "distributed", "memory")
        **kwargs: Các tham số cấu hình cho cache

    Returns:
        Cache instance
    """
    if cache_type == "layered":
        return LayeredCache(**kwargs)
    elif cache_type == "distributed":
        return DistributedCache(**kwargs)
    elif cache_type == "memory":
        # Import memory cache từ app.cache
        from app.cache.backends.memory import MemoryBackend

        return MemoryBackend(**kwargs)
    else:
        raise ValueError(f"Loại cache không hỗ trợ: {cache_type}")


# Export các components
__all__ = [
    "LayeredCache",
    "CacheLayer",
    "CacheStrategy",
    "CacheTier",
    "cached",
    "DistributedCache",
    "LockAcquisitionError",
    "InvalidationManager",
    "InvalidationStrategy",
    "create_cache",
]
