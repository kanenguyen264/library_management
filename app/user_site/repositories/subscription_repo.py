from typing import Optional, List, Dict, Any
from datetime import datetime, date  # Import date
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.user_site.models.subscription import SubscriptionPlan, UserSubscription
from app.core.exceptions import NotFoundException


class SubscriptionRepository:
    """Repository cho các thao tác với SubscriptionPlan và UserSubscription."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    # SubscriptionPlan methods

    async def create_plan(self, plan_data: Dict[str, Any]) -> SubscriptionPlan:
        """Tạo một gói đăng ký mới."""
        # Lọc các trường hợp lệ cho SubscriptionPlan
        allowed_fields = {
            "name",
            "description",
            "price",
            "currency",
            "billing_cycle",
            "features_json",
            "is_active",
        }
        filtered_data = {k: v for k, v in plan_data.items() if k in allowed_fields}
        plan = SubscriptionPlan(**filtered_data)
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def get_plan_by_id(self, plan_id: int) -> Optional[SubscriptionPlan]:
        """Lấy gói đăng ký theo ID."""
        query = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_plans(
        self,
        skip: int = 0,
        limit: int = 100,
        only_active: bool = True,
        sort_by: str = "name",
        sort_desc: bool = False,
    ) -> List[SubscriptionPlan]:
        """Liệt kê danh sách gói đăng ký."""
        query = select(SubscriptionPlan)

        if only_active:
            query = query.where(SubscriptionPlan.is_active == True)

        # Sắp xếp
        sort_attr = getattr(SubscriptionPlan, sort_by, SubscriptionPlan.name)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_plans(self, only_active: bool = True) -> int:
        """Đếm số lượng gói đăng ký."""
        query = select(func.count(SubscriptionPlan.id))

        if only_active:
            query = query.where(SubscriptionPlan.is_active == True)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update_plan(self, plan_id: int, data: Dict[str, Any]) -> SubscriptionPlan:
        """Cập nhật thông tin gói đăng ký."""
        plan = await self.get_plan_by_id(plan_id)
        if not plan:
            raise NotFoundException(
                detail=f"Không tìm thấy gói đăng ký với ID {plan_id}"
            )

        allowed_fields = {
            "name",
            "description",
            "price",
            "currency",
            "billing_cycle",
            "features_json",
            "is_active",
        }
        for key, value in data.items():
            if key in allowed_fields:
                setattr(plan, key, value)

        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def delete_plan(self, plan_id: int, hard_delete: bool = False) -> bool:
        """Xóa (mềm hoặc cứng) gói đăng ký."""
        plan = await self.get_plan_by_id(plan_id)
        if not plan:
            raise NotFoundException(
                detail=f"Không tìm thấy gói đăng ký với ID {plan_id}"
            )

        if hard_delete:
            # Cảnh báo: Xóa cứng cần xử lý các UserSubscription liên quan
            await self.db.delete(plan)
        else:
            # Xóa mềm: Đánh dấu là không hoạt động
            plan.is_active = False

        await self.db.commit()
        return True

    # UserSubscription methods

    async def create_subscription(
        self, subscription_data: Dict[str, Any]
    ) -> UserSubscription:
        """Tạo đăng ký mới cho người dùng."""
        # Lọc các trường hợp lệ cho UserSubscription
        # Bao gồm cả cột auto_renew mới thêm
        allowed_fields = {
            "user_id",
            "plan_id",
            "status",
            "start_date",
            "end_date",
            "renewal_date",
            "payment_method",
            "auto_renew",
            "billing_info_json",
        }
        filtered_data = {
            k: v for k, v in subscription_data.items() if k in allowed_fields
        }
        subscription = UserSubscription(**filtered_data)
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def get_subscription_by_id(
        self, subscription_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[UserSubscription]:
        """Lấy đăng ký theo ID, tùy chọn load relations."""
        query = select(UserSubscription).where(UserSubscription.id == subscription_id)

        if with_relations:
            options = []
            if "plan" in with_relations:
                options.append(selectinload(UserSubscription.plan))
            if "user" in with_relations:
                options.append(selectinload(UserSubscription.user))
            if "transactions" in with_relations:
                options.append(selectinload(UserSubscription.transactions))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_active_subscription(
        self, user_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[UserSubscription]:
        """Lấy đăng ký hiện tại đang hoạt động của người dùng."""
        query = select(UserSubscription).where(
            and_(
                UserSubscription.user_id == user_id, UserSubscription.status == "active"
            )
        )

        if with_relations:
            options = []
            if "plan" in with_relations:
                options.append(selectinload(UserSubscription.plan))
            if "transactions" in with_relations:
                options.append(selectinload(UserSubscription.transactions))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_user_subscriptions(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        with_relations: Optional[List[str]] = None,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> List[UserSubscription]:
        """Liệt kê lịch sử đăng ký của người dùng."""
        query = select(UserSubscription).where(UserSubscription.user_id == user_id)

        if status:
            query = query.where(UserSubscription.status == status)

        if with_relations:
            options = []
            if "plan" in with_relations:
                options.append(selectinload(UserSubscription.plan))
            if "transactions" in with_relations:
                options.append(selectinload(UserSubscription.transactions))
            if options:
                query = query.options(*options)

        # Sắp xếp
        sort_attr = getattr(UserSubscription, sort_by, UserSubscription.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_user_subscriptions(
        self, user_id: int, status: Optional[str] = None
    ) -> int:
        """Đếm số lượng đăng ký của người dùng."""
        query = select(func.count(UserSubscription.id)).where(
            UserSubscription.user_id == user_id
        )
        if status:
            query = query.where(UserSubscription.status == status)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update_subscription(
        self, subscription_id: int, data: Dict[str, Any]
    ) -> UserSubscription:
        """Cập nhật thông tin đăng ký."""
        subscription = await self.get_subscription_by_id(subscription_id)
        if not subscription:
            raise NotFoundException(
                detail=f"Không tìm thấy đăng ký với ID {subscription_id}"
            )

        allowed_fields = {
            "plan_id",
            "status",
            "start_date",
            "end_date",
            "renewal_date",
            "payment_method",
            "auto_renew",
            "billing_info_json",
        }
        for key, value in data.items():
            if key in allowed_fields:
                setattr(subscription, key, value)

        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def cancel_subscription(self, subscription_id: int) -> UserSubscription:
        """Hủy đăng ký (đặt trạng thái là cancelled và tắt auto_renew)."""
        return await self.update_subscription(
            subscription_id, {"status": "cancelled", "auto_renew": False}
        )

    async def count_active_subscriptions(self) -> int:
        """Đếm tổng số lượng đăng ký đang hoạt động."""
        query = select(func.count(UserSubscription.id)).where(
            UserSubscription.status == "active"
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def find_expired_subscriptions(self) -> List[UserSubscription]:
        """Tìm các đăng ký đã hết hạn nhưng trạng thái vẫn là active."""
        # Dùng date() để so sánh ngày thay vì datetime chính xác
        today = date.today()
        query = select(UserSubscription).where(
            and_(
                UserSubscription.status == "active",
                UserSubscription.end_date < today,  # So sánh với ngày hôm nay
            )
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def mark_subscription_as_expired(
        self, subscription_id: int
    ) -> UserSubscription:
        """Đánh dấu một đăng ký là hết hạn."""
        return await self.update_subscription(
            subscription_id, {"status": "expired", "auto_renew": False}
        )

    async def renew_subscription(
        self,
        subscription_id: int,
        new_end_date: date,
        new_renewal_date: Optional[date] = None,
    ) -> UserSubscription:
        """Gia hạn đăng ký với ngày kết thúc và ngày gia hạn mới."""
        update_data = {
            "status": "active",
            "start_date": date.today(),  # Có thể giữ start_date cũ?
            "end_date": new_end_date,
            "renewal_date": new_renewal_date,
            "auto_renew": True,  # Mặc định bật lại auto_renew khi gia hạn
        }
        # Xóa renewal_date khỏi dict nếu là None
        if new_renewal_date is None:
            del update_data["renewal_date"]

        return await self.update_subscription(subscription_id, update_data)
