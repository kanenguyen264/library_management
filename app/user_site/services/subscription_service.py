from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.subscription_repo import SubscriptionRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.subscription_plan_repo import SubscriptionPlanRepository
from app.user_site.repositories.payment_repo import PaymentRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    ValidationException,
    ConflictException,
    PaymentException,
)
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.cache.decorators import cached
from app.monitoring.metrics.business_metrics import track_subscription
from app.security.audit.audit_trails import log_data_operation
from app.logs_manager.services import create_user_activity_log
from app.logging.setup import get_logger

logger = get_logger(__name__)


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.subscription_repo = SubscriptionRepository(db)
        self.user_repo = UserRepository(db)
        self.subscription_plan_repo = SubscriptionPlanRepository(db)
        self.payment_repo = PaymentRepository(db)

    @cached(
        ttl=3600,
        namespace="subscriptions",
        key_prefix="plans",
        tags=["subscription_plans"],
    )
    async def get_subscription_plans(self) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các gói đăng ký

        Returns:
            Danh sách các gói đăng ký
        """
        plans = await self.subscription_plan_repo.get_active_plans()

        result = []
        for plan in plans:
            result.append(
                {
                    "id": plan.id,
                    "name": plan.name,
                    "description": plan.description,
                    "price": plan.price,
                    "currency": plan.currency,
                    "duration_days": plan.duration_days,
                    "features": plan.features,
                    "is_popular": plan.is_popular,
                    "max_books": plan.max_books,
                    "is_active": plan.is_active,
                    "created_at": plan.created_at,
                }
            )

        return result

    @cached(
        ttl=300, namespace="subscriptions", key_prefix="user", tags=["subscriptions"]
    )
    async def get_user_subscription(self, user_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin đăng ký của người dùng

        Args:
            user_id: ID người dùng

        Returns:
            Thông tin đăng ký của người dùng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy đăng ký hiện tại
        subscription = await self.subscription_repo.get_active_subscription(user_id)

        if not subscription:
            return {
                "has_subscription": False,
                "subscription_status": "inactive",
                "user_id": user_id,
            }

        # Lấy thông tin gói đăng ký
        plan = await self.subscription_plan_repo.get_by_id(subscription.plan_id)

        # Tính toán thời gian còn lại
        now = datetime.now(timezone.utc)
        days_remaining = 0
        if subscription.expires_at and subscription.expires_at > now:
            days_remaining = (subscription.expires_at - now).days

        # Format kết quả
        result = {
            "has_subscription": True,
            "subscription_status": subscription.status,
            "user_id": user_id,
            "subscription_id": subscription.id,
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "description": plan.description,
                "price": plan.price,
                "currency": plan.currency,
                "features": plan.features,
                "max_books": plan.max_books,
            },
            "started_at": subscription.created_at,
            "expires_at": subscription.expires_at,
            "days_remaining": days_remaining,
            "auto_renew": subscription.auto_renew,
            "books_read_count": await self.subscription_repo.get_books_read_count(
                subscription.id
            ),
            "payment_status": subscription.payment_status,
            "updated_at": subscription.updated_at,
        }

        return result

    async def create_subscription(
        self, user_id: int, plan_id: int, payment_method: str, auto_renew: bool = False
    ) -> Dict[str, Any]:
        """
        Tạo đăng ký mới cho người dùng

        Args:
            user_id: ID người dùng
            plan_id: ID gói đăng ký
            payment_method: Phương thức thanh toán
            auto_renew: Tự động gia hạn

        Returns:
            Thông tin đăng ký mới

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc gói đăng ký
            ConflictException: Nếu người dùng đã có đăng ký đang hoạt động
            PaymentException: Nếu xử lý thanh toán thất bại
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Kiểm tra gói đăng ký tồn tại và đang hoạt động
        plan = await self.subscription_plan_repo.get_by_id(plan_id)
        if not plan or not plan.is_active:
            raise NotFoundException(f"Không tìm thấy gói đăng ký có ID {plan_id}")

        # Kiểm tra người dùng đã có đăng ký đang hoạt động chưa
        active_subscription = await self.subscription_repo.get_active_subscription(
            user_id
        )
        if active_subscription:
            raise ConflictException("Người dùng đã có đăng ký đang hoạt động")

        # Tính toán thời hạn đăng ký
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=plan.duration_days)

        # Tạo thanh toán
        payment_data = {
            "user_id": user_id,
            "amount": plan.price,
            "currency": plan.currency,
            "payment_method": payment_method,
            "description": f"Đăng ký gói {plan.name}",
            "status": "pending",
        }

        payment = await self.payment_repo.create(payment_data)

        # Xử lý thanh toán (giả định thành công)
        try:
            # Giả lập xử lý thanh toán
            # Trong thực tế, bạn cần tích hợp với một cổng thanh toán thực tế
            payment_successful = True

            if not payment_successful:
                raise PaymentException("Xử lý thanh toán thất bại")

            # Cập nhật trạng thái thanh toán
            await self.payment_repo.update(payment.id, {"status": "completed"})

            # Tạo đăng ký mới
            subscription_data = {
                "user_id": user_id,
                "plan_id": plan_id,
                "payment_id": payment.id,
                "status": "active",
                "expires_at": expires_at,
                "auto_renew": auto_renew,
                "payment_status": "completed",
            }

            subscription = await self.subscription_repo.create(subscription_data)

            # Cập nhật trạng thái người dùng
            await self.user_repo.update(
                user_id,
                {
                    "subscription_status": "active",
                    "subscription_id": subscription.id,
                    "max_books": plan.max_books,
                },
            )

            # Ghi log và theo dõi số liệu
            await log_data_operation(
                user_id=user_id,
                operation="create",
                entity_type="subscription",
                entity_id=subscription.id,
                metadata={
                    "plan_id": plan_id,
                    "payment_method": payment_method,
                    "auto_renew": auto_renew,
                },
            )

            track_subscription("create", plan.name)

            # Ghi log hoạt động người dùng
            await create_user_activity_log(
                self.db,
                UserActivityLogCreate(
                    user_id=user_id,
                    activity_type="SUBSCRIBE",
                    entity_type="SUBSCRIPTION",
                    entity_id=subscription.id,
                    description=f"Đăng ký gói {plan.name}",
                    metadata={
                        "plan_id": plan_id,
                        "plan_name": plan.name,
                        "auto_renew": auto_renew,
                    },
                ),
            )

            # Vô hiệu hóa cache
            await self._invalidate_subscription_cache(user_id)

            # Trả về thông tin đăng ký
            return {
                "subscription_id": subscription.id,
                "user_id": user_id,
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "price": plan.price,
                    "currency": plan.currency,
                    "duration_days": plan.duration_days,
                    "features": plan.features,
                    "max_books": plan.max_books,
                },
                "status": "active",
                "payment_status": "completed",
                "payment_id": payment.id,
                "started_at": subscription.created_at,
                "expires_at": expires_at,
                "days_remaining": plan.duration_days,
                "auto_renew": auto_renew,
                "created_at": subscription.created_at,
            }

        except Exception as e:
            # Nếu có lỗi, cập nhật trạng thái thanh toán
            await self.payment_repo.update(payment.id, {"status": "failed"})
            logger.error(f"Lỗi khi tạo đăng ký: {str(e)}")
            raise PaymentException(f"Không thể xử lý thanh toán: {str(e)}")

    async def cancel_subscription(self, user_id: int) -> Dict[str, Any]:
        """
        Hủy đăng ký của người dùng

        Args:
            user_id: ID người dùng

        Returns:
            Thông tin kết quả hủy đăng ký

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc đăng ký
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Kiểm tra đăng ký đang hoạt động
        subscription = await self.subscription_repo.get_active_subscription(user_id)
        if not subscription:
            raise NotFoundException("Không tìm thấy đăng ký đang hoạt động")

        # Hủy tự động gia hạn
        await self.subscription_repo.update(subscription.id, {"auto_renew": False})

        # Ghi log và theo dõi số liệu
        plan = await self.subscription_plan_repo.get_by_id(subscription.plan_id)

        await log_data_operation(
            user_id=user_id,
            operation="update",
            entity_type="subscription",
            entity_id=subscription.id,
            metadata={"action": "cancel_auto_renew", "plan_id": subscription.plan_id},
        )

        track_subscription("cancel_auto_renew", plan.name if plan else "unknown")

        # Ghi log hoạt động người dùng
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="UPDATE",
                entity_type="SUBSCRIPTION",
                entity_id=subscription.id,
                description="Hủy tự động gia hạn đăng ký",
                metadata={
                    "plan_id": subscription.plan_id,
                    "plan_name": plan.name if plan else "unknown",
                },
            ),
        )

        # Vô hiệu hóa cache
        await self._invalidate_subscription_cache(user_id)

        # Trả về kết quả
        return {
            "success": True,
            "message": "Đã hủy tự động gia hạn đăng ký",
            "subscription_id": subscription.id,
            "expires_at": subscription.expires_at,
        }

    async def renew_subscription(
        self, user_id: int, payment_method: str
    ) -> Dict[str, Any]:
        """
        Gia hạn đăng ký của người dùng

        Args:
            user_id: ID người dùng
            payment_method: Phương thức thanh toán

        Returns:
            Thông tin đăng ký đã gia hạn

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc đăng ký
            ValidationException: Nếu đăng ký còn hạn sử dụng
            PaymentException: Nếu xử lý thanh toán thất bại
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Kiểm tra đăng ký hiện tại
        current_subscription = await self.subscription_repo.get_active_subscription(
            user_id
        )
        if not current_subscription:
            raise NotFoundException("Không tìm thấy đăng ký đang hoạt động")

        # Kiểm tra đăng ký còn hạn sử dụng
        now = datetime.now(timezone.utc)
        if (
            current_subscription.expires_at
            and current_subscription.expires_at > now + timedelta(days=7)
        ):
            raise ValidationException("Đăng ký vẫn còn hạn sử dụng, chưa thể gia hạn")

        # Lấy thông tin gói đăng ký
        plan = await self.subscription_plan_repo.get_by_id(current_subscription.plan_id)
        if not plan or not plan.is_active:
            raise NotFoundException(
                f"Không tìm thấy gói đăng ký có ID {current_subscription.plan_id}"
            )

        # Tính toán thời hạn mới
        expires_at = None
        if current_subscription.expires_at and current_subscription.expires_at > now:
            # Gia hạn từ ngày hết hạn
            expires_at = current_subscription.expires_at + timedelta(
                days=plan.duration_days
            )
        else:
            # Gia hạn từ ngày hiện tại
            expires_at = now + timedelta(days=plan.duration_days)

        # Tạo thanh toán
        payment_data = {
            "user_id": user_id,
            "amount": plan.price,
            "currency": plan.currency,
            "payment_method": payment_method,
            "description": f"Gia hạn gói {plan.name}",
            "status": "pending",
        }

        payment = await self.payment_repo.create(payment_data)

        # Xử lý thanh toán (giả định thành công)
        try:
            # Giả lập xử lý thanh toán
            # Trong thực tế, bạn cần tích hợp với một cổng thanh toán thực tế
            payment_successful = True

            if not payment_successful:
                raise PaymentException("Xử lý thanh toán thất bại")

            # Cập nhật trạng thái thanh toán
            await self.payment_repo.update(payment.id, {"status": "completed"})

            # Cập nhật đăng ký
            await self.subscription_repo.update(
                current_subscription.id,
                {
                    "expires_at": expires_at,
                    "payment_id": payment.id,
                    "payment_status": "completed",
                    "status": "active",
                    "auto_renew": True,  # Mặc định bật tự động gia hạn khi gia hạn thủ công
                },
            )

            # Ghi log và theo dõi số liệu
            await log_data_operation(
                user_id=user_id,
                operation="update",
                entity_type="subscription",
                entity_id=current_subscription.id,
                metadata={
                    "action": "renew",
                    "plan_id": plan.id,
                    "payment_method": payment_method,
                },
            )

            track_subscription("renew", plan.name)

            # Ghi log hoạt động người dùng
            await create_user_activity_log(
                self.db,
                UserActivityLogCreate(
                    user_id=user_id,
                    activity_type="UPDATE",
                    entity_type="SUBSCRIPTION",
                    entity_id=current_subscription.id,
                    description=f"Gia hạn gói {plan.name}",
                    metadata={
                        "plan_id": plan.id,
                        "plan_name": plan.name,
                        "new_expires_at": (
                            expires_at.isoformat() if expires_at else None
                        ),
                    },
                ),
            )

            # Vô hiệu hóa cache
            await self._invalidate_subscription_cache(user_id)

            # Tính toán thời gian còn lại
            days_remaining = (expires_at - now).days if expires_at else 0

            # Trả về thông tin đăng ký
            return {
                "subscription_id": current_subscription.id,
                "user_id": user_id,
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "price": plan.price,
                    "currency": plan.currency,
                    "duration_days": plan.duration_days,
                },
                "status": "active",
                "payment_status": "completed",
                "payment_id": payment.id,
                "expires_at": expires_at,
                "days_remaining": days_remaining,
                "auto_renew": True,
                "renewed_at": now,
            }

        except Exception as e:
            # Nếu có lỗi, cập nhật trạng thái thanh toán
            await self.payment_repo.update(payment.id, {"status": "failed"})
            logger.error(f"Lỗi khi gia hạn đăng ký: {str(e)}")
            raise PaymentException(f"Không thể xử lý thanh toán: {str(e)}")

    async def change_subscription_plan(
        self, user_id: int, new_plan_id: int, payment_method: str
    ) -> Dict[str, Any]:
        """
        Thay đổi gói đăng ký của người dùng

        Args:
            user_id: ID người dùng
            new_plan_id: ID gói đăng ký mới
            payment_method: Phương thức thanh toán

        Returns:
            Thông tin đăng ký đã thay đổi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng, đăng ký hoặc gói đăng ký
            ValidationException: Nếu gói đăng ký mới giống gói hiện tại
            PaymentException: Nếu xử lý thanh toán thất bại
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Kiểm tra đăng ký hiện tại
        current_subscription = await self.subscription_repo.get_active_subscription(
            user_id
        )
        if not current_subscription:
            raise NotFoundException("Không tìm thấy đăng ký đang hoạt động")

        # Kiểm tra gói đăng ký mới
        new_plan = await self.subscription_plan_repo.get_by_id(new_plan_id)
        if not new_plan or not new_plan.is_active:
            raise NotFoundException(f"Không tìm thấy gói đăng ký có ID {new_plan_id}")

        # Kiểm tra gói mới khác gói hiện tại
        if current_subscription.plan_id == new_plan_id:
            raise ValidationException("Gói đăng ký mới giống gói hiện tại")

        # Lấy thông tin gói đăng ký hiện tại
        current_plan = await self.subscription_plan_repo.get_by_id(
            current_subscription.plan_id
        )

        # Tính toán thời hạn mới và chi phí
        now = datetime.now(timezone.utc)
        days_remaining = 0
        amount_to_pay = new_plan.price

        if current_subscription.expires_at and current_subscription.expires_at > now:
            # Tính số ngày còn lại của gói hiện tại
            days_remaining = (current_subscription.expires_at - now).days

            # Tính giá trị còn lại của gói hiện tại
            if current_plan and days_remaining > 0:
                daily_rate_current = current_plan.price / current_plan.duration_days
                remaining_value = daily_rate_current * days_remaining

                # Giảm giá trị còn lại từ giá gói mới
                amount_to_pay = max(0, new_plan.price - remaining_value)

        # Tính thời hạn mới
        expires_at = now + timedelta(days=new_plan.duration_days)

        # Tạo thanh toán
        payment_data = {
            "user_id": user_id,
            "amount": amount_to_pay,
            "currency": new_plan.currency,
            "payment_method": payment_method,
            "description": f"Đổi sang gói {new_plan.name}",
            "status": "pending",
        }

        payment = await self.payment_repo.create(payment_data)

        # Xử lý thanh toán (giả định thành công)
        try:
            # Giả lập xử lý thanh toán
            # Trong thực tế, bạn cần tích hợp với một cổng thanh toán thực tế
            payment_successful = True

            if not payment_successful:
                raise PaymentException("Xử lý thanh toán thất bại")

            # Cập nhật trạng thái thanh toán
            await self.payment_repo.update(payment.id, {"status": "completed"})

            # Cập nhật trạng thái đăng ký cũ
            await self.subscription_repo.update(
                current_subscription.id, {"status": "cancelled", "updated_at": now}
            )

            # Tạo đăng ký mới
            subscription_data = {
                "user_id": user_id,
                "plan_id": new_plan_id,
                "payment_id": payment.id,
                "status": "active",
                "expires_at": expires_at,
                "auto_renew": current_subscription.auto_renew,
                "payment_status": "completed",
            }

            new_subscription = await self.subscription_repo.create(subscription_data)

            # Cập nhật trạng thái người dùng
            await self.user_repo.update(
                user_id,
                {
                    "subscription_id": new_subscription.id,
                    "max_books": new_plan.max_books,
                },
            )

            # Ghi log và theo dõi số liệu
            await log_data_operation(
                user_id=user_id,
                operation="update",
                entity_type="subscription",
                entity_id=new_subscription.id,
                metadata={
                    "action": "change_plan",
                    "old_plan_id": current_subscription.plan_id,
                    "new_plan_id": new_plan_id,
                    "payment_method": payment_method,
                },
            )

            track_subscription("change_plan", new_plan.name)

            # Ghi log hoạt động người dùng
            await create_user_activity_log(
                self.db,
                UserActivityLogCreate(
                    user_id=user_id,
                    activity_type="UPDATE",
                    entity_type="SUBSCRIPTION",
                    entity_id=new_subscription.id,
                    description=f"Đổi từ gói {current_plan.name if current_plan else 'không xác định'} sang gói {new_plan.name}",
                    metadata={
                        "old_plan_id": current_subscription.plan_id,
                        "new_plan_id": new_plan_id,
                        "old_plan_name": (
                            current_plan.name if current_plan else "không xác định"
                        ),
                        "new_plan_name": new_plan.name,
                        "new_expires_at": (
                            expires_at.isoformat() if expires_at else None
                        ),
                    },
                ),
            )

            # Vô hiệu hóa cache
            await self._invalidate_subscription_cache(user_id)

            # Trả về thông tin đăng ký mới
            return {
                "subscription_id": new_subscription.id,
                "user_id": user_id,
                "plan": {
                    "id": new_plan.id,
                    "name": new_plan.name,
                    "price": new_plan.price,
                    "currency": new_plan.currency,
                    "duration_days": new_plan.duration_days,
                    "features": new_plan.features,
                    "max_books": new_plan.max_books,
                },
                "status": "active",
                "payment_status": "completed",
                "payment_id": payment.id,
                "started_at": new_subscription.created_at,
                "expires_at": expires_at,
                "days_remaining": new_plan.duration_days,
                "auto_renew": new_subscription.auto_renew,
                "changed_at": now,
                "previous_plan": {
                    "id": current_plan.id if current_plan else None,
                    "name": current_plan.name if current_plan else "không xác định",
                },
            }

        except Exception as e:
            # Nếu có lỗi, cập nhật trạng thái thanh toán
            await self.payment_repo.update(payment.id, {"status": "failed"})
            logger.error(f"Lỗi khi thay đổi gói đăng ký: {str(e)}")
            raise PaymentException(f"Không thể xử lý thanh toán: {str(e)}")

    async def toggle_auto_renew(self, user_id: int) -> Dict[str, Any]:
        """
        Bật/tắt tự động gia hạn đăng ký

        Args:
            user_id: ID người dùng

        Returns:
            Thông tin trạng thái tự động gia hạn

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc đăng ký
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Kiểm tra đăng ký đang hoạt động
        subscription = await self.subscription_repo.get_active_subscription(user_id)
        if not subscription:
            raise NotFoundException("Không tìm thấy đăng ký đang hoạt động")

        # Đảo ngược trạng thái tự động gia hạn
        new_auto_renew = not subscription.auto_renew

        # Cập nhật trạng thái
        await self.subscription_repo.update(
            subscription.id, {"auto_renew": new_auto_renew}
        )

        # Ghi log và theo dõi số liệu
        action = "enable_auto_renew" if new_auto_renew else "disable_auto_renew"

        await log_data_operation(
            user_id=user_id,
            operation="update",
            entity_type="subscription",
            entity_id=subscription.id,
            metadata={"action": action, "plan_id": subscription.plan_id},
        )

        track_subscription(action, "")

        # Ghi log hoạt động người dùng
        description = (
            "Bật tự động gia hạn đăng ký"
            if new_auto_renew
            else "Tắt tự động gia hạn đăng ký"
        )
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="UPDATE",
                entity_type="SUBSCRIPTION",
                entity_id=subscription.id,
                description=description,
                metadata={
                    "auto_renew": new_auto_renew,
                    "plan_id": subscription.plan_id,
                },
            ),
        )

        # Vô hiệu hóa cache
        await self._invalidate_subscription_cache(user_id)

        # Trả về kết quả
        return {
            "success": True,
            "message": "Đã "
            + ("bật" if new_auto_renew else "tắt")
            + " tự động gia hạn đăng ký",
            "subscription_id": subscription.id,
            "auto_renew": new_auto_renew,
            "expires_at": subscription.expires_at,
        }

    async def get_subscription_history(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Lấy lịch sử đăng ký của người dùng

        Args:
            user_id: ID người dùng

        Returns:
            Lịch sử đăng ký của người dùng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy lịch sử đăng ký
        subscriptions = await self.subscription_repo.get_user_subscriptions(user_id)

        # Lấy danh sách ID gói đăng ký
        plan_ids = [sub.plan_id for sub in subscriptions]

        # Lấy thông tin các gói đăng ký
        plans = await self.subscription_plan_repo.get_by_ids(plan_ids)
        plans_dict = {plan.id: plan for plan in plans}

        # Lấy ID các thanh toán
        payment_ids = [sub.payment_id for sub in subscriptions if sub.payment_id]

        # Lấy thông tin các thanh toán
        payments = await self.payment_repo.get_by_ids(payment_ids)
        payments_dict = {payment.id: payment for payment in payments}

        # Format kết quả
        result = []
        for subscription in subscriptions:
            plan = plans_dict.get(subscription.plan_id)
            payment = payments_dict.get(subscription.payment_id)

            sub_data = {
                "id": subscription.id,
                "status": subscription.status,
                "plan": {
                    "id": plan.id if plan else None,
                    "name": plan.name if plan else "Không xác định",
                    "price": plan.price if plan else 0,
                    "currency": plan.currency if plan else "VND",
                },
                "created_at": subscription.created_at,
                "expires_at": subscription.expires_at,
                "cancelled_at": subscription.cancelled_at,
                "auto_renew": subscription.auto_renew,
                "payment": {
                    "id": payment.id if payment else None,
                    "amount": payment.amount if payment else 0,
                    "currency": payment.currency if payment else "VND",
                    "payment_method": (
                        payment.payment_method if payment else "Không xác định"
                    ),
                    "status": payment.status if payment else "Không xác định",
                    "created_at": payment.created_at if payment else None,
                },
            }

            result.append(sub_data)

        # Sắp xếp theo thời gian tạo giảm dần
        result.sort(key=lambda x: x["created_at"], reverse=True)

        return result

    async def check_subscription_access(
        self, user_id: int, required_feature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Kiểm tra quyền truy cập dịch vụ đăng ký

        Args:
            user_id: ID người dùng
            required_feature: Tính năng yêu cầu (tùy chọn)

        Returns:
            Thông tin quyền truy cập
        """
        # Lấy thông tin đăng ký
        try:
            subscription_info = await self.get_user_subscription(user_id)
        except NotFoundException:
            return {"has_access": False, "reason": "user_not_found", "user_id": user_id}

        # Kiểm tra có đăng ký không
        if not subscription_info["has_subscription"]:
            return {
                "has_access": False,
                "reason": "no_subscription",
                "user_id": user_id,
            }

        # Kiểm tra đăng ký còn hoạt động không
        if subscription_info["subscription_status"] != "active":
            return {
                "has_access": False,
                "reason": "subscription_inactive",
                "status": subscription_info["subscription_status"],
            }

        # Kiểm tra còn thời hạn không
        if subscription_info["days_remaining"] <= 0:
            return {
                "has_access": False,
                "reason": "subscription_expired",
                "expires_at": subscription_info["expires_at"],
            }

        # Kiểm tra tính năng yêu cầu nếu có
        if required_feature and subscription_info["plan"]["features"]:
            features = subscription_info["plan"]["features"]

            if isinstance(features, list) and required_feature not in features:
                return {
                    "has_access": False,
                    "reason": "feature_not_available",
                    "required_feature": required_feature,
                }
            elif isinstance(features, dict) and not features.get(
                required_feature, False
            ):
                return {
                    "has_access": False,
                    "reason": "feature_not_available",
                    "required_feature": required_feature,
                }

        # Truy cập hợp lệ
        return {
            "has_access": True,
            "user_id": user_id,
            "subscription_id": subscription_info["subscription_id"],
            "plan_name": subscription_info["plan"]["name"],
            "days_remaining": subscription_info["days_remaining"],
        }

    # --- Helper methods --- #

    async def _invalidate_subscription_cache(self, user_id: int) -> None:
        """
        Vô hiệu hóa cache liên quan đến đăng ký

        Args:
            user_id: ID người dùng
        """
        # Giả sử đã thiết lập cache_manager từ app/cache/manager.py
        from app.cache.manager import cache_manager

        # Vô hiệu hóa cache đăng ký người dùng
        await cache_manager.invalidate_by_tags([f"user:{user_id}", "subscriptions"])
