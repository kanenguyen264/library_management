from typing import Dict, List, Any, Optional, Union, Callable, Type, TypeVar, Generic
import time
import json
import hashlib
import inspect
import asyncio
import functools
from contextlib import contextmanager
from enum import Enum, auto
import logging
from pydantic import BaseModel
import pickle
from datetime import datetime, timedelta
import redis.asyncio as redis

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.cache.backends.memory import MemoryBackend
from app.cache.backends.redis import RedisBackend
from app.cache.factory import get_cache_backend
from app.cache.keys import generate_cache_key
from app.cache.serializers import serialize_data, deserialize_data
from app.security.encryption.field_encryption import (
    encrypt_sensitive_data,
    decrypt_sensitive_data,
)
from app.monitoring.metrics.app_metrics import metrics
from prometheus_client import Histogram, Counter, Summary, CollectorRegistry, REGISTRY

settings = get_settings()
logger = get_logger(__name__)

# Generic type for caching
T = TypeVar("T")

# Singleton pattern for metrics to avoid duplicate registration
_METRICS = None


def get_cache_metrics():
    """
    Singleton pattern for cache metrics to prevent duplicate registrations
    """
    global _METRICS
    if _METRICS is None:
        _METRICS = {
            "cache_operation_time": Histogram(
                "cache_operation_time_seconds",
                "Thời gian thực hiện các thao tác cache",
                ["operation", "cache_type", "cache_layer"],
                buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1],
                registry=None,  # Don't auto-register
            ),
            "cache_hit_counter": Counter(
                "cache_hit_total",
                "Số lần cache hit",
                ["cache_type", "cache_layer"],
                registry=None,  # Don't auto-register
            ),
            "cache_miss_counter": Counter(
                "cache_miss_total",
                "Số lần cache miss",
                ["cache_type", "cache_layer"],
                registry=None,  # Don't auto-register
            ),
            "cache_size_bytes": Summary(
                "cache_size_bytes",
                "Kích thước dữ liệu cache",
                ["cache_type", "cache_layer"],
                registry=None,  # Don't auto-register
            ),
        }

        # Disable metric registration for now to avoid duplicate errors
        # If metrics are needed, they should be registered once at application startup
        # using a custom registry
        """
        # Register metrics explicitly if metrics are enabled
        if settings.METRICS_ENABLED:
            try:
                for metric in _METRICS.values():
                    REGISTRY.register(metric)
                logger.debug("Cache metrics registered successfully")
            except Exception as e:
                logger.warning(f"Failed to register cache metrics: {str(e)}")
        """

    return _METRICS


# Get metrics references
metrics_dict = get_cache_metrics()
CACHE_OPERATION_TIME = metrics_dict["cache_operation_time"]
CACHE_HIT_COUNTER = metrics_dict["cache_hit_counter"]
CACHE_MISS_COUNTER = metrics_dict["cache_miss_counter"]
CACHE_SIZE_BYTES = metrics_dict["cache_size_bytes"]


class CacheLayer(Enum):
    """Các lớp cache hỗ trợ."""

    MEMORY = auto()  # In-memory cache
    REDIS = auto()  # Redis distributed cache
    ALL = auto()  # Cả hai lớp


class CacheStrategy(Enum):
    """Các chiến lược cache hỗ trợ."""

    READ_THROUGH = auto()  # Đọc từ cache trước, nếu không có thì đọc từ nguồn
    WRITE_THROUGH = auto()  # Ghi vào cả cache và nguồn dữ liệu
    WRITE_BEHIND = auto()  # Ghi vào cache trước, ghi vào nguồn dữ liệu sau
    WRITE_AROUND = auto()  # Ghi vào nguồn dữ liệu, invalidate cache


class CacheTier(str, Enum):
    LOCAL = "local"  # In-memory trong một process
    SHARED = "shared"  # Shared memory giữa các process
    DISTRIBUTED = "distributed"  # Distributed cache (Redis)


class LayeredCache(Generic[T]):
    """
    Hệ thống cache nhiều lớp.
    Cung cấp:
    - Nhiều lớp cache (in-memory, Redis)
    - Nhiều chiến lược cache (read-through, write-through, etc.)
    - Kiểm soát TTL theo từng lớp
    - Quản lý invalidation
    """

    def __init__(
        self,
        local_cache=None,  # Lớp cache trong RAM (process)
        shared_cache=None,  # Lớp cache shared memory
        distributed_cache=None,  # Redis hoặc Memcached
        metrics_client=None,
        default_ttl: Dict[str, int] = None,
        namespace: str = "api",
        security_prefixes: List[str] = None,
        encrypt_sensitive: bool = True,
        enable_compression: bool = True,
    ):
        # Khởi tạo các lớp cache
        self.local_cache = local_cache
        self.shared_cache = shared_cache

        # Lazy load distributed cache nếu không được cung cấp
        if distributed_cache is None:
            try:
                from app.performance.caching_strategies.distributed_cache import (
                    get_distributed_cache,
                )

                self.distributed_cache = get_distributed_cache()
            except ImportError:
                logger.warning("Không thể import distributed_cache, sẽ sử dụng None")
                self.distributed_cache = None
        else:
            self.distributed_cache = distributed_cache

        self.metrics_client = metrics_client

        # TTL mặc định cho từng lớp (giây)
        self.default_ttl = default_ttl or {
            CacheTier.LOCAL: 60,  # 1 phút
            CacheTier.SHARED: 300,  # 5 phút
            CacheTier.DISTRIBUTED: 1800,  # 30 phút
        }

        # Namespace cho cache keys
        self.namespace = namespace

        # Danh sách prefixes cần mã hóa dữ liệu nhạy cảm
        self.security_prefixes = security_prefixes or [
            "user:",
            "token:",
            "auth:",
            "session:",
            "payment:",
        ]

        self.encrypt_sensitive = encrypt_sensitive
        self.enable_compression = enable_compression

        # Khởi tạo thống kê và debug
        self.stats = {tier: {"hits": 0, "misses": 0, "sets": 0} for tier in CacheTier}
        self.last_eviction_time = time.time()

        logger.info(
            f"Khởi tạo LayeredCache với {self._count_active_layers()} lớp active"
        )

    def _count_active_layers(self) -> int:
        """Đếm số lượng cache layers đã kích hoạt"""
        return sum(
            1
            for cache in [self.local_cache, self.shared_cache, self.distributed_cache]
            if cache
        )

    def _is_sensitive_key(self, key: str) -> bool:
        """Kiểm tra xem key có chứa dữ liệu nhạy cảm không"""
        return any(key.startswith(prefix) for prefix in self.security_prefixes)

    def _encrypt_value_if_needed(self, key: str, value: Any) -> Any:
        """Mã hóa giá trị nếu chứa dữ liệu nhạy cảm"""
        if not self.encrypt_sensitive or not self._is_sensitive_key(key):
            return value

        try:
            if isinstance(value, dict):
                # Mã hóa trường nhạy cảm trong dict
                return encrypt_sensitive_data(value)
            elif isinstance(value, str):
                # Mã hóa toàn bộ string
                from cryptography.fernet import Fernet

                key = settings.ENCRYPTION_KEY.encode()
                f = Fernet(key)
                return f.encrypt(value.encode()).decode()
            else:
                # Không hỗ trợ mã hóa kiểu dữ liệu này
                return value
        except Exception as e:
            logger.warning(f"Không thể mã hóa dữ liệu nhạy cảm: {str(e)}")
            return value

    def _decrypt_value_if_needed(self, key: str, value: Any) -> Any:
        """Giải mã giá trị nếu chứa dữ liệu nhạy cảm"""
        if not self.encrypt_sensitive or not self._is_sensitive_key(key):
            return value

        try:
            if isinstance(value, dict):
                # Giải mã trường nhạy cảm trong dict
                return decrypt_sensitive_data(value)
            elif isinstance(value, str):
                # Giải mã toàn bộ string
                from cryptography.fernet import Fernet

                key = settings.ENCRYPTION_KEY.encode()
                f = Fernet(key)
                return f.decrypt(value.encode()).decode()
            else:
                # Không hỗ trợ giải mã kiểu dữ liệu này
                return value
        except Exception as e:
            logger.warning(f"Không thể giải mã dữ liệu nhạy cảm: {str(e)}")
            return value

    async def get(self, key: str, default: Any = None) -> Any:
        """Lấy giá trị từ cache, đi từ lớp nhanh nhất đến chậm nhất"""
        start_time = time.time()

        # Thử lấy từ local cache (nhanh nhất)
        if self.local_cache:
            with self._time_operation("get", CacheTier.LOCAL):
                local_value = await self.local_cache.get(key)
                if local_value is not None:
                    self._track_hit(CacheTier.LOCAL)
                    return self._decrypt_value_if_needed(key, local_value)

        # Thử lấy từ shared cache
        if self.shared_cache:
            with self._time_operation("get", CacheTier.SHARED):
                shared_value = await self.shared_cache.get(key)
                if shared_value is not None:
                    self._track_hit(CacheTier.SHARED)
                    # Truyền xuống local cache
                    if self.local_cache:
                        await self.local_cache.set(
                            key, shared_value, ttl=self.default_ttl[CacheTier.LOCAL]
                        )
                    return self._decrypt_value_if_needed(key, shared_value)

        # Thử lấy từ distributed cache
        if self.distributed_cache:
            with self._time_operation("get", CacheTier.DISTRIBUTED):
                dist_value = await self.distributed_cache.get(key)
                if dist_value is not None:
                    self._track_hit(CacheTier.DISTRIBUTED)
                    # Truyền xuống các lớp thấp hơn
                    if self.shared_cache:
                        await self.shared_cache.set(
                            key, dist_value, ttl=self.default_ttl[CacheTier.SHARED]
                        )
                    if self.local_cache:
                        await self.local_cache.set(
                            key, dist_value, ttl=self.default_ttl[CacheTier.LOCAL]
                        )
                    return self._decrypt_value_if_needed(key, dist_value)

        # Không tìm thấy trong tất cả các lớp
        for tier in [t for t in CacheTier if getattr(self, f"{t.lower()}_cache")]:
            self._track_miss(tier)

        # Tính thời gian thực hiện
        duration = time.time() - start_time
        if duration > 0.1:  # Log nếu lấy cache mất >100ms
            logger.warning(f"Cache get cho key '{key}' mất {duration:.3f}s")

        return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[Dict[str, int]] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Lưu giá trị vào tất cả các lớp cache

        Args:
            key: Cache key
            value: Giá trị cần lưu
            ttl: Dictionary với thời gian sống (seconds) cho mỗi lớp
            tags: Danh sách tags để tìm kiếm/invalidate sau này

        Returns:
            True nếu thành công
        """
        if value is None:
            return False

        # Sử dụng TTL mặc định nếu không cung cấp
        if ttl is None:
            ttl = self.default_ttl

        # Mã hóa dữ liệu nhạy cảm
        secure_value = self._encrypt_value_if_needed(key, value)

        # Lưu vào distributed cache (lâu nhất)
        if self.distributed_cache:
            tier_ttl = ttl.get(
                CacheTier.DISTRIBUTED, self.default_ttl[CacheTier.DISTRIBUTED]
            )
            with self._time_operation("set", CacheTier.DISTRIBUTED):
                try:
                    success = await self.distributed_cache.set(
                        key, secure_value, ttl=tier_ttl, tags=tags
                    )
                    self._track_set(CacheTier.DISTRIBUTED)

                    # Track kích thước cache
                    serialized = serialize_data(secure_value)
                    CACHE_SIZE_BYTES.labels(
                        cache_type="redis", cache_layer="distributed"
                    ).observe(
                        len(serialized) if isinstance(serialized, (str, bytes)) else 0
                    )
                except Exception as e:
                    logger.error(f"Lỗi khi set distributed cache: {str(e)}")
                    success = False

        # Lưu vào shared cache
        if self.shared_cache:
            tier_ttl = ttl.get(CacheTier.SHARED, self.default_ttl[CacheTier.SHARED])
            with self._time_operation("set", CacheTier.SHARED):
                try:
                    await self.shared_cache.set(
                        key, secure_value, ttl=tier_ttl, tags=tags
                    )
                    self._track_set(CacheTier.SHARED)
                except Exception as e:
                    logger.error(f"Lỗi khi set shared cache: {str(e)}")

        # Lưu vào local cache (ngắn nhất)
        if self.local_cache:
            tier_ttl = ttl.get(CacheTier.LOCAL, self.default_ttl[CacheTier.LOCAL])
            with self._time_operation("set", CacheTier.LOCAL):
                try:
                    await self.local_cache.set(
                        key, secure_value, ttl=tier_ttl, tags=tags
                    )
                    self._track_set(CacheTier.LOCAL)
                except Exception as e:
                    logger.error(f"Lỗi khi set local cache: {str(e)}")

        return True

    async def delete(self, key: str) -> bool:
        """Xóa key khỏi tất cả các lớp cache"""
        success = True

        # Xóa từ local cache
        if self.local_cache:
            with self._time_operation("delete", CacheTier.LOCAL):
                try:
                    await self.local_cache.delete(key)
                except Exception as e:
                    logger.error(f"Lỗi khi xóa local cache: {str(e)}")
                    success = False

        # Xóa từ shared cache
        if self.shared_cache:
            with self._time_operation("delete", CacheTier.SHARED):
                try:
                    await self.shared_cache.delete(key)
                except Exception as e:
                    logger.error(f"Lỗi khi xóa shared cache: {str(e)}")
                    success = False

        # Xóa từ distributed cache
        if self.distributed_cache:
            with self._time_operation("delete", CacheTier.DISTRIBUTED):
                try:
                    await self.distributed_cache.delete(key)
                except Exception as e:
                    logger.error(f"Lỗi khi xóa distributed cache: {str(e)}")
                    success = False

        return success

    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate tất cả các keys có chứa một trong các tags"""
        invalidated_count = 0

        # Invalidate trong distributed cache
        if self.distributed_cache:
            with self._time_operation("invalidate_tags", CacheTier.DISTRIBUTED):
                try:
                    count = await self.distributed_cache.invalidate_by_tags(tags)
                    invalidated_count = max(invalidated_count, count)
                except Exception as e:
                    logger.error(
                        f"Lỗi khi invalidate distributed cache by tags: {str(e)}"
                    )

        # Invalidate trong shared cache
        if self.shared_cache:
            with self._time_operation("invalidate_tags", CacheTier.SHARED):
                try:
                    count = await self.shared_cache.invalidate_by_tags(tags)
                    invalidated_count = max(invalidated_count, count)
                except Exception as e:
                    logger.error(f"Lỗi khi invalidate shared cache by tags: {str(e)}")

        # Invalidate trong local cache
        if self.local_cache:
            with self._time_operation("invalidate_tags", CacheTier.LOCAL):
                try:
                    count = await self.local_cache.invalidate_by_tags(tags)
                    invalidated_count = max(invalidated_count, count)
                except Exception as e:
                    logger.error(f"Lỗi khi invalidate local cache by tags: {str(e)}")

        return invalidated_count

    async def clear_all(self) -> bool:
        """Xóa tất cả dữ liệu trong tất cả các lớp cache"""
        success = True

        # Xóa distributed cache
        if self.distributed_cache:
            with self._time_operation("clear", CacheTier.DISTRIBUTED):
                try:
                    await self.distributed_cache.clear()
                except Exception as e:
                    logger.error(f"Lỗi khi clear distributed cache: {str(e)}")
                    success = False

        # Xóa shared cache
        if self.shared_cache:
            with self._time_operation("clear", CacheTier.SHARED):
                try:
                    await self.shared_cache.clear()
                except Exception as e:
                    logger.error(f"Lỗi khi clear shared cache: {str(e)}")
                    success = False

        # Xóa local cache
        if self.local_cache:
            with self._time_operation("clear", CacheTier.LOCAL):
                try:
                    await self.local_cache.clear()
                except Exception as e:
                    logger.error(f"Lỗi khi clear local cache: {str(e)}")
                    success = False

        return success

    @contextmanager
    def _time_operation(self, operation: str, tier: CacheTier):
        """Context manager để đo thời gian thực thi các thao tác cache"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            cache_type = (
                "memory"
                if tier == CacheTier.LOCAL
                else "shared" if tier == CacheTier.SHARED else "redis"
            )

            CACHE_OPERATION_TIME.labels(
                operation=operation, cache_type=cache_type, cache_layer=tier.value
            ).observe(duration)

    def _track_hit(self, tier: CacheTier):
        """Ghi nhận cache hit"""
        self.stats[tier]["hits"] += 1
        cache_type = (
            "memory"
            if tier == CacheTier.LOCAL
            else "shared" if tier == CacheTier.SHARED else "redis"
        )
        CACHE_HIT_COUNTER.labels(cache_type=cache_type, cache_layer=tier.value).inc()

        if self.metrics_client:
            try:
                self.metrics_client.increment("cache.hit", tags={"tier": tier.value})
            except Exception:
                pass

    def _track_miss(self, tier: CacheTier):
        """Ghi nhận cache miss"""
        self.stats[tier]["misses"] += 1
        cache_type = (
            "memory"
            if tier == CacheTier.LOCAL
            else "shared" if tier == CacheTier.SHARED else "redis"
        )
        CACHE_MISS_COUNTER.labels(cache_type=cache_type, cache_layer=tier.value).inc()

        if self.metrics_client:
            try:
                self.metrics_client.increment("cache.miss", tags={"tier": tier.value})
            except Exception:
                pass

    def _track_set(self, tier: CacheTier):
        """Ghi nhận cache set"""
        self.stats[tier]["sets"] += 1

        if self.metrics_client:
            try:
                self.metrics_client.increment("cache.set", tags={"tier": tier.value})
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Lấy thống kê về cache"""
        result = {}

        for tier in CacheTier:
            tier_cache = getattr(self, f"{tier.lower()}_cache")
            if tier_cache:
                hits = self.stats[tier]["hits"]
                misses = self.stats[tier]["misses"]
                total = hits + misses
                hit_ratio = (hits / total) * 100 if total > 0 else 0

                result[tier.value] = {
                    "hits": hits,
                    "misses": misses,
                    "sets": self.stats[tier]["sets"],
                    "hit_ratio": f"{hit_ratio:.2f}%",
                }

        return result

    async def health_check(self) -> Dict[str, bool]:
        """Kiểm tra trạng thái sức khỏe của tất cả các lớp cache"""
        result = {}

        # Kiểm tra local cache
        if self.local_cache:
            try:
                test_key = f"health_check:local:{time.time()}"
                await self.local_cache.set(test_key, "ok", ttl=10)
                value = await self.local_cache.get(test_key)
                result["local"] = value == "ok"
            except Exception:
                result["local"] = False

        # Kiểm tra shared cache
        if self.shared_cache:
            try:
                test_key = f"health_check:shared:{time.time()}"
                await self.shared_cache.set(test_key, "ok", ttl=10)
                value = await self.shared_cache.get(test_key)
                result["shared"] = value == "ok"
            except Exception:
                result["shared"] = False

        # Kiểm tra distributed cache
        if self.distributed_cache:
            try:
                test_key = f"health_check:distributed:{time.time()}"
                await self.distributed_cache.set(test_key, "ok", ttl=10)
                value = await self.distributed_cache.get(test_key)
                result["distributed"] = value == "ok"
            except Exception:
                result["distributed"] = False

        return result

    def cached(
        self,
        ttl: Optional[Dict[str, int]] = None,
        key_prefix: Optional[str] = None,
        include_args: bool = True,
        invalidate_on_startup: bool = False,
        tags: Optional[List[str]] = None,
        encrypt_result: bool = False,
    ):
        """
        Decorator để cache kết quả của một hàm.

        Args:
            ttl: Thời gian sống cache cho từng lớp
            key_prefix: Tiền tố cho cache key
            include_args: Có sử dụng tham số để tạo cache key
            invalidate_on_startup: Có xóa cache khi khởi động
            tags: Danh sách tags để quản lý invalidation
            encrypt_result: Có mã hóa kết quả không

        Returns:
            Decorator function
        """

        def decorator(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Tạo cache key
                cache_key = generate_cache_key(
                    func.__module__,
                    func.__name__,
                    args[1:] if include_args and args else None,  # Bỏ qua self/cls
                    kwargs if include_args and kwargs else None,
                    prefix=key_prefix,
                )

                # Thử lấy từ cache
                cached_result = await self.get(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache hit cho '{cache_key}'")
                    return cached_result

                # Cache miss, gọi function gốc
                logger.debug(f"Cache miss cho '{cache_key}'")
                result = await func(*args, **kwargs)

                # Lưu kết quả vào cache
                if result is not None:
                    await self.set(cache_key, result, ttl=ttl, tags=tags)

                return result

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # Xác định event loop
                import asyncio

                # Tạo cache key
                cache_key = generate_cache_key(
                    func.__module__,
                    func.__name__,
                    args[1:] if include_args and args else None,  # Bỏ qua self/cls
                    kwargs if include_args and kwargs else None,
                    prefix=key_prefix,
                )

                # Sử dụng run_in_loop để tránh lỗi "event loop is already running"
                def run_in_loop(coro):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Nếu event loop đã chạy, tạo mới nếu cần
                            asyncio.create_task(coro)
                            return None
                        else:
                            return loop.run_until_complete(coro)
                    except RuntimeError:
                        # Không có event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(coro)
                        finally:
                            loop.close()

                # Thử lấy từ cache
                cached_result = run_in_loop(self.get(cache_key))
                if cached_result is not None:
                    logger.debug(f"Cache hit cho '{cache_key}'")
                    return cached_result

                # Cache miss, gọi function gốc
                logger.debug(f"Cache miss cho '{cache_key}'")
                result = func(*args, **kwargs)

                # Lưu kết quả vào cache (non-blocking)
                if result is not None:
                    run_in_loop(self.set(cache_key, result, ttl=ttl, tags=tags))

                return result

            # Sử dụng wrapper thích hợp dựa vào kiểu function
            wrapper = (
                async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
            )

            # Thêm phương thức để invalidate cache
            async def invalidate(*args, **kwargs):
                cache = self
                cache_key = generate_cache_key(
                    func.__module__,
                    func.__name__,
                    args[1:] if include_args and args else None,
                    kwargs if include_args and kwargs else None,
                    prefix=key_prefix,
                )
                await cache.delete(cache_key)

            wrapper.invalidate = invalidate
            return wrapper

        return decorator


# Tạo cache instance mặc định
default_layered_cache = LayeredCache(
    default_ttl={
        CacheTier.LOCAL: 60,  # 1 phút
        CacheTier.SHARED: 300,  # 5 phút
        CacheTier.DISTRIBUTED: 3600,  # 1 giờ
    },
    namespace="api",
)


# Decorator tiện ích - không phụ thuộc vào instance cụ thể
def cached(
    ttl: Optional[Dict[str, int]] = None,
    key_prefix: Optional[str] = None,
    include_args: bool = True,
    invalidate_on_startup: bool = False,
    tags: Optional[List[str]] = None,
    encrypt_result: bool = False,
):
    """
    Decorator để cache kết quả của một hàm.

    Args:
        ttl: Thời gian sống cache cho từng lớp
        key_prefix: Tiền tố cho cache key
        include_args: Có sử dụng tham số để tạo cache key
        invalidate_on_startup: Có xóa cache khi khởi động
        tags: Danh sách tags để quản lý invalidation
        encrypt_result: Có mã hóa kết quả không

    Returns:
        Decorator function
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Lấy cache instance (singleton)
            cache = default_layered_cache

            # Tạo cache key
            cache_key = generate_cache_key(
                func.__module__,
                func.__name__,
                args[1:] if include_args and args else None,  # Bỏ qua self/cls
                kwargs if include_args and kwargs else None,
                prefix=key_prefix,
            )

            # Thử lấy từ cache
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit cho '{cache_key}'")
                return cached_result

            # Cache miss, gọi function gốc
            logger.debug(f"Cache miss cho '{cache_key}'")
            result = await func(*args, **kwargs)

            # Lưu kết quả vào cache
            if result is not None:
                await cache.set(cache_key, result, ttl=ttl, tags=tags)

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Lấy cache instance (singleton)
            cache = default_layered_cache

            # Xác định event loop
            import asyncio

            # Tạo cache key
            cache_key = generate_cache_key(
                func.__module__,
                func.__name__,
                args[1:] if include_args and args else None,  # Bỏ qua self/cls
                kwargs if include_args and kwargs else None,
                prefix=key_prefix,
            )

            # Sử dụng run_in_loop để tránh lỗi "event loop is already running"
            def run_in_loop(coro):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Nếu event loop đã chạy, tạo mới nếu cần
                        asyncio.create_task(coro)
                        return None
                    else:
                        return loop.run_until_complete(coro)
                except RuntimeError:
                    # Không có event loop
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(coro)
                    finally:
                        loop.close()

            # Thử lấy từ cache
            cached_result = run_in_loop(cache.get(cache_key))
            if cached_result is not None:
                logger.debug(f"Cache hit cho '{cache_key}'")
                return cached_result

            # Cache miss, gọi function gốc
            logger.debug(f"Cache miss cho '{cache_key}'")
            result = func(*args, **kwargs)

            # Lưu kết quả vào cache (non-blocking)
            if result is not None:
                run_in_loop(cache.set(cache_key, result, ttl=ttl, tags=tags))

            return result

        # Sử dụng wrapper thích hợp dựa vào kiểu function
        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        # Thêm phương thức để invalidate cache
        async def invalidate(*args, **kwargs):
            cache = default_layered_cache
            cache_key = generate_cache_key(
                func.__module__,
                func.__name__,
                args[1:] if include_args and args else None,
                kwargs if include_args and kwargs else None,
                prefix=key_prefix,
            )
            await cache.delete(cache_key)

        wrapper.invalidate = invalidate
        return wrapper

    return decorator
