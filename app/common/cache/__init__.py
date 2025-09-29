"""
Common caching utilities.

Cung cấp các công cụ caching đơn giản có thể sử dụng trên toàn ứng dụng.
"""

from app.cache.decorators import cached, invalidate_cache

__all__ = ["cached", "invalidate_cache"]
