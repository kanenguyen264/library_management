from typing import Dict, List, Any, Optional, Union, Callable, Set, Tuple
import time
import json
import asyncio
import logging
import hashlib
from datetime import datetime, timedelta
import inspect
from functools import wraps

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.cache.factory import get_cache_backend
from app.cache.serializers import serialize_data, deserialize_data
from app.cache.keys import generate_cache_key

settings = get_settings()
logger = get_logger(__name__)

# Biến để theo dõi việc đã log
_cache_manager_logged = False
_memory_backend_warning_logged = False


class CacheManager:
    """
    Quản lý cache trung tâm.
    Cung cấp:
    - Giao diện thống nhất cho các backends khác nhau
    - Các tiện ích tự động cache
    - Quản lý vô hiệu hóa cache
    """

    def __init__(
        self,
        backend_name: Optional[str] = None,
        prefix: str = "api_readingbook",
        default_ttl: int = 3600,
        global_key_version: Optional[str] = None,
    ):
        """
        Khởi tạo CacheManager.

        Args:
            backend_name: Tên backend cache
            prefix: Tiền tố cho cache keys
            default_ttl: Thời gian sống mặc định (giây)
            global_key_version: Phiên bản key toàn cục
        """
        global _cache_manager_logged

        # Cấu hình cache backend
        backend_name = backend_name or settings.CACHE_BACKEND

        # Khởi tạo cache một cách an toàn
        try:
            # Hàm helper để chạy coroutine an toàn
            def sync_get_cache_backend(name):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Nếu event loop đang chạy, không thể dùng run_until_complete
                        from app.cache.backends.memory import MemoryBackend

                        # Kiểm tra nếu MemoryBackend đã được log
                        global _memory_backend_warning_logged
                        if not globals().get("_memory_backend_warning_logged", False):
                            logger.warning(
                                "Event loop đang chạy, sử dụng MemoryBackend mặc định"
                            )
                            globals()["_memory_backend_warning_logged"] = True

                        return MemoryBackend()
                    else:
                        # Có thể chạy coroutine đồng bộ
                        return loop.run_until_complete(get_cache_backend(name))
                except RuntimeError:
                    # Không có event loop
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(get_cache_backend(name))
                    finally:
                        new_loop.close()

            # Lấy cache backend
            self.cache = sync_get_cache_backend(backend_name)

        except Exception as e:
            # Fallback to memory cache
            logger.error(f"Lỗi khởi tạo cache backend: {str(e)}, sử dụng MemoryBackend")
            from app.cache.backends.memory import MemoryBackend

            self.cache = MemoryBackend()

        # Cấu hình cache
        self.prefix = prefix
        self.default_ttl = default_ttl
        self.global_key_version = global_key_version or "v1"

        # Cache collections
        self.ns_versions = {}  # namespace versions

        # Chỉ log một lần để tránh trùng lặp
        if not _cache_manager_logged:
            logger.info(
                f"Khởi tạo CacheManager với backend='{backend_name}', "
                f"prefix='{prefix}', default_ttl={default_ttl}s"
            )
            _cache_manager_logged = True

    async def get(
        self,
        key: str,
        namespace: Optional[str] = None,
        default: Any = None,
        ttl: Optional[int] = None,
        deserialize: bool = True,
    ) -> Any:
        """
        Lấy giá trị từ cache.

        Args:
            key: Cache key
            namespace: Namespace
            default: Giá trị mặc định nếu không tìm thấy
            ttl: TTL cho cache miss (set nếu không tìm thấy)
            deserialize: Tự động deserialize dữ liệu

        Returns:
            Giá trị từ cache hoặc giá trị mặc định
        """
        try:
            # Tạo full key
            full_key = self._make_key(key, namespace)

            # Lấy giá trị từ cache
            result = await self.cache.get(full_key)

            # Xử lý cache miss
            if result is None:
                return default

            # Deserialize nếu cần
            if deserialize:
                return deserialize_data(result)

            return result

        except Exception as e:
            logger.error(f"Lỗi khi lấy cache key '{key}': {str(e)}")
            return default

    async def set(
        self,
        key: str,
        value: Any,
        namespace: Optional[str] = None,
        ttl: Optional[int] = None,
        serialize: bool = True,
        nx: bool = False,
        xx: bool = False,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Lưu giá trị vào cache.

        Args:
            key: Cache key
            value: Giá trị cần lưu
            namespace: Namespace
            ttl: Thời gian sống (giây)
            serialize: Tự động serialize dữ liệu
            nx: Chỉ set nếu key chưa tồn tại
            xx: Chỉ set nếu key đã tồn tại
            tags: Danh sách tags cho vô hiệu hóa theo nhóm

        Returns:
            True nếu thành công
        """
        try:
            # Tạo full key
            full_key = self._make_key(key, namespace)

            # Serialize nếu cần
            data = serialize_data(value) if serialize else value

            # TTL mặc định
            ttl = ttl if ttl is not None else self.default_ttl

            # Kiểm tra điều kiện nx và xx
            if nx or xx:
                exists = await self.exists(key, namespace)
                if (nx and exists) or (xx and not exists):
                    return False

            # Lưu vào cache - bỏ qua nx và xx parameters nếu backend không hỗ trợ
            try:
                success = await self.cache.set(
                    full_key, data, ttl=ttl, nx=nx, xx=xx, tags=tags
                )
            except TypeError:
                # Backend không hỗ trợ nx, xx hoặc tags
                success = await self.cache.set(full_key, data, ttl=ttl)

            # Lưu tags nếu có
            if success and tags:
                await self._save_key_tags(full_key, tags, ttl)

            return success

        except Exception as e:
            logger.error(f"Lỗi khi lưu cache key '{key}': {str(e)}")
            return False

    async def delete(self, key: str, namespace: Optional[str] = None) -> bool:
        """
        Xóa key khỏi cache.

        Args:
            key: Cache key
            namespace: Namespace

        Returns:
            True nếu thành công
        """
        try:
            # Tạo full key
            full_key = self._make_key(key, namespace)

            # Xóa key
            return await self.cache.delete(full_key)

        except Exception as e:
            logger.error(f"Lỗi khi xóa cache key '{key}': {str(e)}")
            return False

    async def exists(self, key: str, namespace: Optional[str] = None) -> bool:
        """
        Kiểm tra key có tồn tại trong cache.

        Args:
            key: Cache key
            namespace: Namespace

        Returns:
            True nếu tồn tại
        """
        try:
            # Tạo full key
            full_key = self._make_key(key, namespace)

            # Kiểm tra tồn tại
            return await self.cache.exists(full_key)

        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra cache key '{key}': {str(e)}")
            return False

    async def clear(self, pattern: str = "*", namespace: Optional[str] = None) -> int:
        """
        Xóa tất cả keys khớp với pattern.

        Args:
            pattern: Pattern glob
            namespace: Namespace

        Returns:
            Số lượng keys đã xóa
        """
        try:
            # Tạo full pattern
            if namespace:
                full_pattern = (
                    f"{self.prefix}:{namespace}:{self.global_key_version}:{pattern}"
                )
            else:
                full_pattern = f"{self.prefix}:{pattern}"

            # Xóa keys
            return await self.cache.clear(full_pattern)

        except Exception as e:
            logger.error(f"Lỗi khi xóa cache với pattern '{pattern}': {str(e)}")
            return 0

    async def touch(self, key: str, ttl: int, namespace: Optional[str] = None) -> bool:
        """
        Cập nhật TTL cho key.

        Args:
            key: Cache key
            ttl: Thời gian sống mới (giây)
            namespace: Namespace

        Returns:
            True nếu thành công
        """
        try:
            # Tạo full key
            full_key = self._make_key(key, namespace)

            # Cập nhật TTL
            return await self.cache.touch(full_key, ttl)

        except Exception as e:
            logger.error(f"Lỗi khi cập nhật TTL cho key '{key}': {str(e)}")
            return False

    async def increment(
        self,
        key: str,
        amount: int = 1,
        namespace: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> int:
        """
        Tăng giá trị số.

        Args:
            key: Cache key
            amount: Giá trị tăng
            namespace: Namespace
            ttl: TTL (chỉ áp dụng nếu key mới)

        Returns:
            Giá trị mới
        """
        try:
            # Tạo full key
            full_key = self._make_key(key, namespace)

            # TTL mặc định
            ttl = ttl if ttl is not None else self.default_ttl

            # Tăng giá trị
            return await self.cache.increment(full_key, amount, ttl)

        except Exception as e:
            logger.error(f"Lỗi khi tăng giá trị cho key '{key}': {str(e)}")
            return 0

    async def decrement(
        self,
        key: str,
        amount: int = 1,
        namespace: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> int:
        """
        Giảm giá trị số.

        Args:
            key: Cache key
            amount: Giá trị giảm
            namespace: Namespace
            ttl: TTL (chỉ áp dụng nếu key mới)

        Returns:
            Giá trị mới
        """
        try:
            # Tạo full key
            full_key = self._make_key(key, namespace)

            # TTL mặc định
            ttl = ttl if ttl is not None else self.default_ttl

            # Giảm giá trị
            return await self.cache.decrement(full_key, amount, ttl)

        except Exception as e:
            logger.error(f"Lỗi khi giảm giá trị cho key '{key}': {str(e)}")
            return 0

    async def get_many(
        self, keys: List[str], namespace: Optional[str] = None, deserialize: bool = True
    ) -> Dict[str, Any]:
        """
        Lấy nhiều giá trị từ cache.

        Args:
            keys: Danh sách cache keys
            namespace: Namespace
            deserialize: Tự động deserialize dữ liệu

        Returns:
            Dict {key: value}
        """
        try:
            # Tạo full keys
            full_keys = [self._make_key(key, namespace) for key in keys]

            # Lấy giá trị từ cache
            result = await self.cache.get_many(full_keys)

            # Map về keys gốc
            mapped_result = {}
            for i, value in enumerate(result):
                if value is not None:
                    if deserialize:
                        mapped_result[keys[i]] = deserialize_data(value)
                    else:
                        mapped_result[keys[i]] = value

            return mapped_result

        except Exception as e:
            logger.error(f"Lỗi khi lấy nhiều cache keys: {str(e)}")
            return {}

    async def set_many(
        self,
        data: Dict[str, Any],
        namespace: Optional[str] = None,
        ttl: Optional[int] = None,
        serialize: bool = True,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Lưu nhiều giá trị vào cache.

        Args:
            data: Dict {key: value}
            namespace: Namespace
            ttl: Thời gian sống (giây)
            serialize: Tự động serialize dữ liệu
            tags: Danh sách tags cho vô hiệu hóa theo nhóm

        Returns:
            True nếu thành công
        """
        try:
            # Tạo full keys và serialize dữ liệu
            full_data = {}
            for key, value in data.items():
                full_key = self._make_key(key, namespace)
                full_data[full_key] = serialize_data(value) if serialize else value

            # TTL mặc định
            ttl = ttl if ttl is not None else self.default_ttl

            # Lưu vào cache
            success = await self.cache.set_many(full_data, ttl)

            # Lưu tags nếu có
            if success and tags:
                for key in data.keys():
                    full_key = self._make_key(key, namespace)
                    await self._save_key_tags(full_key, tags, ttl)

            return success

        except Exception as e:
            logger.error(f"Lỗi khi lưu nhiều cache keys: {str(e)}")
            return False

    async def delete_many(
        self, keys: List[str], namespace: Optional[str] = None
    ) -> int:
        """
        Xóa nhiều keys khỏi cache.

        Args:
            keys: Danh sách cache keys
            namespace: Namespace

        Returns:
            Số lượng keys đã xóa
        """
        try:
            # Tạo full keys
            full_keys = [self._make_key(key, namespace) for key in keys]

            # Xóa keys
            return await self.cache.delete_many(full_keys)

        except Exception as e:
            logger.error(f"Lỗi khi xóa nhiều cache keys: {str(e)}")
            return 0

    async def invalidate_namespace(self, namespace: str) -> bool:
        """
        Vô hiệu hóa toàn bộ namespace bằng cách thay đổi version.

        Args:
            namespace: Namespace cần vô hiệu hóa

        Returns:
            True nếu thành công
        """
        try:
            # Tạo ns_key
            ns_key = f"{self.prefix}:ns_version:{namespace}"

            # Tăng version
            new_version = await self.cache.increment(ns_key, 1, self.default_ttl)

            # Cập nhật local version
            self.ns_versions[namespace] = str(new_version)

            logger.info(
                f"Đã vô hiệu hóa namespace '{namespace}', version mới: {new_version}"
            )
            return True

        except Exception as e:
            logger.error(f"Lỗi khi vô hiệu hóa namespace '{namespace}': {str(e)}")
            return False

    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """
        Vô hiệu hóa cache dựa trên tags.

        Args:
            tags: Danh sách tags

        Returns:
            Số lượng keys đã vô hiệu hóa
        """
        try:
            count = 0

            # Xử lý từng tag
            for tag in tags:
                # Lấy danh sách keys cho tag
                tag_key = f"{self.prefix}:tags:{tag}"
                keys = await self.cache.get(tag_key) or "[]"
                if isinstance(keys, bytes):
                    keys = keys.decode("utf-8")

                try:
                    key_list = json.loads(keys)
                except:
                    key_list = []

                # Xóa các keys
                if key_list:
                    count += await self.cache.delete_many(key_list)

                # Xóa tag
                await self.cache.delete(tag_key)

            return count

        except Exception as e:
            logger.error(f"Lỗi khi vô hiệu hóa cache bởi tags {tags}: {str(e)}")
            return 0

    async def _save_key_tags(self, key: str, tags: List[str], ttl: int) -> None:
        """
        Lưu liên kết giữa key và tags.

        Args:
            key: Cache key
            tags: Danh sách tags
            ttl: Thời gian sống (giây)
        """
        # Thêm key vào mỗi tag
        for tag in tags:
            tag_key = f"{self.prefix}:tags:{tag}"

            # Lấy danh sách keys hiện tại
            current_keys = await self.cache.get(tag_key) or "[]"
            if isinstance(current_keys, bytes):
                current_keys = current_keys.decode("utf-8")

            try:
                key_list = json.loads(current_keys)
            except:
                key_list = []

            # Thêm key mới nếu chưa tồn tại
            if key not in key_list:
                key_list.append(key)

            # Lưu lại
            await self.cache.set(tag_key, json.dumps(key_list), ttl)

    def _make_key(self, key: str, namespace: Optional[str] = None) -> str:
        """
        Tạo cache key đầy đủ với prefix và namespace.

        Args:
            key: Cache key
            namespace: Namespace

        Returns:
            Full cache key
        """
        if namespace:
            # Lấy namespace version
            ns_version = self.ns_versions.get(namespace)

            # Nếu chưa có trong cache cục bộ, lấy từ backend
            if ns_version is None:
                ns_key = f"{self.prefix}:ns_version:{namespace}"
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Tạo task lấy version
                    future = asyncio.ensure_future(self.cache.get(ns_key))
                    try:
                        ns_version = loop.run_until_complete(future)
                    except:
                        ns_version = "1"
                else:
                    # Gọi sync
                    ns_version = loop.run_until_complete(self.cache.get(ns_key))

                # Nếu không tìm thấy, khởi tạo
                if not ns_version:
                    ns_version = "1"
                    future = asyncio.ensure_future(
                        self.cache.set(ns_key, ns_version, self.default_ttl)
                    )
                    try:
                        loop.run_until_complete(future)
                    except:
                        pass

                # Cập nhật local cache
                self.ns_versions[namespace] = ns_version

            # Tạo full key với namespace và version
            return f"{self.prefix}:{namespace}:{ns_version}:{key}"
        else:
            # Không có namespace
            return f"{self.prefix}:{self.global_key_version}:{key}"


# Tạo singleton instance
cache_manager = CacheManager()
