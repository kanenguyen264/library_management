from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.user_site.models.notification import UserNotification
from app.user_site.repositories.notification_repo import NotificationRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho notification service
logger = logging.getLogger(__name__)


async def get_all_notifications(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    is_read: Optional[bool] = None,
    type: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> List[UserNotification]:
    """
    Lấy danh sách thông báo với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        is_read: Lọc theo trạng thái đã đọc
        type: Lọc theo loại thông báo
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        admin_id: ID của người dùng admin

    Returns:
        Danh sách thông báo
    """
    try:
        repo = NotificationRepository(db)

        # Nếu có type, phải xử lý filter riêng vì repo hiện tại không hỗ trợ
        if user_id:
            notifications = await repo.list_by_user(
                user_id=user_id, skip=skip, limit=limit, is_read=is_read
            )
        else:
            # Giả sử cần phải có user_id, nếu không phải lấy thủ công
            logger.warning(
                "Getting all notifications without a user_id filter may cause performance issues"
            )

            # Trong trường hợp cần lấy tất cả thông báo của hệ thống (admin)
            # Cần phát triển thêm hàm list_all ở repository
            notifications = []

        # Filter by date và type nếu có
        if from_date or to_date or type:
            filtered_notifications = []
            for n in notifications:
                # Lọc theo ngày tạo
                if from_date and n.created_at < from_date:
                    continue
                if to_date and n.created_at > to_date:
                    continue
                # Lọc theo loại thông báo
                if type and n.type != type:
                    continue
                filtered_notifications.append(n)
            return filtered_notifications

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="NOTIFICATIONS",
                        entity_id=0,
                        description="Viewed notifications list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "is_read": is_read,
                            "type": type,
                            "from_date": from_date.isoformat() if from_date else None,
                            "to_date": to_date.isoformat() if to_date else None,
                            "results_count": len(notifications),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return notifications
    except Exception as e:
        logger.error(f"Error retrieving notifications: {str(e)}")
        raise


async def count_notifications(
    db: Session, user_id: Optional[int] = None, is_read: Optional[bool] = None
) -> int:
    """
    Đếm số lượng thông báo.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        is_read: Lọc theo trạng thái đã đọc

    Returns:
        Số lượng thông báo
    """
    try:
        repo = NotificationRepository(db)

        if user_id:
            return await repo.count_by_user(user_id, is_read)
        else:
            # Đếm tất cả thông báo trong hệ thống (admin)
            # Cần phát triển thêm hàm count_all ở repository
            logger.warning(
                "Counting all notifications without a user_id filter may cause performance issues"
            )
            return 0
    except Exception as e:
        logger.error(f"Error counting notifications: {str(e)}")
        raise


async def get_notification_by_id(
    db: Session, notification_id: int, admin_id: Optional[int] = None
) -> UserNotification:
    """
    Lấy thông tin thông báo theo ID.

    Args:
        db: Database session
        notification_id: ID của thông báo
        admin_id: ID của người dùng admin

    Returns:
        Thông tin thông báo

    Raises:
        NotFoundException: Nếu không tìm thấy thông báo
    """
    try:
        repo = NotificationRepository(db)
        notification = await repo.get_by_id(notification_id)

        if not notification:
            logger.warning(f"Notification with ID {notification_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy thông báo với ID {notification_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="NOTIFICATION",
                        entity_id=notification_id,
                        description=f"Viewed notification details: {notification.title}",
                        metadata={
                            "title": notification.title,
                            "user_id": notification.user_id,
                            "type": notification.type,
                            "is_read": notification.is_read,
                            "created_at": (
                                notification.created_at.isoformat()
                                if hasattr(notification, "created_at")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return notification
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving notification: {str(e)}")
        raise


@cached(key_prefix="admin_user_notifications", ttl=300)
async def get_user_notifications(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    is_read: Optional[bool] = None,
    admin_id: Optional[int] = None,
) -> List[UserNotification]:
    """
    Lấy danh sách thông báo của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        is_read: Lọc theo trạng thái đã đọc
        admin_id: ID của người dùng admin

    Returns:
        Danh sách thông báo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = NotificationRepository(db)
        notifications = await repo.list_notifications(
            user_id=user_id,
            skip=skip,
            limit=limit,
            is_read=is_read,
            sort_by="created_at",
            sort_desc=True,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_NOTIFICATIONS",
                        entity_id=user_id,
                        description=f"Viewed notifications for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "skip": skip,
                            "limit": limit,
                            "is_read": is_read,
                            "results_count": len(notifications),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return notifications
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user notifications: {str(e)}")
        raise


async def count_user_notifications(
    db: Session, user_id: int, is_read: Optional[bool] = None
) -> int:
    """
    Đếm số lượng thông báo của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        is_read: Lọc theo trạng thái đã đọc

    Returns:
        Số lượng thông báo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = NotificationRepository(db)
        return await repo.count_by_user(user_id, is_read)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error counting user notifications: {str(e)}")
        raise


async def create_notification(
    db: Session, notification_data: Dict[str, Any], admin_id: Optional[int] = None
) -> UserNotification:
    """
    Tạo thông báo mới.

    Args:
        db: Database session
        notification_data: Dữ liệu thông báo
        admin_id: ID của người dùng admin

    Returns:
        Thông tin thông báo đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        if "user_id" in notification_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(notification_data["user_id"])

            if not user:
                logger.warning(f"User with ID {notification_data['user_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {notification_data['user_id']}"
                )

        # Tạo thông báo mới
        repo = NotificationRepository(db)
        notification = await repo.create(notification_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="NOTIFICATION",
                        entity_id=notification.id,
                        description=f"Created notification: {notification.title}",
                        metadata={
                            "title": notification.title,
                            "user_id": notification.user_id,
                            "type": notification.type,
                            "message": notification.message,
                            "link": notification.link,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Created new notification with ID {notification.id} for user {notification.user_id}"
        )
        return notification
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating notification: {str(e)}")
        raise


async def mark_as_read(
    db: Session, notification_id: int, admin_id: Optional[int] = None
) -> UserNotification:
    """
    Đánh dấu thông báo đã đọc.

    Args:
        db: Database session
        notification_id: ID của thông báo
        admin_id: ID của người dùng admin

    Returns:
        Thông tin thông báo đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy thông báo
    """
    try:
        # Kiểm tra thông báo tồn tại
        await get_notification_by_id(db, notification_id)

        # Đánh dấu đã đọc
        repo = NotificationRepository(db)
        notification = await repo.mark_as_read(notification_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="NOTIFICATION",
                        entity_id=notification_id,
                        description=f"Marked notification as read: {notification.title}",
                        metadata={
                            "title": notification.title,
                            "user_id": notification.user_id,
                            "previous_status": notification.is_read,
                            "new_status": notification.is_read,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Marked notification {notification_id} as read")
        return notification
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        raise


async def update_notification(
    db: Session,
    notification_id: int,
    notification_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> UserNotification:
    """
    Cập nhật thông tin của thông báo.

    Args:
        db: Database session
        notification_id: ID của thông báo
        notification_data: Dữ liệu cập nhật cho thông báo
        admin_id: ID của người dùng admin

    Returns:
        Thông tin thông báo đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy thông báo
    """
    try:
        # Kiểm tra thông báo tồn tại
        original_notification = await get_notification_by_id(db, notification_id)

        # Cập nhật thông báo
        repo = NotificationRepository(db)
        updated_notification = await repo.update(notification_id, notification_data)

        if not updated_notification:
            raise NotFoundException(
                detail=f"Không thể cập nhật thông báo với ID {notification_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="NOTIFICATION",
                        entity_id=notification_id,
                        description=f"Updated notification: {updated_notification.title}",
                        metadata={
                            "title": updated_notification.title,
                            "user_id": updated_notification.user_id,
                            "type": updated_notification.type,
                            "message": updated_notification.message,
                            "link": updated_notification.link,
                            "is_read": updated_notification.is_read,
                            "original_title": original_notification.title,
                            "changed_fields": list(notification_data.keys()),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated notification with ID {notification_id}")
        return updated_notification
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating notification: {str(e)}")
        raise


async def mark_all_as_read(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> int:
    """
    Đánh dấu tất cả thông báo của người dùng đã đọc.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của người dùng admin

    Returns:
        Số lượng thông báo đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = NotificationRepository(db)
        count = await repo.mark_all_as_read(user_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="USER_NOTIFICATIONS",
                        entity_id=user_id,
                        description=f"Marked all notifications as read for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "count": count,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Marked {count} notifications as read for user {user_id}")
        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        raise


async def delete_notification(
    db: Session, notification_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa thông báo.

    Args:
        db: Database session
        notification_id: ID của thông báo
        admin_id: ID của người dùng admin

    Raises:
        NotFoundException: Nếu không tìm thấy thông báo
    """
    try:
        # Kiểm tra thông báo tồn tại và lưu lại để sử dụng trong logging
        current_notification = await get_notification_by_id(db, notification_id)

        # Xóa thông báo
        repo = NotificationRepository(db)
        await repo.delete(notification_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="NOTIFICATION",
                        entity_id=notification_id,
                        description=f"Deleted notification: {current_notification.title}",
                        metadata={
                            "title": current_notification.title,
                            "user_id": current_notification.user_id,
                            "type": current_notification.type,
                            "is_read": current_notification.is_read,
                            "created_at": (
                                current_notification.created_at.isoformat()
                                if hasattr(current_notification, "created_at")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted notification with ID {notification_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        raise


async def delete_user_notifications(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> int:
    """
    Xóa tất cả thông báo của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của người dùng admin

    Returns:
        Số lượng thông báo đã xóa

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = NotificationRepository(db)
        count = await repo.delete_all_by_user(user_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="USER_NOTIFICATIONS",
                        entity_id=user_id,
                        description=f"Deleted all notifications for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "count": count,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted {count} notifications for user {user_id}")
        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user notifications: {str(e)}")
        raise


async def get_unread_count(db: Session, user_id: int) -> int:
    """
    Lấy số lượng thông báo chưa đọc của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Số lượng thông báo chưa đọc

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = NotificationRepository(db)
        return await repo.get_unread_count(user_id)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        raise


async def create_system_notification(
    db: Session, user_id: int, title: str, message: str, link: Optional[str] = None
) -> UserNotification:
    """
    Tạo thông báo hệ thống cho người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        title: Tiêu đề thông báo
        message: Nội dung thông báo
        link: Đường dẫn liên kết (nếu có)

    Returns:
        Thông tin thông báo đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = NotificationRepository(db)
        notification = await repo.create_system_notification(
            user_id, title, message, link
        )

        logger.info(f"Created system notification for user {user_id}")
        return notification
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating system notification: {str(e)}")
        raise


async def create_follow_notification(
    db: Session, followed_user_id: int, follower_id: int, follower_name: str
) -> UserNotification:
    """
    Tạo thông báo khi có người follow.

    Args:
        db: Database session
        followed_user_id: ID của người dùng được follow
        follower_id: ID của người dùng thực hiện follow
        follower_name: Tên của người dùng thực hiện follow

    Returns:
        Thông tin thông báo đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)

        followed_user = await user_repo.get_by_id(followed_user_id)
        if not followed_user:
            logger.warning(f"Followed user with ID {followed_user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {followed_user_id}"
            )

        follower = await user_repo.get_by_id(follower_id)
        if not follower:
            logger.warning(f"Follower with ID {follower_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {follower_id}"
            )

        repo = NotificationRepository(db)
        notification = await repo.create_follow_notification(
            followed_user_id, follower_id, follower_name
        )

        logger.info(f"Created follow notification for user {followed_user_id}")
        return notification
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating follow notification: {str(e)}")
        raise


async def create_bulk_notifications(
    db: Session,
    user_ids: List[int],
    title: str,
    message: str,
    link: Optional[str] = None,
    notification_type: str = "system",
    admin_id: Optional[int] = None,
) -> int:
    """
    Tạo thông báo hàng loạt cho nhiều người dùng.

    Args:
        db: Database session
        user_ids: Danh sách ID người dùng
        title: Tiêu đề thông báo
        message: Nội dung thông báo
        link: Đường dẫn liên kết (nếu có)
        notification_type: Loại thông báo
        admin_id: ID của người dùng admin

    Returns:
        Số lượng thông báo đã tạo
    """
    try:
        # Check if users exist
        user_repo = UserRepository(db)
        valid_user_ids = []

        for user_id in user_ids:
            user = await user_repo.get_by_id(user_id)
            if user:
                valid_user_ids.append(user_id)

        if not valid_user_ids:
            logger.warning("No valid users found for bulk notification")
            return 0

        # Create notifications
        repo = NotificationRepository(db)
        count = 0

        for user_id in valid_user_ids:
            notification_data = {
                "user_id": user_id,
                "title": title,
                "message": message,
                "link": link,
                "type": notification_type,
                "is_read": False,
            }

            try:
                await repo.create(notification_data)
                count += 1
            except Exception as e:
                logger.error(
                    f"Error creating notification for user {user_id}: {str(e)}"
                )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="BULK_NOTIFICATIONS",
                        entity_id=0,
                        description=f"Created bulk notifications: {title}",
                        metadata={
                            "title": title,
                            "message": message,
                            "link": link,
                            "type": notification_type,
                            "target_user_count": len(user_ids),
                            "successful_notifications": count,
                            "target_users": user_ids[:10]
                            + (
                                ["..."] if len(user_ids) > 10 else []
                            ),  # Limit to first 10 users for logging
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created {count} bulk notifications")
        return count
    except Exception as e:
        logger.error(f"Error creating bulk notifications: {str(e)}")
        raise


@cached(key_prefix="admin_notification_statistics", ttl=3600)
async def get_notification_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về thông báo.

    Args:
        db: Database session
        admin_id: ID của người dùng admin

    Returns:
        Thống kê thông báo
    """
    try:
        # Đây là pseudocode, cần thêm các phương thức ở repository
        # để hỗ trợ các thống kê này

        # Tổng số thông báo
        # total_notifications = await repo.count_all()

        # Số thông báo chưa đọc
        # unread_notifications = await repo.count_all(is_read=False)

        # Phân loại theo loại thông báo
        # notification_types = await repo.count_by_types()

        # Get notification statistics
        repo = NotificationRepository(db)

        total = await repo.count_notifications()
        read = await repo.count_notifications(is_read=True)
        unread = await repo.count_notifications(is_read=False)

        # Count by type
        system_count = await repo.count_notifications(type="system")
        follow_count = await repo.count_notifications(type="follow")
        like_count = await repo.count_notifications(type="like")
        comment_count = await repo.count_notifications(type="comment")

        # Recent activity
        now = datetime.now(timezone.utc)
        today = datetime(now.year, now.month, now.day)

        today_count = await repo.count_notifications(
            from_date=today, to_date=today + timedelta(days=1)
        )

        this_week = await repo.count_notifications(
            from_date=today - timedelta(days=today.weekday()),
            to_date=today + timedelta(days=1),
        )

        stats = {
            "total": total,
            "read": read,
            "unread": unread,
            "by_type": {
                "system": system_count,
                "follow": follow_count,
                "like": like_count,
                "comment": comment_count,
            },
            "today": today_count,
            "this_week": this_week,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="NOTIFICATION_STATISTICS",
                        entity_id=0,
                        description="Viewed notification system statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving notification statistics: {str(e)}")
        raise
