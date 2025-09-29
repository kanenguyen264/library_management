from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.user_site.models.payment import PaymentTransaction as Payment
from app.user_site.repositories.payment_repo import PaymentRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.subscription_repo import SubscriptionRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.user_site.schemas.payment import PaymentCreate, PaymentUpdate
from app.core.exceptions import ConflictException, ServerException

# Logger for payment service
logger = logging.getLogger(__name__)


@cached(ttl=300, namespace="admin:payments", tags=["payments"])
async def get_all_payments(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    order_by: str = "created_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Payment]:
    """
    Lấy danh sách thanh toán.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        search: Từ khóa tìm kiếm
        status: Trạng thái thanh toán
        payment_method: Phương thức thanh toán
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách thanh toán
    """
    try:
        payments = await PaymentRepository.get_all(
            db,
            skip,
            limit,
            search,
            status,
            payment_method,
            start_date,
            end_date,
            order_by,
            order_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PAYMENTS",
                        entity_id=0,
                        description="Viewed payment list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search_query": search,
                            "status": status,
                            "payment_method": payment_method,
                            "start_date": (
                                start_date.isoformat() if start_date else None
                            ),
                            "end_date": end_date.isoformat() if end_date else None,
                            "sort_by": order_by,
                            "sort_desc": order_desc,
                            "results_count": len(payments),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return payments
    except Exception as e:
        logger.error(f"Error retrieving payments: {str(e)}")
        raise


async def count_payments(
    db: Session,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
) -> int:
    """
    Count payments matching filters.

    Args:
        db: Database session
        user_id: Filter by user ID
        status: Filter by payment status
        payment_method: Filter by payment method
        from_date: Filter payments after this date
        to_date: Filter payments before this date
        min_amount: Filter payments with amount greater than this
        max_amount: Filter payments with amount less than this

    Returns:
        Count of payments matching the filters
    """
    try:
        repo = PaymentRepository(db)

        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if status:
            filters["status"] = status
        if payment_method:
            filters["payment_method"] = payment_method
        if from_date:
            filters["from_date"] = from_date
        if to_date:
            filters["to_date"] = to_date
        if min_amount:
            filters["min_amount"] = min_amount
        if max_amount:
            filters["max_amount"] = max_amount

        count = await repo.count(filters=filters)

        return count
    except Exception as e:
        logger.error(f"Error counting payments: {str(e)}")
        raise


@cached(ttl=3600, namespace="admin:payments", tags=["payments"])
async def get_payment_by_id(
    db: Session, payment_id: int, admin_id: Optional[int] = None
) -> Payment:
    """
    Lấy thông tin thanh toán theo ID.

    Args:
        db: Database session
        payment_id: ID thanh toán
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thanh toán

    Raises:
        NotFoundException: Nếu không tìm thấy thanh toán
    """
    try:
        payment = await PaymentRepository.get_by_id(db, payment_id)

        if not payment:
            logger.warning(f"Payment with ID {payment_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy thanh toán với ID={payment_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PAYMENT",
                        entity_id=payment_id,
                        description=f"Viewed payment details: {payment.transaction_id}",
                        metadata={
                            "transaction_id": payment.transaction_id,
                            "amount": payment.amount,
                            "currency": payment.currency,
                            "status": payment.status,
                            "payment_method": payment.payment_method,
                            "created_at": (
                                payment.created_at.isoformat()
                                if payment.created_at
                                else None
                            ),
                            "updated_at": (
                                payment.updated_at.isoformat()
                                if payment.updated_at
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return payment
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving payment: {str(e)}")
        raise


@cached(key_prefix="admin_user_payments", ttl=300)
async def get_user_payments(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
) -> List[Payment]:
    """
    Get list of payments for a specific user.

    Args:
        db: Database session
        user_id: User ID
        skip: Number of records to skip
        limit: Maximum number of records to return
        status: Filter by payment status
        sort_by: Field to sort by
        sort_desc: Sort in descending order if True

    Returns:
        List of user payments

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        filters = {"user_id": user_id}
        if status:
            filters["status"] = status

        repo = PaymentRepository(db)
        return await repo.list(
            skip=skip,
            limit=limit,
            filters=filters,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user payments: {str(e)}")
        raise


async def get_user_payment_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """
    Get payment summary for a specific user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Summary of user payments

    Raises:
        NotFoundException: If user not found
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(detail=f"User with ID {user_id} not found")

        repo = PaymentRepository(db)

        # Get stats for different payment statuses
        total_amount = await repo.get_user_total_amount(user_id)
        successful_payments = await repo.count(
            filters={"user_id": user_id, "status": "completed"}
        )
        failed_payments = await repo.count(
            filters={"user_id": user_id, "status": "failed"}
        )
        pending_payments = await repo.count(
            filters={"user_id": user_id, "status": "pending"}
        )

        # Get latest payment
        latest_payments = await repo.list(
            skip=0,
            limit=1,
            filters={"user_id": user_id},
            sort_by="created_at",
            sort_desc=True,
        )
        latest_payment = latest_payments[0] if latest_payments else None

        # Get subscription info if available
        subscription_repo = SubscriptionRepository(db)
        active_subscription = await subscription_repo.get_active_by_user(user_id)

        return {
            "total_amount": total_amount,
            "successful_payments": successful_payments,
            "failed_payments": failed_payments,
            "pending_payments": pending_payments,
            "total_payments": successful_payments + failed_payments + pending_payments,
            "latest_payment": latest_payment.id if latest_payment else None,
            "latest_payment_date": (
                latest_payment.created_at if latest_payment else None
            ),
            "latest_payment_status": latest_payment.status if latest_payment else None,
            "has_active_subscription": active_subscription is not None,
            "subscription_id": active_subscription.id if active_subscription else None,
            "subscription_expires": (
                active_subscription.expires_at if active_subscription else None
            ),
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user payment summary: {str(e)}")
        raise


@invalidate_cache(tags=["payments"])
async def create_payment(
    db: Session, payment_data: PaymentCreate, admin_id: Optional[int] = None
) -> Payment:
    """
    Tạo thanh toán mới.

    Args:
        db: Database session
        payment_data: Thông tin thanh toán mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thanh toán đã tạo

    Raises:
        ConflictException: Nếu thanh toán đã tồn tại
    """
    try:
        # Kiểm tra xem thanh toán đã tồn tại chưa
        existing_payment = await PaymentRepository.get_by_transaction_id(
            db, payment_data.transaction_id
        )

        if existing_payment:
            logger.warning(
                f"Payment with transaction ID {payment_data.transaction_id} already exists"
            )
            raise ConflictException(
                detail=f"Thanh toán với mã giao dịch {payment_data.transaction_id} đã tồn tại"
            )

        # Chuyển đổi dữ liệu
        payment_dict = payment_data.model_dump()

        # Tạo thanh toán mới
        payment = await PaymentRepository.create(db, payment_dict)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="PAYMENT",
                        entity_id=payment.id,
                        description=f"Created new payment: {payment.transaction_id}",
                        metadata={
                            "transaction_id": payment.transaction_id,
                            "amount": payment.amount,
                            "currency": payment.currency,
                            "status": payment.status,
                            "payment_method": payment.payment_method,
                            "user_id": payment.user_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new payment with ID {payment.id}")
        return payment
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        raise ServerException(detail=f"Không thể tạo thanh toán: {str(e)}")


@invalidate_cache(tags=["payments"])
async def update_payment(
    db: Session,
    payment_id: int,
    payment_data: PaymentUpdate,
    admin_id: Optional[int] = None,
) -> Payment:
    """
    Cập nhật thông tin thanh toán.

    Args:
        db: Database session
        payment_id: ID thanh toán
        payment_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thanh toán đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy thanh toán
        ConflictException: Nếu mã giao dịch đã tồn tại
    """
    try:
        # Kiểm tra thanh toán tồn tại
        payment = await get_payment_by_id(db, payment_id)

        # Kiểm tra xem mã giao dịch mới có trùng với thanh toán khác không
        if (
            payment_data.transaction_id
            and payment_data.transaction_id != payment.transaction_id
        ):
            existing_payment = await PaymentRepository.get_by_transaction_id(
                db, payment_data.transaction_id
            )

            if existing_payment:
                logger.warning(
                    f"Payment with transaction ID {payment_data.transaction_id} already exists"
                )
                raise ConflictException(
                    detail=f"Thanh toán với mã giao dịch {payment_data.transaction_id} đã tồn tại"
                )

        # Chuyển đổi dữ liệu
        update_data = payment_data.model_dump(exclude_unset=True)

        # Cập nhật thanh toán
        updated_payment = await PaymentRepository.update(db, payment_id, update_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="PAYMENT",
                        entity_id=payment_id,
                        description=f"Updated payment: {updated_payment.transaction_id}",
                        metadata={
                            "updated_fields": list(update_data.keys()),
                            "old_values": {
                                k: getattr(payment, k) for k in update_data.keys()
                            },
                            "new_values": {
                                k: getattr(updated_payment, k)
                                for k in update_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated payment with ID {payment_id}")
        return updated_payment
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error updating payment: {str(e)}")
        raise ServerException(
            detail=f"Không thể cập nhật thanh toán với ID={payment_id}"
        )


@invalidate_cache(tags=["payments"])
async def delete_payment(
    db: Session, payment_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa thanh toán.

    Args:
        db: Database session
        payment_id: ID thanh toán
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy thanh toán
    """
    try:
        # Kiểm tra thanh toán tồn tại
        payment = await get_payment_by_id(db, payment_id)

        # Xóa thanh toán
        await PaymentRepository.delete(db, payment_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="PAYMENT",
                        entity_id=payment_id,
                        description=f"Deleted payment: {payment.transaction_id}",
                        metadata={
                            "transaction_id": payment.transaction_id,
                            "amount": payment.amount,
                            "currency": payment.currency,
                            "status": payment.status,
                            "payment_method": payment.payment_method,
                            "user_id": payment.user_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted payment with ID {payment_id}")
        return True
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting payment: {str(e)}")
        raise ServerException(detail=f"Không thể xóa thanh toán với ID={payment_id}")


@cached(key_prefix="admin_payment_statistics", ttl=3600)
async def get_payment_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê thanh toán.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê thanh toán
    """
    try:
        repo = PaymentRepository(db)

        total = await repo.count_payments()

        # Thống kê theo trạng thái
        by_status = await repo.count_payments_by_status()

        # Thống kê theo phương thức thanh toán
        by_method = await repo.count_payments_by_method()

        # Thống kê theo thời gian
        by_time = await repo.count_payments_by_time()

        # Thống kê theo số tiền
        by_amount = await repo.count_payments_by_amount()

        stats = {
            "total": total,
            "by_status": by_status,
            "by_method": by_method,
            "by_time": by_time,
            "by_amount": by_amount,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PAYMENT_STATISTICS",
                        entity_id=0,
                        description="Viewed payment statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving payment statistics: {str(e)}")
        raise
