"""
Service quản lý cache cho trang quản trị (admin_site).

File này cung cấp các chức năng quản lý cache cho admin:
- Xem thông tin cache
- Xóa cache theo namespace, pattern, tags
- Cấu hình cache
"""

from typing import Dict, List, Any, Optional, Union
import time
import datetime

from app.cache import (
    cache_manager,
    TimeBasedStrategy,
    CacheBackendType,
    get_cache_backend,
)
from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)


class CacheManagerService:
    """
    Service quản lý cache cho admin.

    Cung cấp các chức năng:
    - Xem thông tin cache
    - Xóa cache theo namespace, pattern, tags
    - Cấu hình cache
    """

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Lấy thống kê về cache.

        Returns:
            Dict thông tin thống kê
        """
        stats = {
            "time": datetime.datetime.now().isoformat(),
            "backend": settings.CACHE_BACKEND,
            "stats": {},
            "namespaces": [],
        }

        # Lấy thông tin từ Redis nếu có thể
        try:
            redis_backend = await get_cache_backend("redis")
            redis_info = await redis_backend.client.info()

            # Thông tin cơ bản
            stats["stats"] = {
                "used_memory_human": redis_info.get("used_memory_human", "N/A"),
                "connected_clients": redis_info.get("connected_clients", 0),
                "uptime_in_days": redis_info.get("uptime_in_days", 0),
                "total_keys": await redis_backend.client.dbsize(),
            }

            # Lấy danh sách namespace
            cursor = b"0"
            namespaces = set()

            while cursor:
                cursor, keys = await redis_backend.client.scan(
                    cursor=cursor,
                    match=f"{settings.CACHE_KEY_PREFIX}:ns_version:*",
                    count=1000,
                )

                for key in keys:
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")

                    # Lấy tên namespace từ key
                    parts = key.split(":")
                    if len(parts) >= 3:
                        namespaces.add(parts[2])

                if cursor == b"0":
                    break

            # Lấy số lượng keys trong mỗi namespace
            for namespace in namespaces:
                # Lấy version hiện tại
                version_key = f"{settings.CACHE_KEY_PREFIX}:ns_version:{namespace}"
                version = await redis_backend.client.get(version_key)
                if version:
                    if isinstance(version, bytes):
                        version = version.decode("utf-8")

                    # Đếm số lượng keys
                    cursor = b"0"
                    count = 0
                    pattern = f"{settings.CACHE_KEY_PREFIX}:{namespace}:{version}:*"

                    while cursor:
                        cursor, keys = await redis_backend.client.scan(
                            cursor=cursor, match=pattern, count=1000
                        )
                        count += len(keys)

                        if cursor == b"0":
                            break

                    stats["namespaces"].append(
                        {"name": namespace, "version": version, "keys": count}
                    )

        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin cache: {str(e)}")
            stats["error"] = str(e)

        return stats

    async def clear_namespace(self, namespace: str) -> Dict[str, Any]:
        """
        Xóa toàn bộ cache trong namespace.

        Args:
            namespace: Tên namespace

        Returns:
            Dict kết quả
        """
        try:
            # Vô hiệu hóa namespace
            success = await cache_manager.invalidate_namespace(namespace)

            return {
                "success": success,
                "namespace": namespace,
                "message": f"Đã vô hiệu hóa namespace '{namespace}'",
            }

        except Exception as e:
            logger.error(f"Lỗi khi xóa namespace '{namespace}': {str(e)}")

            return {
                "success": False,
                "namespace": namespace,
                "message": f"Lỗi: {str(e)}",
            }

    async def clear_pattern(
        self, pattern: str, namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Xóa cache theo pattern.

        Args:
            pattern: Pattern cache key
            namespace: Tên namespace (không bắt buộc)

        Returns:
            Dict kết quả
        """
        try:
            # Xóa theo pattern
            count = await cache_manager.clear(pattern, namespace)

            return {
                "success": True,
                "pattern": pattern,
                "namespace": namespace,
                "count": count,
                "message": f"Đã xóa {count} keys theo pattern '{pattern}'",
            }

        except Exception as e:
            logger.error(f"Lỗi khi xóa pattern '{pattern}': {str(e)}")

            return {
                "success": False,
                "pattern": pattern,
                "namespace": namespace,
                "message": f"Lỗi: {str(e)}",
            }

    async def clear_tags(self, tags: List[str]) -> Dict[str, Any]:
        """
        Xóa cache theo tags.

        Args:
            tags: Danh sách tags

        Returns:
            Dict kết quả
        """
        try:
            # Xóa theo tags
            count = await cache_manager.invalidate_by_tags(tags)

            return {
                "success": True,
                "tags": tags,
                "count": count,
                "message": f"Đã xóa {count} keys theo tags '{', '.join(tags)}'",
            }

        except Exception as e:
            logger.error(f"Lỗi khi xóa tags '{tags}': {str(e)}")

            return {"success": False, "tags": tags, "message": f"Lỗi: {str(e)}"}

    async def setup_scheduled_cleanup(
        self,
        schedule_type: str,
        namespace: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        hour: int = 0,
        minute: int = 0,
        day_of_week: int = 0,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        Thiết lập lịch tự động dọn dẹp cache.

        Args:
            schedule_type: Loại lịch (daily, weekly)
            namespace: Namespace
            patterns: Danh sách patterns
            tags: Danh sách tags
            hour: Giờ (0-23)
            minute: Phút (0-59)
            day_of_week: Ngày trong tuần (0 = Thứ Hai, 6 = Chủ Nhật)
            enabled: Bật/tắt lịch

        Returns:
            Dict kết quả
        """
        try:
            # Tạo strategy theo loại lịch
            if schedule_type == "daily":
                strategy = TimeBasedStrategy.create_daily(
                    hour=hour,
                    minute=minute,
                    namespace=namespace,
                    patterns=patterns,
                    tags=tags,
                    auto_start=enabled,
                )
            elif schedule_type == "weekly":
                strategy = TimeBasedStrategy.create_weekly(
                    day_of_week=day_of_week,
                    hour=hour,
                    minute=minute,
                    namespace=namespace,
                    patterns=patterns,
                    tags=tags,
                    auto_start=enabled,
                )
            else:
                return {
                    "success": False,
                    "message": f"Loại lịch không hợp lệ: {schedule_type}",
                }

            # Lưu strategy vào registry (cần thêm registry vào TimeBasedStrategy)
            # Hoặc lưu thông tin lịch vào DB để khởi tạo lại khi restart

            return {
                "success": True,
                "schedule_type": schedule_type,
                "namespace": namespace,
                "patterns": patterns,
                "tags": tags,
                "hour": hour,
                "minute": minute,
                "day_of_week": day_of_week,
                "enabled": enabled,
                "message": f"Đã thiết lập lịch {schedule_type} dọn dẹp cache",
            }

        except Exception as e:
            logger.error(f"Lỗi khi thiết lập lịch dọn dẹp cache: {str(e)}")

            return {"success": False, "message": f"Lỗi: {str(e)}"}

    async def run_immediate_cleanup(
        self,
        namespace: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Chạy ngay lập tức việc dọn dẹp cache.

        Args:
            namespace: Namespace
            patterns: Danh sách patterns
            tags: Danh sách tags

        Returns:
            Dict kết quả
        """
        try:
            result = {
                "success": True,
                "namespace": namespace,
                "patterns": patterns,
                "tags": tags,
                "counts": {},
            }

            # Vô hiệu hóa namespace
            if namespace:
                success = await cache_manager.invalidate_namespace(namespace)
                result["counts"]["namespace"] = 1 if success else 0

            # Xóa theo patterns
            if patterns:
                pattern_count = 0
                for pattern in patterns:
                    count = await cache_manager.clear(pattern, namespace)
                    pattern_count += count
                result["counts"]["patterns"] = pattern_count

            # Xóa theo tags
            if tags:
                tag_count = await cache_manager.invalidate_by_tags(tags)
                result["counts"]["tags"] = tag_count

            # Tổng số lượng
            total = sum(result["counts"].values())
            result["message"] = f"Đã xóa tổng cộng {total} cache keys"

            return result

        except Exception as e:
            logger.error(f"Lỗi khi dọn dẹp cache: {str(e)}")

            return {"success": False, "message": f"Lỗi: {str(e)}"}
