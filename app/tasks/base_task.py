"""
Lớp cơ sở cho các tác vụ nền

Module này định nghĩa lớp cơ sở BaseTask cho các tác vụ nền,
bao gồm các phương thức tiện ích và xử lý lỗi.
"""

import time
import functools
import traceback
from typing import Any, Callable, Dict, Optional, Type, TypeVar, cast, Union
import celery
from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.security.audit.audit_trails import log_task_success, log_task_failure

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)
celery_logger = get_task_logger(__name__)

# Generic type for task return values
T = TypeVar("T")


class BaseTask(celery.Task):
    """
    Lớp cơ sở cho các tác vụ Celery.
    Cung cấp các phương thức tiện ích và xử lý lỗi.
    """

    # Số lần thử lại tối đa
    max_retries = 3

    # Thời gian trễ giữa các lần thử lại (giây)
    default_retry_delay = 60

    # Loại lỗi sẽ thử lại
    autoretry_for = (Exception,)

    # Có bỏ qua các ngoại lệ không
    ignore_result = False

    # Ghi lại việc bắt đầu và hoàn thành tác vụ
    track_started = True

    # Loại serializer
    serializer = "json"

    # Queue mặc định
    default_queue = "default"

    # Cache kết quả task
    cache_result = False
    cache_ttl = 3600  # 1 giờ

    def __init__(self) -> None:
        """Khởi tạo task."""
        self.cache_backend = None
        if self.cache_result:
            from app.cache import cache_manager

            self.cache_backend = cache_manager

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Gọi tác vụ.
        Cung cấp wrapper để bổ sung các chức năng:
        - Đo thời gian thực thi
        - Ghi nhật ký
        - Ghi lại metrics
        - Xử lý lỗi
        """
        # Thời gian bắt đầu
        start_time = time.time()

        # Ghi nhật ký bắt đầu
        task_name = self.name or self.__class__.__name__
        celery_logger.info(f"Task {task_name} started. args={args}, kwargs={kwargs}")

        try:
            # Nếu sử dụng cache
            if self.cache_result and self.cache_backend:
                # Tạo cache key
                cache_key = f"task:{self.name}:{self._create_cache_key(args, kwargs)}"

                # Thử lấy từ cache
                cached_result = None
                try:
                    import asyncio

                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Tạo task để lấy cache
                        future = asyncio.ensure_future(
                            self.cache_backend.get(cache_key)
                        )
                        cached_result = loop.run_until_complete(future)
                    else:
                        # Khởi tạo event loop mới
                        cached_result = loop.run_until_complete(
                            self.cache_backend.get(cache_key)
                        )
                except:
                    # Lỗi khi lấy cache, bỏ qua
                    pass

                if cached_result is not None:
                    # Lấy từ cache thành công
                    celery_logger.info(
                        f"Task {task_name} cache hit. Result from cache."
                    )
                    return cached_result

            # Thực thi tác vụ thực sự
            result = super(BaseTask, self).__call__(*args, **kwargs)

            # Lưu vào cache nếu cần
            if self.cache_result and self.cache_backend and result is not None:
                try:
                    import asyncio

                    loop = asyncio.get_event_loop()
                    cache_key = (
                        f"task:{self.name}:{self._create_cache_key(args, kwargs)}"
                    )
                    if loop.is_running():
                        # Tạo task để set cache
                        asyncio.ensure_future(
                            self.cache_backend.set(
                                cache_key, result, ttl=self.cache_ttl
                            )
                        )
                    else:
                        # Khởi tạo event loop mới
                        loop.run_until_complete(
                            self.cache_backend.set(
                                cache_key, result, ttl=self.cache_ttl
                            )
                        )
                except:
                    # Lỗi khi lưu cache, bỏ qua
                    pass

            # Đo thời gian hoàn thành
            execution_time = time.time() - start_time

            # Ghi nhật ký hoàn thành
            celery_logger.info(f"Task {task_name} completed in {execution_time:.2f}s.")

            # Audit log cho task thành công
            try:
                log_task_success(
                    task_name=task_name,
                    execution_time=execution_time,
                    result=result if not isinstance(result, bytes) else "[Binary Data]",
                )
            except:
                # Lỗi khi ghi audit log, bỏ qua
                pass

            # Trả về kết quả
            return result
        except Exception as ex:
            # Đo thời gian lỗi
            execution_time = time.time() - start_time

            # Lấy traceback
            tb = traceback.format_exc()

            # Ghi nhật ký lỗi
            celery_logger.error(
                f"Task {task_name} failed after {execution_time:.2f}s. "
                f"Error: {str(ex)}. Traceback: {tb}"
            )

            # Audit log cho task thất bại
            try:
                log_task_failure(
                    task_name=task_name,
                    execution_time=execution_time,
                    error=str(ex),
                    traceback=tb,
                )
            except:
                # Lỗi khi ghi audit log, bỏ qua
                pass

            # Ném lại ngoại lệ
            raise

    def _create_cache_key(self, args: tuple, kwargs: dict) -> str:
        """
        Tạo cache key từ args và kwargs.

        Args:
            args: Các tham số positional
            kwargs: Các tham số keyword

        Returns:
            Cache key dạng string
        """
        import hashlib
        import json

        # Tạo dict từ args và kwargs
        key_data = {"args": args, "kwargs": kwargs}

        # Serialize thành JSON và tạo hash
        try:
            key_str = json.dumps(key_data, sort_keys=True)
        except:
            # Nếu không serialize được, dùng string representation
            key_str = f"{args}:{kwargs}"

        # Tạo hash
        return hashlib.md5(key_str.encode()).hexdigest()

    def on_retry(self, exc, task_id, args, kwargs, einfo) -> None:
        """
        Xử lý sự kiện retry.

        Args:
            exc: Exception gây ra retry
            task_id: ID của task
            args: Các tham số positional
            kwargs: Các tham số keyword
            einfo: Thông tin exception
        """
        task_name = self.name or self.__class__.__name__
        retry_count = self.request.retries
        max_retries = self.max_retries

        celery_logger.warning(
            f"Task {task_name} retry {retry_count}/{max_retries}. "
            f"Error: {str(exc)}. Task ID: {task_id}"
        )

        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        """
        Xử lý sự kiện thất bại.

        Args:
            exc: Exception gây ra thất bại
            task_id: ID của task
            args: Các tham số positional
            kwargs: Các tham số keyword
            einfo: Thông tin exception
        """
        task_name = self.name or self.__class__.__name__

        celery_logger.error(
            f"Task {task_name} failed permanently. "
            f"Error: {str(exc)}. Task ID: {task_id}"
        )

        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs) -> None:
        """
        Xử lý sự kiện thành công.

        Args:
            retval: Giá trị trả về
            task_id: ID của task
            args: Các tham số positional
            kwargs: Các tham số keyword
        """
        super().on_success(retval, task_id, args, kwargs)

    @classmethod
    def with_task_context(cls, **task_context):
        """
        Decorator để thêm task context.

        Args:
            **task_context: Các thông tin context

        Returns:
            Decorator
        """

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Thêm context vào kwargs
                kwargs.update(task_context)
                return func(*args, **kwargs)

            return wrapper

        return decorator
