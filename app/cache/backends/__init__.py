"""
Cache backends - Cung cấp các backend lưu trữ cache cho hệ thống.

Các backend hỗ trợ:
- Memory: Backend lưu trong bộ nhớ, phù hợp cho development
- Redis: Backend phân tán sử dụng Redis
- Multi-level: Kết hợp memory cache và distributed cache
"""

from app.cache.backends.memory import MemoryBackend
from app.cache.backends.redis import RedisBackend
from app.cache.backends.multi_level import MultiLevelCache

__all__ = ["MemoryBackend", "RedisBackend", "MultiLevelCache"]
