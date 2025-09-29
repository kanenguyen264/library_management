import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from app.cache.serializers import serialize, deserialize
from app.logging.setup import get_logger
from app.monitoring.metrics import metrics

logger = get_logger(__name__)


class MultiLevelCache:
    """
    Cache đa tầng kết hợp memory cache và distributed cache.

    Hoạt động:
    1. Đọc từ memory cache trước
    2. Nếu miss, đọc từ distributed cache
    3. Nếu hit ở distributed, backfill vào memory cache
    4. Ghi vào cả memory và distributed cache
    """

    def __init__(
        self,
        memory_cache=None,
        distributed_cache=None,
        redis_cache=None,  # Alias for distributed_cache for compatibility
        memory_ttl_ratio: float = 0.5,  # Tỉ lệ TTL cho memory cache so với distributed
        backfill_memory: bool = True,  # Tự động fill memory cache khi miss
        write_through: bool = True,  # Ghi đồng thời vào cả hai lớp
    ):
        """
        Khởi tạo cache đa tầng.

        Args:
            memory_cache: In-memory cache backend
            distributed_cache: Distributed cache backend (Redis, etc.)
            redis_cache: Alias for distributed_cache
            memory_ttl_ratio: Tỉ lệ TTL cho memory cache so với distributed
            backfill_memory: Tự động thêm vào memory cache khi đọc từ distributed
            write_through: Ghi đồng thời vào cả hai lớp
        """
        self.memory_cache = memory_cache
        # Use redis_cache if provided, otherwise use distributed_cache
        self.distributed_cache = (
            redis_cache if redis_cache is not None else distributed_cache
        )
        self.memory_ttl_ratio = memory_ttl_ratio
        self.backfill_memory = backfill_memory
        self.write_through = write_through

        # Kiểm tra backends
        if self.memory_cache is None:
            from app.cache.backends.memory import MemoryBackend

            self.memory_cache = MemoryBackend()
            logger.info("Khởi tạo MemoryBackend mặc định cho MultiLevelCache")

        if self.distributed_cache is None:
            from app.cache.backends.redis import RedisBackend

            self.distributed_cache = RedisBackend()
            logger.info("Khởi tạo RedisBackend mặc định cho MultiLevelCache")

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Lấy giá trị từ cache.

        Args:
            key: Cache key
            default: Giá trị mặc định nếu không tìm thấy

        Returns:
            Giá trị đã cache hoặc default
        """
        # Đo thời gian truy cập
        start_time = metrics.time_cache_operation("get", "multi_level")

        try:
            # Thử lấy từ memory cache trước
            value = await self.memory_cache.get(key, None)

            if value is not None:
                # Hit ở memory cache
                metrics.track_cache_operation("get", "memory", True, 0)
                return value

            # Memory cache miss, thử lấy từ distributed cache
            value = await self.distributed_cache.get(key, default)

            if value is not None and value != default and self.backfill_memory:
                # Hit ở distributed, backfill vào memory cache
                # Sử dụng TTL ngắn hơn cho memory cache
                await self.memory_cache.set(key, value)
                metrics.track_cache_operation("get", "distributed", True, 0)
            elif value is None or value == default:
                # Miss ở cả hai lớp
                metrics.track_cache_operation("get", "distributed", False, 0)

            return value

        except Exception as e:
            logger.error(f"Lỗi khi lấy giá trị từ multi_level cache: {str(e)}")
            return default

        finally:
            # Đánh dấu kết thúc đo thời gian
            start_time.set_hit(value is not None)
            start_time.__exit__(None, None, None)

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Đặt giá trị vào cache.

        Args:
            key: Cache key
            value: Giá trị cần cache
            ttl: Thời gian sống (giây)
            tags: Danh sách tags
            metadata: Metadata bổ sung

        Returns:
            True nếu thành công, False nếu thất bại
        """
        # Đo thời gian thao tác
        start_time = metrics.time_cache_operation("set", "multi_level")

        try:
            result_distributed = True
            result_memory = True

            # Tính TTL cho memory cache
            memory_ttl = int(ttl * self.memory_ttl_ratio) if ttl is not None else None

            # Nếu write_through, ghi đồng thời vào cả hai lớp
            if self.write_through:
                # Tạo tasks cho cả hai cache
                tasks = []

                # Task cho distributed cache (Redis)
                tasks.append(
                    self.distributed_cache.set(key, value, ttl, tags, metadata)
                )

                # Task cho memory cache
                tasks.append(
                    self.memory_cache.set(key, value, memory_ttl, tags, metadata)
                )

                # Chạy đồng thời
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Kiểm tra kết quả
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        if i == 0:
                            logger.error(
                                f"Lỗi khi ghi vào distributed cache: {str(result)}"
                            )
                            result_distributed = False
                        else:
                            logger.error(f"Lỗi khi ghi vào memory cache: {str(result)}")
                            result_memory = False
                    elif i == 0:
                        result_distributed = result
                    else:
                        result_memory = result

            else:
                # Chỉ ghi vào distributed cache
                result_distributed = await self.distributed_cache.set(
                    key, value, ttl, tags, metadata
                )

                # Sau đó ghi vào memory cache với TTL ngắn hơn
                if result_distributed:
                    result_memory = await self.memory_cache.set(
                        key, value, memory_ttl, tags, metadata
                    )

            metrics.track_cache_operation("set", "distributed", result_distributed, 0)
            metrics.track_cache_operation("set", "memory", result_memory, 0)

            return result_distributed and result_memory

        except Exception as e:
            logger.error(f"Lỗi khi đặt giá trị vào multi_level cache: {str(e)}")
            return False

        finally:
            # Đánh dấu kết thúc đo thời gian
            start_time.__exit__(None, None, None)

    async def delete(self, key: str) -> bool:
        """
        Xóa giá trị khỏi cache.

        Args:
            key: Cache key

        Returns:
            True nếu thành công, False nếu thất bại
        """
        try:
            # Xóa đồng thời từ cả hai lớp
            tasks = [self.memory_cache.delete(key), self.distributed_cache.delete(key)]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Chỉ cần một trong hai thành công là được
            success = any(
                result
                for result in results
                if not isinstance(result, Exception) and result
            )

            return success

        except Exception as e:
            logger.error(f"Lỗi khi xóa giá trị khỏi multi_level cache: {str(e)}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Kiểm tra key có tồn tại trong cache không.

        Args:
            key: Cache key

        Returns:
            True nếu tồn tại, False nếu không
        """
        try:
            # Kiểm tra memory cache trước
            exists_in_memory = await self.memory_cache.exists(key)

            if exists_in_memory:
                return True

            # Kiểm tra distributed cache
            return await self.distributed_cache.exists(key)

        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra tồn tại trong multi_level cache: {str(e)}")
            return False

    async def clear(self, pattern: Optional[str] = None) -> int:
        """
        Xóa cache theo pattern.

        Args:
            pattern: Key pattern để xóa

        Returns:
            Số lượng keys đã xóa
        """
        try:
            # Xóa từ cả hai lớp
            tasks = [
                self.memory_cache.clear(pattern),
                self.distributed_cache.clear(pattern),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Tính tổng số keys đã xóa
            count = 0
            for result in results:
                if not isinstance(result, Exception):
                    count += result

            return count

        except Exception as e:
            logger.error(f"Lỗi khi xóa cache theo pattern: {str(e)}")
            return 0

    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """
        Vô hiệu hóa cache theo tags.

        Args:
            tags: Danh sách tags

        Returns:
            Số lượng keys đã vô hiệu hóa
        """
        try:
            # Vô hiệu hóa từ cả hai lớp
            tasks = [
                self.memory_cache.invalidate_by_tags(tags),
                self.distributed_cache.invalidate_by_tags(tags),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Tính tổng số keys đã vô hiệu hóa
            count = 0
            for result in results:
                if not isinstance(result, Exception):
                    count += result

            return count

        except Exception as e:
            logger.error(f"Lỗi khi vô hiệu hóa cache theo tags: {str(e)}")
            return 0
