from typing import Dict, Any, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    HTTPException,
    status,
    Request,
    Body,
)
from app.user_site.api.throttling import throttle_requests
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from pydantic import conint, validator, root_validator

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_active_user
from app.user_site.models.user import User
from app.user_site.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    DeviceNotificationToken,
    NotificationCategoryResponse,
    NotificationFilterParams,
    NotificationPreferencesUpdate,
    NotificationPreferencesResponse,
    NotificationCountResponse,
    NotificationPreferences,
    NotificationStatsResponse,
    NotificationSearchParams,
    NotificationBulkUpdateRequest,
    NotificationCreate,
    NotificationCategoryEnum,
    NotificationPriorityEnum,
    BulkNotificationAction,
    NotificationStats,
    PushNotificationToken,
    DeviceRegistration,
    NotificationCategory,
    NotificationPriority,
    NotificationBulkAction,
    NotificationPreferenceResponse,
    NotificationMarkRequest,
)
from app.user_site.services.notification_service import NotificationService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    ServerException,
    ConflictException,
    RateLimitException,
)
from app.common.exceptions import ResourceNotFoundException, PermissionDeniedException
from app.security.audit.log_admin_action import log_admin_action as log_action
from app.common.utils.pagination import PaginationParams

router = APIRouter()
logger = get_logger("notifications_api")
audit_logger = AuditLogger()


@router.get(
    "/",
    response_model=NotificationListResponse,
    summary="Get user notifications",
    description="Retrieve a list of notifications for the current user with filtering options",
)
@track_request_time
async def get_notifications(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    unread_only: bool = Query(False, description="Filter to unread notifications only"),
    notification_type: Optional[str] = Query(
        None, description="Filter by notification type"
    ),
    start_date: Optional[str] = Query(
        None, description="Start date filter (ISO format)"
    ),
    end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get paginated list of notifications for the current user.

    Can be filtered by:
    - Read/unread status
    - Notification type (follow, like, comment, etc.)
    - Date range
    """
    notification_service = NotificationService(db)

    try:
        # Calculate pagination
        skip = (page - 1) * page_size

        # Get notifications with filters
        notifications, total = await notification_service.get_user_notifications(
            user_id=current_user.id,
            skip=skip,
            limit=page_size,
            unread_only=unread_only,
            notification_type=notification_type,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate total pages
        total_pages = (total + page_size - 1) // page_size

        # Update last viewed timestamp
        await notification_service.update_last_viewed(user_id=current_user.id)

        return {
            "items": notifications,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "unread_count": await notification_service.get_unread_count(
                user_id=current_user.id
            ),
        }
    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get notifications",
        )


@router.post("/bulk-update", response_model=Dict[str, Any])
@track_request_time(endpoint="bulk_update_notifications")
@invalidate_cache(namespace="notifications", tags=["notifications"])
async def bulk_update_notifications(
    update_request: NotificationBulkUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Cập nhật hàng loạt các thông báo.

    Cho phép người dùng đánh dấu nhiều thông báo là đã đọc/chưa đọc,
    xóa nhiều thông báo cùng lúc, hoặc đánh dấu tất cả là đã đọc.
    """
    try:
        notification_service = NotificationService(db)

        # Validate quyền truy cập vào các thông báo
        if update_request.notification_ids:
            for notification_id in update_request.notification_ids:
                notification = await notification_service.get_notification(
                    notification_id
                )
                if not notification or notification.user_id != current_user.id:
                    raise ForbiddenException(
                        detail="Không có quyền truy cập vào thông báo"
                    )

        result = {"success": True, "updated_count": 0, "message": ""}

        # Thực hiện các thao tác hàng loạt
        if update_request.mark_all_read:
            # Đánh dấu tất cả thông báo là đã đọc
            updated_count = await notification_service.mark_all_as_read(current_user.id)
            result["updated_count"] = updated_count
            result["message"] = (
                f"Đã đánh dấu tất cả {updated_count} thông báo là đã đọc"
            )
        elif update_request.action and update_request.notification_ids:
            # Thực hiện hành động trên danh sách thông báo
            if update_request.action == "mark_read":
                updated_count = await notification_service.mark_as_read(
                    update_request.notification_ids
                )
                result["updated_count"] = updated_count
                result["message"] = f"Đã đánh dấu {updated_count} thông báo là đã đọc"
            elif update_request.action == "mark_unread":
                updated_count = await notification_service.mark_as_unread(
                    update_request.notification_ids
                )
                result["updated_count"] = updated_count
                result["message"] = f"Đã đánh dấu {updated_count} thông báo là chưa đọc"
            elif update_request.action == "delete":
                deleted_count = await notification_service.delete_notifications(
                    update_request.notification_ids
                )
                result["updated_count"] = deleted_count
                result["message"] = f"Đã xóa {deleted_count} thông báo"
            else:
                raise BadRequestException(detail="Hành động không hợp lệ")
        else:
            raise BadRequestException(detail="Yêu cầu không hợp lệ")

        # Ghi log hành động
        log_action(
            actor_id=current_user.id,
            action=(
                f"bulk_{update_request.action}"
                if update_request.action
                else "mark_all_read"
            ),
            resource_type="notifications",
            resource_id=None,
            ip_address=None,
        )

        return result
    except BadRequestException:
        raise
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating notifications: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật thông báo")


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark notification as read",
    description="Mark a specific notification as read",
)
@track_request_time
async def mark_notification_read(
    request: Request,
    notification_id: int = Path(..., description="Notification ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationResponse:
    """Mark a specific notification as read."""
    try:
        notification_service = NotificationService(db)
        notification = await notification_service.mark_as_read(
            user_id=current_user.id, notification_id=notification_id
        )

        if not notification:
            raise NotFoundException(detail="Notification not found")

        return notification
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        raise ServerException(detail="Failed to mark notification as read")


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all notifications as read",
    description="Mark all notifications or notifications of a specific category as read",
)
@track_request_time
@throttle_requests(max_requests=10, window_seconds=60)
async def mark_all_notifications_read(
    request: Request,
    category: Optional[NotificationCategory] = Query(
        None, description="Category of notifications to mark as read"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Mark all user notifications as read, optionally filtered by category."""
    try:
        notification_service = NotificationService(db)
        await notification_service.mark_all_as_read(
            user_id=current_user.id, category=category
        )
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        raise ServerException(detail="Failed to mark notifications as read")


@router.post(
    "/bulk-action",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Perform bulk action on notifications",
    description="Mark multiple notifications as read/unread or delete them",
)
@track_request_time
@throttle_requests(max_requests=5, window_seconds=60)
async def bulk_notification_action(
    request: Request,
    bulk_action: NotificationBulkAction = Body(..., description="Bulk action details"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Perform bulk actions on multiple notifications."""
    if not bulk_action.notification_ids:
        raise BadRequestException(detail="No notification IDs provided")

    try:
        notification_service = NotificationService(db)

        if bulk_action.action == "mark_read":
            await notification_service.bulk_mark_as_read(
                user_id=current_user.id, notification_ids=bulk_action.notification_ids
            )
        elif bulk_action.action == "mark_unread":
            await notification_service.bulk_mark_as_unread(
                user_id=current_user.id, notification_ids=bulk_action.notification_ids
            )
        elif bulk_action.action == "delete":
            await notification_service.bulk_delete(
                user_id=current_user.id, notification_ids=bulk_action.notification_ids
            )
        else:
            raise BadRequestException(detail="Invalid action specified")
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error performing bulk action on notifications: {str(e)}")
        raise ServerException(detail="Failed to perform bulk action on notifications")


@router.get(
    "/unread-count",
    response_model=Dict[str, Any],
    summary="Get unread notification count",
    description="Get the count of unread notifications, optionally by category",
)
@track_request_time
@cache_response(ttl=60)
async def get_unread_count(
    request: Request,
    category: Optional[NotificationCategory] = Query(
        None, description="Filter by category"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Get the count of unread notifications for the current user."""
    try:
        notification_service = NotificationService(db)
        count = await notification_service.get_unread_count(
            user_id=current_user.id, category=category
        )

        result = {"count": count}

        if category:
            result["category"] = category

        return result
    except Exception as e:
        logger.error(f"Error retrieving unread count: {str(e)}")
        raise ServerException(detail="Failed to retrieve unread notification count")


@router.post(
    "/{notification_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete notification",
    description="Delete a specific notification",
)
@track_request_time
async def delete_notification(
    request: Request,
    notification_id: int = Path(..., description="Notification ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Delete a specific notification."""
    try:
        notification_service = NotificationService(db)
        deleted = await notification_service.delete_notification(
            user_id=current_user.id, notification_id=notification_id
        )

        if not deleted:
            raise NotFoundException(detail="Notification not found")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        raise ServerException(detail="Failed to delete notification")


@router.get(
    "/settings",
    response_model=NotificationSettingsResponse,
    summary="Get notification settings",
    description="Retrieve the current notification settings for the user",
)
@track_request_time
@cache_response(ttl=600)
async def get_notification_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationSettingsResponse:
    """Retrieve the current notification settings for the user."""
    try:
        notification_service = NotificationService(db)
        settings = await notification_service.get_settings(user_id=current_user.id)

        return settings
    except Exception as e:
        logger.error(f"Error retrieving notification settings: {str(e)}")
        raise ServerException(detail="Failed to retrieve notification settings")


@router.put(
    "/settings",
    response_model=NotificationSettingsResponse,
    summary="Update notification settings",
    description="Update the notification settings for the user",
)
@track_request_time
async def update_notification_settings(
    request: Request,
    settings: NotificationSettingsUpdate = Body(
        ..., description="Updated notification settings"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationSettingsResponse:
    """Update the notification settings for the user."""
    try:
        notification_service = NotificationService(db)
        updated_settings = await notification_service.update_settings(
            user_id=current_user.id, settings=settings
        )

        return updated_settings
    except Exception as e:
        logger.error(f"Error updating notification settings: {str(e)}")
        raise ServerException(detail="Failed to update notification settings")


@router.post(
    "/register-device",
    status_code=status.HTTP_201_CREATED,
    summary="Register device for push notifications",
    description="Register a device token for receiving push notifications",
)
@track_request_time
@throttle_requests(max_requests=10, window_seconds=3600)
async def register_device(
    request: Request,
    device_data: DeviceRegistration = Body(
        ..., description="Device registration details"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, bool]:
    """Register a device for push notifications."""
    try:
        notification_service = NotificationService(db)

        # Check if user has reached the device limit (e.g., 10 devices)
        device_count = await notification_service.get_device_count(
            user_id=current_user.id
        )
        if device_count >= 10:
            raise BadRequestException(detail="Maximum number of devices reached (10)")

        success = await notification_service.register_device(
            user_id=current_user.id,
            device_token=device_data.device_token,
            device_type=device_data.device_type,
            device_name=device_data.device_name,
        )

        return {"registered": success}
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error registering device: {str(e)}")
        raise ServerException(detail="Failed to register device for notifications")


@router.delete(
    "/unregister-device",
    status_code=status.HTTP_200_OK,
    summary="Unregister device",
    description="Unregister a device token to stop receiving push notifications",
)
@track_request_time
async def unregister_device(
    request: Request,
    device_token: str = Query(..., description="Device token to unregister"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, bool]:
    """Unregister a device from push notifications."""
    try:
        notification_service = NotificationService(db)
        success = await notification_service.unregister_device(
            user_id=current_user.id, device_token=device_token
        )

        return {"unregistered": success}
    except Exception as e:
        logger.error(f"Error unregistering device: {str(e)}")
        raise ServerException(detail="Failed to unregister device")


@router.get(
    "/stats",
    response_model=NotificationStatsResponse,
    summary="Get notification statistics",
    description="Get statistics about user notifications",
)
@track_request_time
@cache_response(ttl=300)
async def get_notification_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NotificationStatsResponse:
    """Get statistics about user notifications."""
    try:
        notification_service = NotificationService(db)
        stats = await notification_service.get_notification_stats(
            user_id=current_user.id
        )

        return stats
    except Exception as e:
        logger.error(f"Error retrieving notification statistics: {str(e)}")
        raise ServerException(detail="Failed to retrieve notification statistics")


@router.post("/mark-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notifications_read(
    mark_request: NotificationMarkRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Mark notifications as read. Can mark all notifications or specific ones by ID.
    """
    try:
        notification_service = NotificationService(db)

        if mark_request.mark_all:
            await notification_service.mark_all_as_read(user_id=current_user.id)
            logger.info(f"User {current_user.id} marked all notifications as read")
        elif mark_request.notification_ids:
            await notification_service.mark_as_read(
                user_id=current_user.id, notification_ids=mark_request.notification_ids
            )
            logger.info(
                f"User {current_user.id} marked notifications {mark_request.notification_ids} as read"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either mark_all must be true or notification_ids must be provided",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error marking notifications as read for user {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark notifications as read: {str(e)}",
        )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_notifications(
    notification_type: Optional[str] = Query(
        None, description="Delete only notifications of this type"
    ),
    older_than: Optional[str] = Query(
        None, description="Delete notifications older than this date (ISO format)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Delete all notifications for the current user with optional filtering.
    """
    try:
        notification_service = NotificationService(db)
        count = await notification_service.delete_all_notifications(
            user_id=current_user.id,
            notification_type=notification_type,
            older_than=older_than,
        )
        logger.info(f"User {current_user.id} deleted {count} notifications")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error deleting notifications for user {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete notifications: {str(e)}",
        )


@router.post("/test", status_code=status.HTTP_204_NO_CONTENT)
@throttle_requests(max_requests=1, window_seconds=60)
async def send_test_notification(
    notification_type: str = Query(..., description="Type of notification to test"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Send a test notification of the specified type to the current user.
    """
    try:
        valid_types = [
            "follow",
            "like",
            "comment",
            "achievement",
            "system",
            "reading_reminder",
        ]
        if notification_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid notification type. Valid types are: {', '.join(valid_types)}",
            )

        notification_service = NotificationService(db)
        await notification_service.send_test_notification(
            user_id=current_user.id, notification_type=notification_type
        )
        logger.info(
            f"Sent test {notification_type} notification to user {current_user.id}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error sending test notification to user {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test notification: {str(e)}",
        )


@router.post("/bulk-create", status_code=status.HTTP_204_NO_CONTENT)
async def create_bulk_notifications(
    notifications: List[NotificationCreate] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Create multiple notifications at once (admin only).
    """
    try:
        # Check if user is admin
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can create bulk notifications",
            )

        notification_service = NotificationService(db)
        await notification_service.create_bulk_notifications(
            notifications=notifications
        )
        logger.info(
            f"Admin {current_user.id} created {len(notifications)} bulk notifications"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating bulk notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create bulk notifications: {str(e)}",
        )
