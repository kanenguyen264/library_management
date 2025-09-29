"""
Hệ thống cache - Cung cấp cơ chế cache đa tầng với nhiều backend và strategies.

Module này bao gồm:
- Backends: Các backend cache (Memory, Redis, Multi-level)
- Strategies: Các chiến lược vô hiệu hóa cache (Time-based, Event-based, Query-based)
- Decorators: Các decorator cache cho function, method, class
- Manager: Cache manager trung tâm quản lý các backend
- Keys: Các tiện ích tạo cache key
- Middleware: Middleware cache cho API responses
- Serializers: Serializer/deserializer data
"""

# Cache manager để sử dụng trong ứng dụng
from app.cache.manager import cache_manager

# Backends
from app.cache.backends.memory import MemoryBackend
from app.cache.backends.redis import RedisBackend
from app.cache.backends.multi_level import MultiLevelCache

# Strategies
from app.cache.strategies.time_based import TimeBasedStrategy
from app.cache.strategies.event_based import (
    EventBasedStrategy,
    ModelEventStrategy,
    APIEventStrategy,
    trigger_event,
    clear_on_event,
    clear_on_model_change,
)
from app.cache.strategies.query_based import (
    QueryBasedStrategy,
    SQLAlchemyQueryListener,
    setup_sqlalchemy_listener,
)

# Decorators
from app.cache.decorators import (
    cached,
    invalidate_cache,
    cache_model,
    cache_list,
    cache_paginated,
)

# Middleware
from app.cache.middleware import CacheMiddleware

# Factory
from app.cache.factory import get_cache_backend, CacheBackendType

# Key creation utilities
from app.cache.keys import (
    generate_cache_key,
    create_model_key,
    create_list_key,
    create_query_key,
    create_api_response_key,
)

# Serializers
from app.cache.serializers import serialize_data, deserialize_data, SerializationFormat


# Helper để lấy cache instance
def get_cache(namespace: str = None, ttl: int = None):
    """
    Lấy cache instance từ cache manager.

    Args:
        namespace: Namespace cho cache instance
        ttl: Time-to-live mặc định cho cache instance

    Returns:
        Instance của cache để sử dụng
    """
    if namespace:
        return cache_manager.get_scoped_cache(namespace, ttl)
    return cache_manager
