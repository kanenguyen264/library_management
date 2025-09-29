from typing import Optional, List, Dict, Any
from sqlalchemy import (
    select,
    func,
    update,
    delete,
    desc,
    and_,
    asc,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app.user_site.models.notification import UserNotification
from app.user_site.models.user import User
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ValidationException,
)


class NotificationRepository:
    """Repository cho các thao tác với Thông báo (Notification) của người dùng."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession.

        Args:
            db: Đối tượng AsyncSession để tương tác với cơ sở dữ liệu.
        """
        self.db = db

    async def create(self, user_id: int, data: Dict[str, Any]) -> UserNotification:
        """Tạo một thông báo mới cho người dùng.

        Args:
            user_id: ID của người dùng nhận thông báo.
            data: Dữ liệu thông báo. Các trường yêu cầu/tùy chọn:
                - notification_type (str): Loại thông báo.
                - content (str): Nội dung thông báo.
                - link (Optional[str]): Đường dẫn liên kết (nếu có).
                - is_read (bool): Trạng thái đã đọc (mặc định False).

        Returns:
            Đối tượng Notification đã tạo.

        Raises:
            NotFoundException: Nếu user_id không tồn tại.
            ValidationException: Nếu thiếu các trường bắt buộc (notification_type, content).
            ConflictException: Nếu có lỗi ràng buộc khác.
        """
        # Kiểm tra user tồn tại
        user = await self.db.get(User, user_id)
        if not user:
            raise NotFoundException(f"Người dùng với ID {user_id} không tồn tại.")

        allowed_fields = {"notification_type", "content", "link", "is_read"}
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
        filtered_data["user_id"] = user_id

        # Validation
        if not filtered_data.get("notification_type"):
            raise ValidationException("Loại thông báo (notification_type) là bắt buộc.")
        if not filtered_data.get("content"):
            raise ValidationException("Nội dung thông báo (content) là bắt buộc.")

        filtered_data.setdefault("is_read", False)

        notification = UserNotification(**filtered_data)
        self.db.add(notification)
        try:
            await self.db.commit()
            await self.db.refresh(notification)
            return notification
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Không thể tạo thông báo: {e}")

    async def get_by_id(
        self, notification_id: int, with_user: bool = False
    ) -> Optional[UserNotification]:
        """Lấy thông báo theo ID.

        Args:
            notification_id: ID của thông báo.
            with_user: Có load thông tin người dùng không.

        Returns:
            Đối tượng Notification hoặc None.
        """
        query = select(UserNotification).where(UserNotification.id == notification_id)
        if with_user:
            query = query.options(joinedload(UserNotification.user))
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_notifications(
        self,
        user_id: int,
        is_read: Optional[bool] = None,
        notification_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> List[UserNotification]:
        """Lấy danh sách thông báo cho người dùng cụ thể.

        Args:
            user_id: ID của người dùng (bắt buộc).
            is_read: Lọc theo trạng thái đã đọc.
            notification_type: Lọc theo loại thông báo.
            skip, limit: Phân trang.
            sort_by: Trường sắp xếp ('created_at', 'is_read').
            sort_desc: Sắp xếp giảm dần.

        Returns:
            Danh sách các đối tượng Notification.
        """
        query = select(UserNotification).where(UserNotification.user_id == user_id)

        # Áp dụng bộ lọc
        if is_read is not None:
            query = query.filter(UserNotification.is_read == is_read)
        if notification_type:
            query = query.filter(
                UserNotification.notification_type == notification_type
            )

        # Sắp xếp
        sort_attr = getattr(UserNotification, sort_by, UserNotification.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_notifications(
        self,
        user_id: int,
        is_read: Optional[bool] = None,
        notification_type: Optional[str] = None,
    ) -> int:
        """Đếm số lượng thông báo của người dùng theo bộ lọc.

        Args:
            user_id: ID của người dùng (bắt buộc).
            is_read: Lọc theo trạng thái đã đọc.
            notification_type: Lọc theo loại thông báo.

        Returns:
            Tổng số thông báo khớp điều kiện.
        """
        query = select(func.count(UserNotification.id)).where(
            UserNotification.user_id == user_id
        )

        # Áp dụng bộ lọc
        if is_read is not None:
            query = query.filter(UserNotification.is_read == is_read)
        if notification_type:
            query = query.filter(
                UserNotification.notification_type == notification_type
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def count_unread_notifications(self, user_id: int) -> int:
        """Đếm số lượng thông báo chưa đọc của người dùng."""
        return await self.count_notifications(user_id=user_id, is_read=False)

    async def mark_as_read(self, notification_id: int) -> Optional[UserNotification]:
        """Đánh dấu một thông báo là đã đọc.

        Args:
            notification_id: ID thông báo.

        Returns:
            Đối tượng Notification đã cập nhật hoặc None nếu không tìm thấy.
        """
        stmt = (
            update(UserNotification)
            .where(UserNotification.id == notification_id)
            .where(UserNotification.is_read == False)  # Chỉ cập nhật nếu chưa đọc
            .values(is_read=True)
            .returning(UserNotification)
            .execution_options(synchronize_session="fetch")
        )
        result = await self.db.execute(stmt)
        updated_notification = result.scalars().first()
        if updated_notification:
            await self.db.commit()
            return updated_notification
        # Nếu không update được (do ko tìm thấy hoặc đã đọc rồi), trả về None hoặc lấy lại trạng thái hiện tại
        # return await self.get_by_id(notification_id) # Tùy chọn: trả về trạng thái hiện tại
        return None

    async def mark_as_unread(self, notification_id: int) -> Optional[UserNotification]:
        """Đánh dấu một thông báo là chưa đọc.

        Args:
            notification_id: ID thông báo.

        Returns:
            Đối tượng Notification đã cập nhật hoặc None nếu không tìm thấy.
        """
        stmt = (
            update(UserNotification)
            .where(UserNotification.id == notification_id)
            .where(UserNotification.is_read == True)  # Chỉ cập nhật nếu đang đọc
            .values(is_read=False)
            .returning(UserNotification)
            .execution_options(synchronize_session="fetch")
        )
        result = await self.db.execute(stmt)
        updated_notification = result.scalars().first()
        if updated_notification:
            await self.db.commit()
            return updated_notification
        return None

    async def mark_all_as_read(self, user_id: int) -> int:
        """Đánh dấu tất cả thông báo chưa đọc của người dùng là đã đọc.

        Args:
            user_id: ID của người dùng.

        Returns:
            Số lượng thông báo được cập nhật.
        """
        stmt = (
            update(UserNotification)
            .where(UserNotification.user_id == user_id)
            .where(UserNotification.is_read == False)
            .values(is_read=True)
            .execution_options(
                synchronize_session=False
            )  # Không cần fetch khi update nhiều
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def delete_notification(self, notification_id: int) -> bool:
        """Xóa một thông báo.

        Args:
            notification_id: ID thông báo cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        stmt = delete(UserNotification).where(UserNotification.id == notification_id)
        result = await self.db.execute(stmt)
        if result.rowcount > 0:
            await self.db.commit()
            return True
        return False

    async def delete_all_for_user(self, user_id: int, only_read: bool = False) -> int:
        """Xóa tất cả thông báo của người dùng (hoặc chỉ những thông báo đã đọc).

        Args:
            user_id: ID của người dùng.
            only_read: Chỉ xóa những thông báo đã đọc (True) hay xóa tất cả (False).

        Returns:
            Số lượng thông báo đã xóa.
        """
        stmt = delete(UserNotification).where(UserNotification.user_id == user_id)
        if only_read:
            stmt = stmt.where(UserNotification.is_read == True)

        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def create_system_notification(
        self, user_id: int, title: str, message: str, link: Optional[str] = None
    ) -> UserNotification:
        """Tạo thông báo hệ thống cho người dùng."""
        data = {
            "user_id": user_id,
            "type": "system",
            "title": title,
            "message": message,
            "link": link,
            "is_read": False,
        }
        return await self.create(user_id, data)

    async def create_follow_notification(
        self, followed_user_id: int, follower_id: int, follower_name: str
    ) -> UserNotification:
        """Tạo thông báo khi có người follow."""
        data = {
            "user_id": followed_user_id,
            "type": "follow",
            "title": "Có người theo dõi mới",
            "message": f"{follower_name} đã bắt đầu theo dõi bạn",
            "link": f"/users/{follower_id}",
            "is_read": False,
        }
        return await self.create(followed_user_id, data)

    async def create_like_notification(
        self,
        content_owner_id: int,
        liker_id: int,
        liker_name: str,
        content_type: str,
        content_id: int,
    ) -> UserNotification:
        """Tạo thông báo khi có người thích nội dung."""
        content_map = {
            "review": "bài đánh giá",
            "comment": "bình luận",
            "quote": "trích dẫn",
            "discussion": "thảo luận",
        }
        content_text = content_map.get(content_type, "nội dung")

        data = {
            "user_id": content_owner_id,
            "type": f"like_{content_type}",
            "title": f"Có người thích {content_text} của bạn",
            "message": f"{liker_name} đã thích {content_text} của bạn",
            "link": f"/{content_type}s/{content_id}",
            "is_read": False,
        }
        return await self.create(content_owner_id, data)

    async def create_comment_notification(
        self,
        content_owner_id: int,
        commenter_id: int,
        commenter_name: str,
        content_type: str,
        content_id: int,
    ) -> UserNotification:
        """Tạo thông báo khi có người bình luận."""
        content_map = {
            "review": "bài đánh giá",
            "discussion": "thảo luận",
            "quote": "trích dẫn",
        }
        content_text = content_map.get(content_type, "nội dung")

        data = {
            "user_id": content_owner_id,
            "type": f"comment_{content_type}",
            "title": f"Có bình luận mới trên {content_text} của bạn",
            "message": f"{commenter_name} đã bình luận về {content_text} của bạn",
            "link": f"/{content_type}s/{content_id}",
            "is_read": False,
        }
        return await self.create(content_owner_id, data)
