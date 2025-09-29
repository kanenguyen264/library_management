from typing import Dict, List, Any, Optional, Union, Callable, Set, Tuple
import time
import json
import asyncio
import functools
import logging
import hashlib
from datetime import datetime, timedelta
import re
from enum import Enum, auto
import inspect

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.performance.caching_strategies.layered_cache import LayeredCache, CacheLayer
from app.performance.caching_strategies.distributed_cache import (
    DistributedCache,
    get_distributed_cache,
)

settings = get_settings()
logger = get_logger(__name__)


class InvalidationStrategy(Enum):
    """Các chiến lược vô hiệu hóa cache."""

    TIME_BASED = auto()  # Vô hiệu hóa dựa trên thời gian
    EVENT_BASED = auto()  # Vô hiệu hóa khi có sự kiện xảy ra
    PATTERN_BASED = auto()  # Vô hiệu hóa dựa trên pattern
    TAG_BASED = auto()  # Vô hiệu hóa dựa trên tags
    HYBRID = auto()  # Kết hợp nhiều chiến lược


class InvalidationManager:
    """
    Quản lý vô hiệu hóa cache thông minh.
    Cung cấp:
    - Vô hiệu hóa dựa trên tags
    - Vô hiệu hóa dựa trên pattern
    - Vô hiệu hóa theo thời gian
    - Vô hiệu hóa dựa trên sự kiện
    - Phối hợp nhiều chiến lược
    """

    def __init__(
        self,
        layered_cache: Optional[LayeredCache] = None,
        distributed_cache: Optional[DistributedCache] = None,
        default_strategy: InvalidationStrategy = InvalidationStrategy.TAG_BASED,
        default_ttl: int = 3600,  # 1 giờ
        max_event_queue_size: int = 1000,
        namespace: str = "invalidation",
    ):
        """
        Khởi tạo invalidation manager.

        Args:
            layered_cache: Layered cache instance
            distributed_cache: Distributed cache instance
            default_strategy: Chiến lược mặc định
            default_ttl: Thời gian sống mặc định (giây)
            max_event_queue_size: Kích thước tối đa của event queue
            namespace: Namespace cho invalidation
        """
        # Cache backends
        from app.performance.caching_strategies.layered_cache import (
            default_layered_cache,
        )
        from app.performance.caching_strategies.distributed_cache import (
            get_distributed_cache,
        )

        self.layered_cache = layered_cache or default_layered_cache
        self.distributed_cache = distributed_cache or get_distributed_cache()

        # Invalidation settings
        self.default_strategy = default_strategy
        self.default_ttl = default_ttl
        self.namespace = namespace

        # Event-based invalidation
        self.event_handlers = {}  # {event_name: [handlers]}
        self.event_queue = asyncio.Queue(maxsize=max_event_queue_size)
        self.event_processor_task = None

        # Pattern-based invalidation
        self.pattern_registry = {}  # {pattern: [affected_keys]}

        # Tag-based invalidation
        self.tag_registry = {}  # {tag: [affected_keys]}

        logger.info(
            f"Khởi tạo invalidation manager với strategy={default_strategy.name}, "
            f"default_ttl={default_ttl}s, namespace={namespace}"
        )

    async def invalidate_by_key(
        self, key: str, layers: CacheLayer = CacheLayer.ALL
    ) -> bool:
        """
        Vô hiệu hóa cache item bằng key.

        Args:
            key: Cache key
            layers: Các lớp cache cần vô hiệu hóa

        Returns:
            True nếu thành công
        """
        # Vô hiệu hóa trong layered cache
        await self.layered_cache.delete(key, layers=layers)

        # Thông báo các node khác
        if self.distributed_cache and layers in (CacheLayer.REDIS, CacheLayer.ALL):
            await self.distributed_cache.delete(key)

        return True

    async def invalidate_by_pattern(
        self, pattern: str, layers: CacheLayer = CacheLayer.ALL
    ) -> int:
        """
        Vô hiệu hóa cache items bằng pattern.

        Args:
            pattern: Pattern để so khớp keys
            layers: Các lớp cache cần vô hiệu hóa

        Returns:
            Số lượng keys đã vô hiệu hóa
        """
        count = 0

        # Vô hiệu hóa trong layered cache
        count += await self.layered_cache.clear(pattern, layers=layers)

        # Thông báo các node khác
        if self.distributed_cache and layers in (CacheLayer.REDIS, CacheLayer.ALL):
            count += await self.distributed_cache.clear(pattern)

        # Cập nhật pattern registry
        if pattern in self.pattern_registry:
            self.pattern_registry[pattern] = []

        return count

    async def invalidate_by_tags(
        self, tags: List[str], layers: CacheLayer = CacheLayer.ALL
    ) -> int:
        """
        Vô hiệu hóa cache items bằng tags.

        Args:
            tags: Danh sách tags
            layers: Các lớp cache cần vô hiệu hóa

        Returns:
            Số lượng keys đã vô hiệu hóa
        """
        count = 0

        # Vô hiệu hóa trong layered cache
        count += await self.layered_cache.invalidate_by_tags(tags, layers=layers)

        # Thông báo các node khác
        if self.distributed_cache and layers in (CacheLayer.REDIS, CacheLayer.ALL):
            count += await self.distributed_cache.invalidate_by_tags(tags)

        # Cập nhật tag registry
        for tag in tags:
            if tag in self.tag_registry:
                self.tag_registry[tag] = []

        return count

    async def register_event_handler(
        self, event_name: str, handler: Callable, once: bool = False
    ) -> None:
        """
        Đăng ký handler cho sự kiện.

        Args:
            event_name: Tên sự kiện
            handler: Hàm xử lý
            once: Chỉ thực thi một lần
        """
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []

        self.event_handlers[event_name].append((handler, once))
        logger.debug(f"Đã đăng ký handler cho sự kiện '{event_name}'")

    async def trigger_event(self, event_name: str, data: Any = None) -> int:
        """
        Kích hoạt sự kiện vô hiệu hóa.

        Args:
            event_name: Tên sự kiện
            data: Dữ liệu kèm theo

        Returns:
            Số lượng handlers được thực thi
        """
        # Thêm sự kiện vào queue
        try:
            await self.event_queue.put((event_name, data, time.time()))

            # Bắt đầu xử lý sự kiện nếu chưa
            if not self.event_processor_task or self.event_processor_task.done():
                self.event_processor_task = asyncio.create_task(self._process_events())

            return len(self.event_handlers.get(event_name, []))

        except asyncio.QueueFull:
            logger.warning(f"Event queue đầy, không thể thêm sự kiện '{event_name}'")
            return 0

    async def _process_events(self) -> None:
        """Xử lý các sự kiện trong queue."""
        try:
            while not self.event_queue.empty():
                # Lấy sự kiện từ queue
                event_name, data, timestamp = await self.event_queue.get()

                # Lấy danh sách handlers
                handlers = self.event_handlers.get(event_name, [])
                once_handlers = []

                # Thực thi handlers
                for handler, once in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event_name, data)
                        else:
                            handler(event_name, data)

                        # Đánh dấu handler chỉ thực thi một lần
                        if once:
                            once_handlers.append((handler, once))

                    except Exception as e:
                        logger.error(
                            f"Lỗi khi thực thi handler cho sự kiện '{event_name}': {str(e)}"
                        )

                # Xóa các handlers chỉ thực thi một lần
                for handler_item in once_handlers:
                    self.event_handlers[event_name].remove(handler_item)

                # Xóa event_name nếu không còn handlers
                if (
                    event_name in self.event_handlers
                    and not self.event_handlers[event_name]
                ):
                    del self.event_handlers[event_name]

                # Đánh dấu task hoàn thành
                self.event_queue.task_done()

        except Exception as e:
            logger.error(f"Lỗi trong vòng lặp xử lý sự kiện: {str(e)}")

    async def register_pattern(self, pattern: str, key: str) -> None:
        """
        Đăng ký key với pattern.

        Args:
            pattern: Pattern
            key: Cache key
        """
        if pattern not in self.pattern_registry:
            self.pattern_registry[pattern] = []

        if key not in self.pattern_registry[pattern]:
            self.pattern_registry[pattern].append(key)

    async def register_tag(self, tag: str, key: str) -> None:
        """
        Đăng ký key với tag.

        Args:
            tag: Tag
            key: Cache key
        """
        if tag not in self.tag_registry:
            self.tag_registry[tag] = []

        if key not in self.tag_registry[tag]:
            self.tag_registry[tag].append(key)

    def invalidation_decorator(
        self,
        strategy: Optional[InvalidationStrategy] = None,
        keys: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        events: Optional[List[str]] = None,
        condition: Optional[Callable] = None,
    ):
        """
        Decorator để tự động vô hiệu hóa cache.

        Args:
            strategy: Chiến lược vô hiệu hóa
            keys: Danh sách keys cần vô hiệu hóa
            patterns: Danh sách patterns cần vô hiệu hóa
            tags: Danh sách tags cần vô hiệu hóa
            events: Danh sách sự kiện cần kích hoạt
            condition: Điều kiện vô hiệu hóa

        Returns:
            Decorator
        """

        def decorator(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Thực thi hàm
                result = await func(*args, **kwargs)

                # Kiểm tra điều kiện
                if condition and not condition(result, *args, **kwargs):
                    return result

                # Xác định chiến lược
                active_strategy = strategy or self.default_strategy

                # Vô hiệu hóa dựa trên chiến lược
                if active_strategy == InvalidationStrategy.TAG_BASED:
                    if tags:
                        await self.invalidate_by_tags(tags)

                elif active_strategy == InvalidationStrategy.PATTERN_BASED:
                    if patterns:
                        for pattern in patterns:
                            await self.invalidate_by_pattern(pattern)

                elif active_strategy == InvalidationStrategy.TIME_BASED:
                    # Không cần làm gì, TTL sẽ tự động vô hiệu hóa
                    pass

                elif active_strategy == InvalidationStrategy.EVENT_BASED:
                    if events:
                        for event in events:
                            await self.trigger_event(
                                event,
                                {
                                    "func": func.__qualname__,
                                    "args": args,
                                    "kwargs": kwargs,
                                    "result": result,
                                },
                            )

                elif active_strategy == InvalidationStrategy.HYBRID:
                    # Kết hợp nhiều chiến lược

                    # 1. Vô hiệu hóa bằng keys
                    if keys:
                        for key in keys:
                            await self.invalidate_by_key(key)

                    # 2. Vô hiệu hóa bằng patterns
                    if patterns:
                        for pattern in patterns:
                            await self.invalidate_by_pattern(pattern)

                    # 3. Vô hiệu hóa bằng tags
                    if tags:
                        await self.invalidate_by_tags(tags)

                    # 4. Kích hoạt sự kiện
                    if events:
                        for event in events:
                            await self.trigger_event(
                                event,
                                {
                                    "func": func.__qualname__,
                                    "args": args,
                                    "kwargs": kwargs,
                                    "result": result,
                                },
                            )

                return result

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # For sync functions, create and run a task
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(async_wrapper(*args, **kwargs))

            # Use appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        return decorator


# Tạo singleton instance
invalidation_manager = InvalidationManager()

# Decorator tiện ích
invalidate_cache = invalidation_manager.invalidation_decorator
