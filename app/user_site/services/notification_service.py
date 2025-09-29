from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.notification_repo import NotificationRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
)
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache
from app.cache.keys import CacheKeyBuilder
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import check_permission
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.logs_manager.services.user_activity_log_service import UserActivityLogService
from app.core.config import get_settings

settings = get_settings()


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_repo = NotificationRepository(db)
        self.user_repo = UserRepository(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time_static()
    @invalidate_cache(namespace="notifications", tags=["user_notifications"])
    async def create_notification(
        self,
        user_id: int,
        type: str,
        title: str,
        message: str,
        link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Tạo thông báo mới cho người dùng.

        Args:
            user_id: ID của người dùng
            type: Loại thông báo (SYSTEM, SECURITY, ACCOUNT, etc.)
            title: Tiêu đề thông báo
            message: Nội dung thông báo
            link: Đường dẫn (tùy chọn)

        Returns:
            Thông tin thông báo đã tạo
        """
        # Làm sạch dữ liệu
        title = sanitize_html(title)
        message = sanitize_html(message)
        if link:
            # Đảm bảo link không chứa mã độc
            link = sanitize_html(link)

        # Tạo thông báo
        notification_data = {
            "type": type,
            "title": title,
            "message": message,
            "link": link,
            "is_read": False,
        }

        notification = await self.notification_repo.create(user_id, notification_data)

        # Gửi thông báo realtime nếu được cấu hình
        try:
            # Nếu có websocket hoặc push notification service
            if (
                hasattr(settings, "ENABLE_REALTIME_NOTIFICATIONS")
                and settings.ENABLE_REALTIME_NOTIFICATIONS
            ):
                await self._send_realtime_notification(user_id, notification)
        except Exception as e:
            # Log lỗi nhưng không fail request
            print(f"Lỗi gửi thông báo realtime: {str(e)}")

        # Metrics
        self.metrics.track_user_activity("receive_notification", "registered")

        return {
            "id": notification.id,
            "user_id": notification.user_id,
            "type": notification.type,
            "title": notification.title,
            "message": notification.message,
            "link": notification.link,
            "is_read": notification.is_read,
            "created_at": notification.created_at,
            "read_at": (
                notification.read_at if hasattr(notification, "read_at") else None
            ),
        }

    @CodeProfiler.profile_time_static()
    @cached(ttl=300, namespace="notifications", tags=["notification_details"])
    async def get_notification(
        self, notification_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Lấy thông tin thông báo theo ID.

        Args:
            notification_id: ID của thông báo
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông tin thông báo

        Raises:
            NotFoundException: Nếu không tìm thấy thông báo
            ForbiddenException: Nếu không có quyền xem thông báo
        """
        notification = await self.notification_repo.get_by_id(notification_id)
        if not notification:
            raise NotFoundException(
                detail=f"Không tìm thấy thông báo với ID {notification_id}"
            )

        # Kiểm tra quyền
        if notification.user_id != user_id:
            try:
                is_admin = await check_permission(user_id, "manage_notifications")
                if not is_admin:
                    raise ForbiddenException("Bạn không có quyền xem thông báo này")
            except:
                raise ForbiddenException("Bạn không có quyền xem thông báo này")

        return {
            "id": notification.id,
            "user_id": notification.user_id,
            "type": notification.type,
            "title": notification.title,
            "message": notification.message,
            "link": notification.link,
            "is_read": notification.is_read,
            "created_at": notification.created_at,
            "read_at": notification.read_at,
        }

    @CodeProfiler.profile_time_static()
    @cached(ttl=300, namespace="notifications", tags=["user_notifications"])
    async def list_user_notifications(
        self, user_id: int, skip: int = 0, limit: int = 20, unread_only: bool = False
    ) -> Dict[str, Any]:
        """
        Lấy danh sách thông báo của người dùng.

        Args:
            user_id: ID của người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            unread_only: Chỉ lấy thông báo chưa đọc

        Returns:
            Danh sách thông báo và thông tin phân trang
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy danh sách thông báo
        filters = {"user_id": user_id}
        if unread_only:
            filters["is_read"] = False

        notifications = await self.notification_repo.list_by_user(
            user_id, skip, limit, unread_only
        )
        total = await self.notification_repo.count_by_user(user_id, unread_only)

        return {
            "items": [
                {
                    "id": notification.id,
                    "user_id": notification.user_id,
                    "type": notification.type,
                    "title": notification.title,
                    "message": notification.message,
                    "link": notification.link,
                    "is_read": notification.is_read,
                    "created_at": notification.created_at,
                    "read_at": notification.read_at,
                }
                for notification in notifications
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
            "unread_count": await self.get_unread_count(user_id),
        }

    @CodeProfiler.profile_time_static()
    @invalidate_cache(
        namespace="notifications", tags=["user_notifications", "notification_details"]
    )
    async def mark_as_read(self, notification_id: int, user_id: int) -> Dict[str, Any]:
        """
        Đánh dấu thông báo là đã đọc.

        Args:
            notification_id: ID của thông báo
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông tin thông báo đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy thông báo
            ForbiddenException: Nếu không có quyền đánh dấu thông báo
        """
        notification = await self.notification_repo.get_by_id(notification_id)
        if not notification:
            raise NotFoundException(
                detail=f"Không tìm thấy thông báo với ID {notification_id}"
            )

        # Kiểm tra quyền
        if notification.user_id != user_id:
            raise ForbiddenException("Bạn không có quyền đánh dấu thông báo này")

        # Kiểm tra xem đã đọc chưa
        if notification.is_read:
            return {
                "id": notification.id,
                "is_read": notification.is_read,
                "read_at": notification.read_at,
            }

        # Cập nhật trạng thái đã đọc
        update_data = {"is_read": True, "read_at": datetime.now().isoformat()}

        updated = await self.notification_repo.update(notification_id, update_data)

        # Metrics
        self.metrics.track_user_activity("read_notification", "registered")

        return {
            "id": updated.id,
            "is_read": updated.is_read,
            "read_at": updated.read_at,
        }

    @CodeProfiler.profile_time_static()
    @invalidate_cache(namespace="notifications", tags=["user_notifications"])
    async def mark_all_as_read(self, user_id: int) -> Dict[str, Any]:
        """
        Đánh dấu tất cả thông báo của người dùng là đã đọc.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông báo kết quả
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Đánh dấu tất cả là đã đọc
        updated_count = await self.notification_repo.mark_all_as_read(user_id)

        # Metrics
        self.metrics.track_user_activity("read_all_notifications", "registered")

        return {
            "success": True,
            "message": f"Đã đánh dấu {updated_count} thông báo là đã đọc",
            "updated_count": updated_count,
        }

    @CodeProfiler.profile_time_static()
    @invalidate_cache(
        namespace="notifications", tags=["user_notifications", "notification_details"]
    )
    async def delete_notification(
        self, notification_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Xóa thông báo.

        Args:
            notification_id: ID của thông báo
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy thông báo
            ForbiddenException: Nếu không có quyền xóa thông báo
        """
        notification = await self.notification_repo.get_by_id(notification_id)
        if not notification:
            raise NotFoundException(
                detail=f"Không tìm thấy thông báo với ID {notification_id}"
            )

        # Kiểm tra quyền
        if notification.user_id != user_id:
            try:
                is_admin = await check_permission(user_id, "manage_notifications")
                if not is_admin:
                    raise ForbiddenException("Bạn không có quyền xóa thông báo này")
            except:
                raise ForbiddenException("Bạn không có quyền xóa thông báo này")

        # Xóa thông báo
        result = await self.notification_repo.delete(notification_id)

        # Metrics
        self.metrics.track_user_activity("delete_notification", "registered")

        return {"success": result, "message": "Đã xóa thông báo thành công"}

    @CodeProfiler.profile_time_static()
    @invalidate_cache(namespace="notifications", tags=["user_notifications"])
    async def delete_all_notifications(self, user_id: int) -> Dict[str, Any]:
        """
        Xóa tất cả thông báo của người dùng.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông báo kết quả
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Xóa tất cả thông báo
        deleted_count = await self.notification_repo.delete_by_user(user_id)

        # Metrics
        self.metrics.track_user_activity("delete_all_notifications", "registered")

        return {
            "success": True,
            "message": f"Đã xóa {deleted_count} thông báo",
            "deleted_count": deleted_count,
        }

    @CodeProfiler.profile_time_static()
    @invalidate_cache(namespace="notifications", tags=["system_notifications"])
    async def create_system_notification(
        self,
        title: str,
        message: str,
        link: Optional[str] = None,
        admin_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Tạo thông báo hệ thống cho tất cả hoặc một nhóm người dùng.

        Args:
            title: Tiêu đề thông báo
            message: Nội dung thông báo
            link: Đường dẫn liên quan (tùy chọn)
            admin_id: ID admin thực hiện (tùy chọn)

        Returns:
            Kết quả tạo thông báo

        Raises:
            BadRequestException: Nếu dữ liệu không hợp lệ
            ForbiddenException: Nếu không có quyền tạo thông báo hệ thống
        """
        # Kiểm tra quyền nếu có admin_id
        if admin_id:
            try:
                is_admin = await check_permission(admin_id, "manage_notifications")
                if not is_admin:
                    raise ForbiddenException(
                        "Bạn không có quyền tạo thông báo hệ thống"
                    )
            except:
                raise ForbiddenException("Bạn không có quyền tạo thông báo hệ thống")

        # Làm sạch dữ liệu
        title = sanitize_html(title)
        message = sanitize_html(message)
        if link:
            link = sanitize_html(link)

        # TODO: Tạo thông báo cho tất cả người dùng
        # Trong trường hợp thực tế, không nên tạo thông báo cho từng người dùng
        # mà nên lưu thông báo hệ thống và hiển thị cho người dùng khi họ đăng nhập

        # Tạm thời trả về kết quả thành công
        return {
            "success": True,
            "message": "Đã tạo thông báo hệ thống thành công",
            "title": title,
            "message": message,
            "link": link,
        }

    @CodeProfiler.profile_time_static()
    @cached(ttl=60, namespace="notifications", tags=["user_notifications"])
    async def get_unread_count(self, user_id: int) -> Dict[str, Any]:
        """
        Lấy số lượng thông báo chưa đọc của người dùng.

        Args:
            user_id: ID của người dùng

        Returns:
            Số lượng thông báo chưa đọc
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy số lượng thông báo chưa đọc
        unread_count = await self.notification_repo.count_by_user(
            user_id, unread_only=True
        )

        return {"user_id": user_id, "unread_count": unread_count}

    async def _send_realtime_notification(
        self, user_id: int, notification: Dict[str, Any]
    ) -> None:
        """
        Gửi thông báo realtime qua WebSocket hoặc Push Notification.

        Args:
            user_id: ID người dùng
            notification: Thông tin thông báo
        """
        # Kiểm tra xem có WebSocket Manager không
        try:
            from app.websockets.manager import WebSocketManager

            ws_manager = WebSocketManager()

            # Đảm bảo các trường tồn tại trong đối tượng notification
            notification_data = {
                "id": (
                    notification.id
                    if hasattr(notification, "id")
                    else notification.get("id")
                ),
                "type": (
                    notification.type
                    if hasattr(notification, "type")
                    else notification.get("type")
                ),
                "title": (
                    notification.title
                    if hasattr(notification, "title")
                    else notification.get("title")
                ),
                "message": (
                    notification.message
                    if hasattr(notification, "message")
                    else notification.get("message")
                ),
                "link": (
                    notification.link
                    if hasattr(notification, "link")
                    else notification.get("link")
                ),
                "created_at": (
                    notification.created_at
                    if hasattr(notification, "created_at")
                    else notification.get("created_at")
                ),
            }

            await ws_manager.send_to_user(
                user_id=str(user_id),
                message_type="notification",
                data=notification_data,
            )
        except ImportError:
            # WebSocket không được cấu hình
            pass

        # Thử gửi Push Notification
        try:
            from app.notifications.push import send_push_notification

            # Lấy thông tin thiết bị của người dùng
            devices = await self._get_user_devices(user_id)

            if devices:
                title = (
                    notification.title
                    if hasattr(notification, "title")
                    else notification.get("title", "")
                )
                message = (
                    notification.message
                    if hasattr(notification, "message")
                    else notification.get("message", "")
                )
                notification_id = (
                    notification.id
                    if hasattr(notification, "id")
                    else notification.get("id")
                )
                notification_type = (
                    notification.type
                    if hasattr(notification, "type")
                    else notification.get("type")
                )
                notification_link = (
                    notification.link
                    if hasattr(notification, "link")
                    else notification.get("link")
                )

                for device in devices:
                    await send_push_notification(
                        device_token=device["token"],
                        title=title,
                        body=message,
                        data={
                            "notification_id": notification_id,
                            "type": notification_type,
                            "link": notification_link,
                        },
                    )
        except ImportError:
            # Push Notification không được cấu hình
            pass

    async def _get_user_devices(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Lấy danh sách thiết bị của người dùng.

        Args:
            user_id: ID người dùng

        Returns:
            Danh sách thiết bị
        """
        # Trong thực tế, cần lấy danh sách thiết bị từ database
        # Nhưng trong ví dụ này, chúng ta giả định không có thiết bị nào
        return []
