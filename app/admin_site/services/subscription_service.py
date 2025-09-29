from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.user_site.models.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionType,
)
from app.user_site.repositories.subscription_repo import SubscriptionRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException, ConflictException
from app.common.utils.cache import cached, remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho subscription service
logger = logging.getLogger(__name__)


async def get_all_subscriptions(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    status: Optional[SubscriptionStatus] = None,
    subscription_type: Optional[SubscriptionType] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Subscription]:
    """
    Lấy danh sách đăng ký với các bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        status: Lọc theo trạng thái đăng ký
        subscription_type: Lọc theo loại đăng ký
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách đăng ký
    """
    try:
        repo = SubscriptionRepository(db)
        subscriptions = await repo.list_subscriptions(
            skip=skip,
            limit=limit,
            user_id=user_id,
            status=status,
            subscription_type=subscription_type,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                activity_description = "Viewed subscriptions list"
                if user_id:
                    activity_description = f"Viewed subscriptions for user {user_id}"

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SUBSCRIPTIONS",
                        entity_id=0,
                        description=activity_description,
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "status": status.value if status else None,
                            "subscription_type": (
                                subscription_type.value if subscription_type else None
                            ),
                            "from_date": from_date.isoformat() if from_date else None,
                            "to_date": to_date.isoformat() if to_date else None,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(subscriptions),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return subscriptions
    except Exception as e:
        logger.error(f"Error retrieving subscriptions: {str(e)}")
        raise


async def count_subscriptions(
    db: Session,
    user_id: Optional[int] = None,
    status: Optional[SubscriptionStatus] = None,
    subscription_type: Optional[SubscriptionType] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> int:
    """
    Đếm số lượng đăng ký.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        status: Lọc theo trạng thái đăng ký
        subscription_type: Lọc theo loại đăng ký
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày

    Returns:
        Số lượng đăng ký
    """
    try:
        repo = SubscriptionRepository(db)
        return await repo.count_subscriptions(
            user_id=user_id,
            status=status,
            subscription_type=subscription_type,
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as e:
        logger.error(f"Error counting subscriptions: {str(e)}")
        raise


@cached(key_prefix="admin_subscription", ttl=300)
async def get_subscription_by_id(
    db: Session, subscription_id: int, admin_id: Optional[int] = None
) -> Subscription:
    """
    Lấy thông tin đăng ký theo ID.

    Args:
        db: Database session
        subscription_id: ID của đăng ký
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin đăng ký

    Raises:
        NotFoundException: Nếu không tìm thấy đăng ký
    """
    try:
        repo = SubscriptionRepository(db)
        subscription = await repo.get_by_id(subscription_id)

        if not subscription:
            logger.warning(f"Subscription with ID {subscription_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy đăng ký với ID {subscription_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SUBSCRIPTION",
                        entity_id=subscription_id,
                        description=f"Viewed subscription details for ID {subscription_id}",
                        metadata={
                            "user_id": (
                                subscription.user_id
                                if hasattr(subscription, "user_id")
                                else None
                            ),
                            "status": (
                                subscription.status.value
                                if hasattr(subscription, "status")
                                else None
                            ),
                            "subscription_type": (
                                subscription.subscription_type.value
                                if hasattr(subscription, "subscription_type")
                                else None
                            ),
                            "start_date": (
                                subscription.start_date.isoformat()
                                if hasattr(subscription, "start_date")
                                and subscription.start_date
                                else None
                            ),
                            "end_date": (
                                subscription.end_date.isoformat()
                                if hasattr(subscription, "end_date")
                                and subscription.end_date
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return subscription
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving subscription: {str(e)}")
        raise


async def get_user_active_subscription(
    db: Session, user_id: int
) -> Optional[Subscription]:
    """
    Lấy đăng ký đang hoạt động của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Thông tin đăng ký hoặc None nếu không có
    """
    try:
        repo = SubscriptionRepository(db)
        return await repo.get_user_active_subscription(user_id)
    except Exception as e:
        logger.error(f"Error retrieving active subscription: {str(e)}")
        raise


async def create_subscription(
    db: Session, subscription_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Subscription:
    """
    Tạo đăng ký mới.

    Args:
        db: Database session
        subscription_data: Dữ liệu đăng ký
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin đăng ký đã tạo
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(subscription_data["user_id"])

        if not user:
            logger.warning(f"User with ID {subscription_data['user_id']} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {subscription_data['user_id']}"
            )

        # Nếu đang tạo subscription ACTIVE, hãy hủy các subscription ACTIVE hiện tại
        repo = SubscriptionRepository(db)

        if subscription_data.get("status") == SubscriptionStatus.ACTIVE:
            active_sub = await repo.get_user_active_subscription(
                subscription_data["user_id"]
            )
            if active_sub:
                # Hủy subscription hiện tại
                await repo.update(
                    active_sub.id,
                    {
                        "status": SubscriptionStatus.CANCELLED,
                        "end_date": datetime.now(timezone.utc),
                        "cancellation_date": datetime.now(timezone.utc),
                        "cancellation_reason": "Superseded by new subscription",
                    },
                )

                # Xóa cache
                remove_cache(f"admin_subscription:{active_sub.id}")

        # Tạo đăng ký mới
        subscription = await repo.create(subscription_data)

        # Cập nhật trạng thái premium cho người dùng nếu đăng ký đang hoạt động
        if subscription.status == SubscriptionStatus.ACTIVE:
            await user_repo.set_premium_status(
                user_id=subscription.user_id,
                is_premium=True,
                premium_until=subscription.end_date,
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="SUBSCRIPTION",
                        entity_id=subscription.id,
                        description=f"Created new subscription for user {subscription.user_id}",
                        metadata={
                            "user_id": subscription.user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "subscription_type": (
                                subscription.subscription_type.value
                                if hasattr(subscription, "subscription_type")
                                else None
                            ),
                            "status": (
                                subscription.status.value
                                if hasattr(subscription, "status")
                                else None
                            ),
                            "start_date": (
                                subscription.start_date.isoformat()
                                if hasattr(subscription, "start_date")
                                and subscription.start_date
                                else None
                            ),
                            "end_date": (
                                subscription.end_date.isoformat()
                                if hasattr(subscription, "end_date")
                                and subscription.end_date
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Created new subscription with ID {subscription.id} for user {subscription.user_id}"
        )
        return subscription
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating subscription: {str(e)}")
        raise


async def update_subscription(
    db: Session,
    subscription_id: int,
    subscription_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Subscription:
    """
    Cập nhật thông tin đăng ký.

    Args:
        db: Database session
        subscription_id: ID của đăng ký
        subscription_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin đăng ký đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy đăng ký
    """
    try:
        repo = SubscriptionRepository(db)

        # Kiểm tra đăng ký tồn tại
        subscription = await get_subscription_by_id(db, subscription_id)

        # Cập nhật đăng ký
        updated_subscription = await repo.update(subscription_id, subscription_data)

        # Xóa cache
        remove_cache(f"admin_subscription:{subscription_id}")

        # Cập nhật trạng thái premium nếu trạng thái đăng ký thay đổi
        if "status" in subscription_data:
            user_repo = UserRepository(db)

            if subscription_data["status"] == SubscriptionStatus.ACTIVE:
                await user_repo.set_premium_status(
                    user_id=subscription.user_id,
                    is_premium=True,
                    premium_until=updated_subscription.end_date,
                )
            elif subscription_data["status"] in [
                SubscriptionStatus.CANCELLED,
                SubscriptionStatus.EXPIRED,
            ]:
                # Kiểm tra xem người dùng còn đăng ký active nào khác không
                active_sub = await repo.get_user_active_subscription(
                    subscription.user_id
                )

                if not active_sub:
                    await user_repo.set_premium_status(
                        user_id=subscription.user_id,
                        is_premium=False,
                        premium_until=None,
                    )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="SUBSCRIPTION",
                        entity_id=subscription_id,
                        description=f"Updated subscription for user {subscription.user_id}",
                        metadata={
                            "user_id": subscription.user_id,
                            "previous_status": (
                                subscription.status.value
                                if hasattr(subscription, "status")
                                else None
                            ),
                            "new_status": (
                                subscription_data.get(
                                    "status", subscription.status
                                ).value
                                if isinstance(
                                    subscription_data.get("status"), SubscriptionStatus
                                )
                                else subscription_data.get("status")
                            ),
                            "updates": {
                                k: (
                                    v.value
                                    if isinstance(
                                        v, (SubscriptionStatus, SubscriptionType)
                                    )
                                    else v
                                )
                                for k, v in subscription_data.items()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated subscription with ID {subscription_id}")
        return updated_subscription
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating subscription: {str(e)}")
        raise


async def cancel_subscription(
    db: Session,
    subscription_id: int,
    reason: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> Subscription:
    """
    Hủy đăng ký.

    Args:
        db: Database session
        subscription_id: ID của đăng ký
        reason: Lý do hủy
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin đăng ký đã hủy

    Raises:
        NotFoundException: Nếu không tìm thấy đăng ký
    """
    try:
        repo = SubscriptionRepository(db)

        # Kiểm tra đăng ký tồn tại
        subscription = await get_subscription_by_id(db, subscription_id)

        # Chỉ có thể hủy đăng ký đang hoạt động
        if subscription.status != SubscriptionStatus.ACTIVE:
            logger.warning(
                f"Cannot cancel subscription {subscription_id} with status {subscription.status}"
            )
            raise ConflictException(detail=f"Không thể hủy đăng ký không hoạt động")

        # Cập nhật trạng thái đăng ký
        updated_data = {
            "status": SubscriptionStatus.CANCELLED,
            "cancellation_date": datetime.now(timezone.utc),
            "cancellation_reason": reason or "Cancelled by admin",
        }

        updated_subscription = await repo.update(subscription_id, updated_data)

        # Xóa cache
        remove_cache(f"admin_subscription:{subscription_id}")

        # Kiểm tra xem người dùng còn đăng ký active nào khác không
        active_sub = await repo.get_user_active_subscription(subscription.user_id)

        if not active_sub:
            user_repo = UserRepository(db)
            await user_repo.set_premium_status(
                user_id=subscription.user_id, is_premium=False, premium_until=None
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CANCEL",
                        entity_type="SUBSCRIPTION",
                        entity_id=subscription_id,
                        description=f"Cancelled subscription for user {subscription.user_id}",
                        metadata={
                            "user_id": subscription.user_id,
                            "subscription_type": (
                                subscription.subscription_type.value
                                if hasattr(subscription, "subscription_type")
                                else None
                            ),
                            "start_date": (
                                subscription.start_date.isoformat()
                                if hasattr(subscription, "start_date")
                                and subscription.start_date
                                else None
                            ),
                            "end_date": (
                                subscription.end_date.isoformat()
                                if hasattr(subscription, "end_date")
                                and subscription.end_date
                                else None
                            ),
                            "cancellation_date": updated_data[
                                "cancellation_date"
                            ].isoformat(),
                            "cancellation_reason": updated_data["cancellation_reason"],
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Cancelled subscription with ID {subscription_id}")
        return updated_subscription
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling subscription: {str(e)}")
        raise


async def delete_subscription(
    db: Session, subscription_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa đăng ký.

    Args:
        db: Database session
        subscription_id: ID của đăng ký
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy đăng ký
    """
    try:
        repo = SubscriptionRepository(db)

        # Kiểm tra đăng ký tồn tại
        subscription = await get_subscription_by_id(db, subscription_id)

        # Log admin activity before deletion
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="SUBSCRIPTION",
                        entity_id=subscription_id,
                        description=f"Deleted subscription for user {subscription.user_id}",
                        metadata={
                            "user_id": subscription.user_id,
                            "subscription_type": (
                                subscription.subscription_type.value
                                if hasattr(subscription, "subscription_type")
                                else None
                            ),
                            "status": (
                                subscription.status.value
                                if hasattr(subscription, "status")
                                else None
                            ),
                            "start_date": (
                                subscription.start_date.isoformat()
                                if hasattr(subscription, "start_date")
                                and subscription.start_date
                                else None
                            ),
                            "end_date": (
                                subscription.end_date.isoformat()
                                if hasattr(subscription, "end_date")
                                and subscription.end_date
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Xóa đăng ký
        await repo.delete(subscription_id)

        # Xóa cache
        remove_cache(f"admin_subscription:{subscription_id}")

        # Nếu đăng ký đang hoạt động, cập nhật trạng thái premium của người dùng
        if subscription.status == SubscriptionStatus.ACTIVE:
            user_repo = UserRepository(db)

            # Kiểm tra xem người dùng còn đăng ký active nào khác không
            active_sub = await repo.get_user_active_subscription(subscription.user_id)

            if not active_sub:
                await user_repo.set_premium_status(
                    user_id=subscription.user_id, is_premium=False, premium_until=None
                )

        logger.info(f"Deleted subscription with ID {subscription_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting subscription: {str(e)}")
        raise


@cached(key_prefix="admin_subscription_statistics", ttl=3600)
async def get_subscription_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê đăng ký.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê đăng ký
    """
    try:
        repo = SubscriptionRepository(db)

        total = await repo.count_subscriptions()
        active = await repo.count_subscriptions(status=SubscriptionStatus.ACTIVE)
        cancelled = await repo.count_subscriptions(status=SubscriptionStatus.CANCELLED)
        expired = await repo.count_subscriptions(status=SubscriptionStatus.EXPIRED)

        # Thống kê theo loại đăng ký
        monthly = await repo.count_subscriptions(
            subscription_type=SubscriptionType.MONTHLY
        )
        quarterly = await repo.count_subscriptions(
            subscription_type=SubscriptionType.QUARTERLY
        )
        yearly = await repo.count_subscriptions(
            subscription_type=SubscriptionType.YEARLY
        )

        # Thống kê theo thời gian
        now = datetime.now(timezone.utc)
        this_month = await repo.count_subscriptions(
            from_date=datetime(now.year, now.month, 1),
            to_date=(
                datetime(now.year, now.month + 1, 1)
                if now.month < 12
                else datetime(now.year + 1, 1, 1)
            ),
        )

        stats = {
            "total": total,
            "active": active,
            "cancelled": cancelled,
            "expired": expired,
            "monthly": monthly,
            "quarterly": quarterly,
            "yearly": yearly,
            "this_month": this_month,
            "active_rate": round(active / total * 100, 2) if total > 0 else 0,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SUBSCRIPTION_STATISTICS",
                        entity_id=0,
                        description="Viewed subscription statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving subscription statistics: {str(e)}")
        raise


async def check_expired_subscriptions(db: Session) -> int:
    """
    Kiểm tra và cập nhật các đăng ký đã hết hạn.

    Args:
        db: Database session

    Returns:
        Số lượng đăng ký đã cập nhật
    """
    try:
        repo = SubscriptionRepository(db)
        user_repo = UserRepository(db)
        now = datetime.now(timezone.utc)

        # Lấy danh sách đăng ký đã hết hạn nhưng chưa được cập nhật
        expired_subs = await repo.list_subscriptions(
            status=SubscriptionStatus.ACTIVE, end_date_before=now
        )

        count = 0
        for sub in expired_subs:
            # Cập nhật trạng thái đăng ký
            await repo.update(sub.id, {"status": SubscriptionStatus.EXPIRED})

            # Xóa cache
            remove_cache(f"admin_subscription:{sub.id}")

            # Kiểm tra xem người dùng còn đăng ký active nào khác không
            active_sub = await repo.get_user_active_subscription(sub.user_id)

            if not active_sub:
                await user_repo.set_premium_status(
                    user_id=sub.user_id, is_premium=False, premium_until=None
                )

            count += 1

        if count > 0:
            logger.info(f"Updated {count} expired subscriptions")

        return count
    except Exception as e:
        logger.error(f"Error checking expired subscriptions: {str(e)}")
        raise
