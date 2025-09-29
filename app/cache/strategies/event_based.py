"""
Chiến lược vô hiệu hóa cache dựa trên các sự kiện (event).

Chiến lược này cung cấp cơ chế để vô hiệu hóa cache khi các sự kiện liên quan xảy ra,
ví dụ: khi dữ liệu gốc thay đổi, khi người dùng thực hiện các hành động cụ thể, v.v.
"""

import asyncio
from typing import (
    Dict,
    List,
    Any,
    Optional,
    Union,
    Set,
    Tuple,
    Callable,
    TypeVar,
    Generic,
)

from app.logging.setup import get_logger
from app.cache.manager import cache_manager

logger = get_logger(__name__)

# Type vars
T = TypeVar("T")
Event = str  # Event là một chuỗi định danh sự kiện


class EventDispatcher:
    """
    Dispatcher cho các sự kiện cache.
    Đây là singleton để giúp kết nối giữa các phần khác nhau của ứng dụng.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventDispatcher, cls).__new__(cls)
            cls._instance._handlers = {}
        return cls._instance

    def register_handler(self, event: Event, handler: Callable[..., Any]) -> None:
        """
        Đăng ký handler cho sự kiện.

        Args:
            event: Tên sự kiện
            handler: Hàm xử lý sự kiện
        """
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def unregister_handler(self, event: Event, handler: Callable[..., Any]) -> None:
        """
        Hủy đăng ký handler.

        Args:
            event: Tên sự kiện
            handler: Hàm xử lý sự kiện
        """
        if event in self._handlers:
            if handler in self._handlers[event]:
                self._handlers[event].remove(handler)

    async def dispatch(self, event: Event, *args, **kwargs) -> None:
        """
        Kích hoạt sự kiện.

        Args:
            event: Tên sự kiện
            *args, **kwargs: Tham số cho handlers
        """
        if event in self._handlers:
            for handler in self._handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(*args, **kwargs)
                    else:
                        handler(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Lỗi khi xử lý sự kiện {event}: {str(e)}")


# Singleton instance
event_dispatcher = EventDispatcher()


class EventBasedStrategy:
    """
    Chiến lược vô hiệu hóa cache dựa trên các sự kiện.

    Cho phép vô hiệu hóa cache khi các sự kiện cụ thể xảy ra trong hệ thống.
    """

    def __init__(
        self,
        events: List[Event],
        namespace: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ):
        """
        Khởi tạo strategy vô hiệu hóa dựa trên sự kiện.

        Args:
            events: Danh sách sự kiện cần theo dõi
            namespace: Namespace cần vô hiệu hóa
            patterns: Danh sách pattern cần vô hiệu hóa
            tags: Danh sách tags cần vô hiệu hóa
        """
        self.events = events
        self.namespace = namespace
        self.patterns = patterns
        self.tags = tags

        # Đăng ký handlers
        for event in events:
            event_dispatcher.register_handler(event, self._handle_event)

    async def _handle_event(self, *args, **kwargs) -> None:
        """
        Xử lý sự kiện.

        Args:
            *args, **kwargs: Tham số từ sự kiện
        """
        # Vô hiệu hóa theo namespace
        if self.namespace:
            await cache_manager.invalidate_namespace(self.namespace)
            logger.info(f"Đã vô hiệu hóa namespace: {self.namespace}")

        # Vô hiệu hóa theo patterns
        if self.patterns:
            for pattern in self.patterns:
                count = await cache_manager.clear(pattern, self.namespace)
                logger.info(f"Đã vô hiệu hóa {count} keys theo pattern: {pattern}")

        # Vô hiệu hóa theo tags
        if self.tags:
            count = await cache_manager.invalidate_by_tags(self.tags)
            logger.info(
                f"Đã vô hiệu hóa {count} keys theo tags: {', '.join(self.tags)}"
            )

    def destroy(self) -> None:
        """
        Hủy strategy.
        """
        # Hủy đăng ký handlers
        for event in self.events:
            event_dispatcher.unregister_handler(event, self._handle_event)


class ModelEventStrategy(EventBasedStrategy):
    """
    Chiến lược vô hiệu hóa cache dựa trên các sự kiện model.

    Tự động vô hiệu hóa cache khi model thay đổi (create, update, delete).
    """

    def __init__(
        self,
        model_name: str,
        invalidate_on_create: bool = True,
        invalidate_on_update: bool = True,
        invalidate_on_delete: bool = True,
        namespace: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ):
        """
        Khởi tạo strategy vô hiệu hóa dựa trên sự kiện model.

        Args:
            model_name: Tên model
            invalidate_on_create: Vô hiệu hóa khi tạo mới
            invalidate_on_update: Vô hiệu hóa khi cập nhật
            invalidate_on_delete: Vô hiệu hóa khi xóa
            namespace: Namespace cần vô hiệu hóa
            patterns: Danh sách pattern cần vô hiệu hóa
            tags: Danh sách tags cần vô hiệu hóa
        """
        events = []

        # Xác định các sự kiện cần theo dõi
        if invalidate_on_create:
            events.append(f"{model_name}.created")
        if invalidate_on_update:
            events.append(f"{model_name}.updated")
        if invalidate_on_delete:
            events.append(f"{model_name}.deleted")

        # Mặc định, invalidate theo model tag
        if tags is None:
            tags = [model_name.lower()]

        super().__init__(
            events=events, namespace=namespace, patterns=patterns, tags=tags
        )


class APIEventStrategy(EventBasedStrategy):
    """
    Chiến lược vô hiệu hóa cache dựa trên các sự kiện API.

    Tự động vô hiệu hóa cache khi API được gọi.
    """

    def __init__(
        self,
        endpoints: List[str],
        namespace: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ):
        """
        Khởi tạo strategy vô hiệu hóa dựa trên sự kiện API.

        Args:
            endpoints: Danh sách endpoint cần theo dõi (ví dụ: ["POST /api/users", "PUT /api/users/{id}"])
            namespace: Namespace cần vô hiệu hóa
            patterns: Danh sách pattern cần vô hiệu hóa
            tags: Danh sách tags cần vô hiệu hóa
        """
        events = [f"api.{endpoint}" for endpoint in endpoints]
        super().__init__(
            events=events, namespace=namespace, patterns=patterns, tags=tags
        )


# Hàm tiện ích
async def trigger_event(event: Event, *args, **kwargs) -> None:
    """
    Kích hoạt sự kiện.

    Args:
        event: Tên sự kiện
        *args, **kwargs: Tham số cho handlers
    """
    await event_dispatcher.dispatch(event, *args, **kwargs)


def clear_on_event(
    event: Union[Event, List[Event]],
    namespace: Optional[str] = None,
    patterns: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> EventBasedStrategy:
    """
    Tạo và đăng ký strategy vô hiệu hóa cache dựa trên sự kiện.

    Args:
        event: Tên sự kiện hoặc danh sách sự kiện
        namespace: Namespace cần vô hiệu hóa
        patterns: Danh sách pattern cần vô hiệu hóa
        tags: Danh sách tags cần vô hiệu hóa

    Returns:
        EventBasedStrategy instance
    """
    events = [event] if isinstance(event, str) else event
    return EventBasedStrategy(
        events=events, namespace=namespace, patterns=patterns, tags=tags
    )


def clear_on_model_change(
    model_name: str,
    invalidate_on_create: bool = True,
    invalidate_on_update: bool = True,
    invalidate_on_delete: bool = True,
    namespace: Optional[str] = None,
    patterns: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> ModelEventStrategy:
    """
    Tạo và đăng ký strategy vô hiệu hóa cache dựa trên sự kiện model.

    Args:
        model_name: Tên model
        invalidate_on_create: Vô hiệu hóa khi tạo mới
        invalidate_on_update: Vô hiệu hóa khi cập nhật
        invalidate_on_delete: Vô hiệu hóa khi xóa
        namespace: Namespace cần vô hiệu hóa
        patterns: Danh sách pattern cần vô hiệu hóa
        tags: Danh sách tags cần vô hiệu hóa

    Returns:
        ModelEventStrategy instance
    """
    return ModelEventStrategy(
        model_name=model_name,
        invalidate_on_create=invalidate_on_create,
        invalidate_on_update=invalidate_on_update,
        invalidate_on_delete=invalidate_on_delete,
        namespace=namespace,
        patterns=patterns,
        tags=tags,
    )
