from typing import Dict, List, Any, Optional, Union, Callable, Type, Set
import time
import json
import asyncio
import functools
import logging
import pickle
import hashlib
from datetime import datetime, timedelta
import redis.asyncio as redis
from enum import Enum
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.cache.factory import get_cache_backend

settings = get_settings()
logger = get_logger(__name__)


class LockAcquisitionError(Exception):
    """Lỗi khi không thể lấy lock."""

    pass


class DistributedCache:
    """
    Triển khai cache phân tán an toàn.
    Cung cấp:
    - Giải quyết race condition trong môi trường nhiều server
    - Phối hợp invalidation giữa các node
    - Distributed locking
    - Pub/Sub cho đồng bộ hóa cache
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        namespace: str = "dist_cache",
        default_ttl: int = 3600,  # 1 giờ
        lock_timeout: int = 10,  # 10 giây
        node_id: Optional[str] = None,
        pubsub_channel: Optional[str] = None,
    ):
        """
        Khởi tạo distributed cache.

        Args:
            redis_client: Redis client hoặc None để tạo mới
            namespace: Namespace để tách biệt cache keys
            default_ttl: Thời gian sống mặc định (giây)
            lock_timeout: Timeout cho distributed lock (giây)
            node_id: ID của node hiện tại
            pubsub_channel: Kênh pub/sub cho invalidation
        """
        # Cache settings
        self.namespace = namespace
        self.default_ttl = default_ttl
        self.lock_timeout = lock_timeout

        # Khởi tạo Redis client
        try:
            import asyncio

            # Nếu đã cung cấp redis_client, sử dụng luôn
            if redis_client:
                self.redis_client = redis_client
                # Tạo redis_cache từ client
                from app.cache.backends.redis import RedisBackend

                self.redis_cache = RedisBackend(
                    redis_client=self.redis_client, default_ttl=default_ttl
                )
            else:
                # Tạo mới Redis client và backend
                try:
                    # Tạo Redis client trực tiếp
                    import redis.asyncio as redis_async

                    # Kiểm tra và chuẩn bị các thiết lập Redis
                    redis_host = getattr(settings, "REDIS_HOST", "localhost")
                    redis_port = getattr(settings, "REDIS_PORT", 6379)
                    redis_password = getattr(settings, "REDIS_PASSWORD", None)

                    # Tạo Redis client
                    self.redis_client = redis_async.Redis(
                        host=redis_host,
                        port=redis_port,
                        password=redis_password,
                        decode_responses=True,
                    )

                    # Tạo cache backend từ client
                    from app.cache.backends.redis import RedisBackend

                    self.redis_cache = RedisBackend(
                        redis_client=self.redis_client, default_ttl=default_ttl
                    )
                except Exception as e:
                    logger.error(f"Không thể tạo Redis client: {str(e)}")
                    raise

        except Exception as e:
            logger.error(f"Lỗi khởi tạo Redis cache: {str(e)}")
            raise

        # Node identification
        self.node_id = (
            node_id or hashlib.md5(f"{time.time()}:{id(self)}".encode()).hexdigest()[:8]
        )

        # Pub/Sub settings
        self.pubsub_channel = pubsub_channel or f"{namespace}:invalidation"
        self.pubsub = None
        self.pubsub_task = None

        logger.info(
            f"Khởi tạo distributed cache '{namespace}' "
            f"với node_id={self.node_id}, "
            f"lock_timeout={lock_timeout}s, "
            f"pubsub_channel={self.pubsub_channel}"
        )

    def _get_key(self, key: str) -> str:
        """
        Tạo cache key với namespace.

        Args:
            key: Khóa cơ bản

        Returns:
            Cache key hoàn chỉnh
        """
        return f"{self.namespace}:{key}"

    def _get_lock_key(self, key: str) -> str:
        """
        Tạo lock key cho cache key.

        Args:
            key: Cache key

        Returns:
            Lock key
        """
        return f"{self.namespace}:lock:{key}"

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Lấy giá trị từ cache.

        Args:
            key: Cache key
            default: Giá trị mặc định nếu không tìm thấy

        Returns:
            Giá trị được cache hoặc default
        """
        cache_key = self._get_key(key)
        return await self.redis_cache.get(cache_key, default)

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
        notify: bool = True,
    ) -> bool:
        """
        Lưu giá trị vào cache.

        Args:
            key: Cache key
            value: Giá trị cần lưu
            ttl: Thời gian sống (giây)
            tags: Tags để phân loại item
            notify: Thông báo cho các node khác

        Returns:
            True nếu thành công
        """
        cache_key = self._get_key(key)
        result = await self.redis_cache.set(cache_key, value, ttl=ttl, tags=tags)

        # Thông báo cho các node khác
        if result and notify:
            await self._notify_update(key, "set")

        return result

    async def delete(self, key: str, notify: bool = True) -> bool:
        """
        Xóa item khỏi cache.

        Args:
            key: Cache key
            notify: Thông báo cho các node khác

        Returns:
            True nếu thành công
        """
        cache_key = self._get_key(key)
        result = await self.redis_cache.delete(cache_key)

        # Thông báo cho các node khác
        if result and notify:
            await self._notify_update(key, "delete")

        return result

    async def clear(self, pattern: Optional[str] = None, notify: bool = True) -> int:
        """
        Xóa tất cả các items phù hợp với pattern.

        Args:
            pattern: Pattern để so khớp keys, None để xóa tất cả
            notify: Thông báo cho các node khác

        Returns:
            Số lượng keys đã xóa
        """
        full_pattern = f"{self.namespace}:{pattern or '*'}"
        result = await self.redis_cache.clear(full_pattern)

        # Thông báo cho các node khác
        if result > 0 and notify:
            await self._notify_update(pattern or "*", "clear")

        return result

    async def invalidate_by_tags(self, tags: List[str], notify: bool = True) -> int:
        """
        Vô hiệu hóa cache dựa trên tags.

        Args:
            tags: Danh sách tags cần vô hiệu hóa
            notify: Thông báo cho các node khác

        Returns:
            Số lượng keys đã xóa
        """
        result = await self.redis_cache.invalidate_by_tags(tags)

        # Thông báo cho các node khác
        if result > 0 and notify:
            await self._notify_update(",".join(tags), "invalidate_tags")

        return result

    async def acquire_lock(self, key: str, timeout: Optional[int] = None) -> str:
        """
        Lấy distributed lock cho key.

        Args:
            key: Lock key
            timeout: Thời gian timeout (giây)

        Returns:
            Lock token nếu thành công

        Raises:
            LockAcquisitionError: Nếu không thể lấy lock
        """
        lock_key = self._get_lock_key(key)
        lock_timeout = timeout or self.lock_timeout
        lock_token = f"{self.node_id}:{time.time()}"

        # Thử lấy lock với lệnh SETNX
        acquired = await self.redis_client.set(
            lock_key, lock_token, ex=lock_timeout, nx=True
        )

        if not acquired:
            # Kiểm tra xem lock có bị treo không
            current_lock = await self.redis_client.get(lock_key)
            if current_lock:
                # Lấy thông tin về node đang giữ lock
                try:
                    lock_node = current_lock.decode().split(":", 1)[0]
                    raise LockAcquisitionError(
                        f"Không thể lấy lock cho key '{key}', "
                        f"đang bị giữ bởi node '{lock_node}'"
                    )
                except (UnicodeDecodeError, IndexError):
                    raise LockAcquisitionError(f"Không thể lấy lock cho key '{key}'")
            else:
                raise LockAcquisitionError(f"Không thể lấy lock cho key '{key}'")

        return lock_token

    async def release_lock(self, key: str, lock_token: str) -> bool:
        """
        Giải phóng distributed lock.

        Args:
            key: Lock key
            lock_token: Token nhận được khi lấy lock

        Returns:
            True nếu thành công
        """
        lock_key = self._get_lock_key(key)

        # Đảm bảo chỉ node đang giữ lock mới có thể giải phóng
        async with self.redis_client.pipeline() as pipe:
            # Lấy giá trị hiện tại và xóa nếu khớp
            pipe.get(lock_key)
            pipe.delete(lock_key)
            results = await pipe.execute()

        current_token = results[0]
        delete_result = results[1]

        if not current_token or current_token.decode() != lock_token:
            logger.warning(
                f"Cố gắng giải phóng lock '{key}' với token không hợp lệ. "
                f"Hiện tại: {current_token and current_token.decode()}, Đã cung cấp: {lock_token}"
            )
            return False

        return delete_result > 0

    async def with_lock(self, key: str, timeout: Optional[int] = None):
        """
        Context manager để thực hiện thao tác với distributed lock.

        Args:
            key: Lock key
            timeout: Thời gian timeout (giây)

        Yields:
            Context manager
        """
        lock_token = None
        try:
            # Lấy lock
            lock_token = await self.acquire_lock(key, timeout)
            yield
        finally:
            # Giải phóng lock nếu đã lấy
            if lock_token:
                await self.release_lock(key, lock_token)

    async def _notify_update(self, key: str, operation: str) -> None:
        """
        Thông báo cho các node khác về thay đổi cache.

        Args:
            key: Cache key
            operation: Loại thao tác (set, delete, clear, invalidate_tags)
        """
        if not self.redis_client:
            return

        try:
            # Chuẩn bị thông điệp
            message = {
                "operation": operation,
                "key": key,
                "node_id": self.node_id,
                "timestamp": time.time(),
            }

            # Publish thông điệp
            await self.redis_client.publish(self.pubsub_channel, json.dumps(message))

        except Exception as e:
            logger.error(f"Lỗi khi thông báo cache update: {str(e)}")

    async def start_listener(self) -> None:
        """Bắt đầu lắng nghe các thông báo invalidation từ các node khác."""
        if self.pubsub_task:
            return

        # Khởi tạo pubsub
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe(self.pubsub_channel)

        # Tạo task xử lý thông báo
        self.pubsub_task = asyncio.create_task(self._process_messages())
        logger.info(
            f"Đã bắt đầu lắng nghe thông báo cache trên kênh '{self.pubsub_channel}'"
        )

    async def stop_listener(self) -> None:
        """Dừng lắng nghe các thông báo invalidation."""
        if not self.pubsub_task:
            return

        # Hủy task
        self.pubsub_task.cancel()

        try:
            await self.pubsub_task
        except asyncio.CancelledError:
            pass

        # Đóng pubsub
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
            self.pubsub = None

        self.pubsub_task = None
        logger.info("Đã dừng lắng nghe thông báo cache")

    async def _process_messages(self) -> None:
        """Xử lý các thông báo invalidation từ Pub/Sub."""
        try:
            while True:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if not message:
                    await asyncio.sleep(0.1)
                    continue

                # Xử lý thông điệp
                try:
                    data = json.loads(message["data"])

                    # Bỏ qua thông điệp từ chính node này
                    if data.get("node_id") == self.node_id:
                        continue

                    # Xử lý thông điệp
                    operation = data.get("operation")
                    key = data.get("key")

                    if operation == "delete":
                        cache_key = self._get_key(key)
                        await self.redis_cache.delete(cache_key)
                        logger.debug(
                            f"Invalidated cache key '{key}' từ thông báo của node {data.get('node_id')}"
                        )

                    elif operation == "clear":
                        pattern = key
                        full_pattern = f"{self.namespace}:{pattern}"
                        count = await self.redis_cache.clear(full_pattern)
                        logger.debug(
                            f"Cleared {count} cache keys với pattern '{pattern}' từ thông báo của node {data.get('node_id')}"
                        )

                    elif operation == "invalidate_tags":
                        tags = key.split(",")
                        count = await self.redis_cache.invalidate_by_tags(tags)
                        logger.debug(
                            f"Invalidated {count} cache keys với tags {tags} từ thông báo của node {data.get('node_id')}"
                        )

                except Exception as e:
                    logger.error(f"Lỗi khi xử lý thông báo cache: {str(e)}")

        except asyncio.CancelledError:
            # Task bị hủy
            logger.debug("Đã dừng xử lý thông báo cache")
            raise

        except Exception as e:
            logger.error(f"Lỗi trong vòng lặp xử lý thông báo cache: {str(e)}")


# Sử dụng lazy initialization cho singleton instance
_distributed_cache_instance = None


def get_distributed_cache():
    """
    Lazy initialization cho distributed cache singleton.

    Returns:
        Singleton instance của DistributedCache
    """
    global _distributed_cache_instance

    if _distributed_cache_instance is None:
        # Kiểm tra xem Redis có được cấu hình và có thể kết nối không
        redis_available = False
        try:
            # Kiểm tra các thiết lập Redis tối thiểu
            redis_host = getattr(settings, "REDIS_HOST", None)
            redis_port = getattr(settings, "REDIS_PORT", None)

            if redis_host and redis_port:
                # Thử kết nối Redis (nhưng không block main thread)
                import redis.asyncio as redis_async
                import asyncio

                # Tạo client để test kết nối
                test_client = redis_async.Redis(
                    host=redis_host,
                    port=redis_port,
                    password=getattr(settings, "REDIS_PASSWORD", None),
                    socket_connect_timeout=1.0,  # Timeout ngắn để không làm chậm ứng dụng
                )

                # Chỉ thử kết nối nếu có sẵn event loop
                try:
                    loop = asyncio.get_running_loop()
                    # Đã có event loop, không test blocking
                    redis_available = True
                except RuntimeError:
                    # Không có event loop, có thể test blocking
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        # Thử ping Redis
                        result = loop.run_until_complete(test_client.ping())
                        redis_available = result
                        loop.close()
                    except Exception:
                        redis_available = False
        except Exception as e:
            logger.warning(f"Không thể kiểm tra kết nối Redis: {str(e)}")
            redis_available = False

        # Khởi tạo cache dựa trên kết quả kiểm tra
        if redis_available:
            try:
                logger.info("Redis khả dụng, khởi tạo DistributedCache")
                _distributed_cache_instance = DistributedCache()
            except Exception as e:
                logger.error(f"Lỗi khởi tạo DistributedCache: {str(e)}")
                redis_available = False

        # Fallback to dummy cache nếu Redis không khả dụng
        if not redis_available:
            logger.warning("Redis không khả dụng, sử dụng DummyDistributedCache")

            # Tạo một dummy class đầy đủ
            class DummyDistributedCache:
                """Dummy implementation của DistributedCache khi không thể kết nối Redis"""

                def __init__(self):
                    self.namespace = "dummy"
                    self.node_id = "dummy-node"
                    self.default_ttl = 60
                    logger.info("Đã khởi tạo DummyDistributedCache")

                # Định nghĩa tất cả các phương thức async trả về giá trị mặc định
                async def get(self, key, default=None):
                    return default

                async def set(self, key, value, ttl=None, tags=None, notify=True):
                    return False

                async def delete(self, key, notify=True):
                    return False

                async def clear(self, pattern=None, notify=True):
                    return 0

                async def invalidate_by_tags(self, tags, notify=True):
                    return 0

                async def acquire_lock(self, key, timeout=None):
                    return "dummy-lock"

                async def release_lock(self, key, lock_token):
                    return True

                # Các phương thức context manager, utility
                @asynccontextmanager
                async def with_lock(self, key, timeout=None):
                    yield

                async def start_listener(self):
                    pass

                async def stop_listener(self):
                    pass

                async def _notify_update(self, key, operation):
                    pass

                async def health_check(self):
                    return {"status": "dummy", "healthy": True}

                # Helper methods
                def _get_key(self, key):
                    return f"dummy:{key}"

                def _get_lock_key(self, key):
                    return f"dummy:lock:{key}"

            # Tạo instance của dummy cache
            _distributed_cache_instance = DummyDistributedCache()

    return _distributed_cache_instance
