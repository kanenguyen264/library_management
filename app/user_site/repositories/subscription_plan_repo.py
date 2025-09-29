"""
Repository cho việc quản lý Subscription Plans.
"""

from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc, asc
from datetime import datetime

from app.core.exceptions import NotFoundException, ServerException
from app.logging.setup import get_logger
from app.user_site.models.subscription import SubscriptionPlan


logger = get_logger(__name__)


class SubscriptionPlanRepository:
    """
    Repository class cho SubscriptionPlan.
    Cung cấp các phương thức để tương tác với cơ sở dữ liệu cho model SubscriptionPlan.
    """

    @staticmethod
    async def get_by_id(db: Session, plan_id: int) -> Optional[SubscriptionPlan]:
        """
        Lấy subscription plan theo ID.

        Args:
            db: Database session
            plan_id: ID của subscription plan

        Returns:
            SubscriptionPlan object hoặc None nếu không tìm thấy
        """
        try:
            return (
                db.query(SubscriptionPlan)
                .filter(SubscriptionPlan.id == plan_id)
                .first()
            )
        except Exception as e:
            logger.error(f"Lỗi khi lấy subscription plan theo ID {plan_id}: {str(e)}")
            raise ServerException(
                detail=f"Không thể truy vấn subscription plan: {str(e)}"
            )

    @staticmethod
    async def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> List[SubscriptionPlan]:
        """
        Lấy danh sách subscription plans với phân trang và lọc.

        Args:
            db: Database session
            skip: Số lượng records để bỏ qua
            limit: Số lượng records tối đa trả về
            search: Từ khóa tìm kiếm
            is_active: Lọc theo trạng thái kích hoạt
            sort_by: Sắp xếp theo trường
            sort_desc: Sắp xếp giảm dần (True) hoặc tăng dần (False)

        Returns:
            Danh sách subscription plans
        """
        try:
            query = db.query(SubscriptionPlan)

            # Áp dụng bộ lọc
            if search:
                query = query.filter(
                    or_(
                        SubscriptionPlan.name.ilike(f"%{search}%"),
                        SubscriptionPlan.description.ilike(f"%{search}%"),
                    )
                )

            if is_active is not None:
                query = query.filter(SubscriptionPlan.is_active == is_active)

            # Sắp xếp
            sort_attr = getattr(SubscriptionPlan, sort_by, SubscriptionPlan.created_at)
            if sort_desc:
                query = query.order_by(desc(sort_attr))
            else:
                query = query.order_by(asc(sort_attr))

            # Phân trang
            query = query.offset(skip).limit(limit)

            return query.all()
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách subscription plans: {str(e)}")
            raise ServerException(
                detail=f"Không thể truy vấn danh sách subscription plans: {str(e)}"
            )

    @staticmethod
    async def create(db: Session, data: Dict[str, Any]) -> SubscriptionPlan:
        """
        Tạo subscription plan mới.

        Args:
            db: Database session
            data: Dictionary chứa dữ liệu của subscription plan mới

        Returns:
            SubscriptionPlan object đã tạo
        """
        try:
            subscription_plan = SubscriptionPlan(**data)
            db.add(subscription_plan)
            db.commit()
            db.refresh(subscription_plan)
            return subscription_plan
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo subscription plan: {str(e)}")
            raise ServerException(detail=f"Không thể tạo subscription plan: {str(e)}")

    @staticmethod
    async def update(
        db: Session, plan_id: int, data: Dict[str, Any]
    ) -> SubscriptionPlan:
        """
        Cập nhật subscription plan.

        Args:
            db: Database session
            plan_id: ID của subscription plan
            data: Dictionary chứa dữ liệu cần cập nhật

        Returns:
            SubscriptionPlan object đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy subscription plan
        """
        try:
            subscription_plan = await SubscriptionPlanRepository.get_by_id(db, plan_id)
            if not subscription_plan:
                raise NotFoundException(
                    detail=f"Không tìm thấy subscription plan với ID {plan_id}"
                )

            # Cập nhật các trường
            for key, value in data.items():
                if hasattr(subscription_plan, key):
                    setattr(subscription_plan, key, value)

            db.commit()
            db.refresh(subscription_plan)
            return subscription_plan
        except NotFoundException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật subscription plan ID {plan_id}: {str(e)}")
            raise ServerException(
                detail=f"Không thể cập nhật subscription plan: {str(e)}"
            )

    @staticmethod
    async def delete(db: Session, plan_id: int) -> bool:
        """
        Xóa subscription plan.

        Args:
            db: Database session
            plan_id: ID của subscription plan

        Returns:
            True nếu xóa thành công

        Raises:
            NotFoundException: Nếu không tìm thấy subscription plan
        """
        try:
            subscription_plan = await SubscriptionPlanRepository.get_by_id(db, plan_id)
            if not subscription_plan:
                raise NotFoundException(
                    detail=f"Không tìm thấy subscription plan với ID {plan_id}"
                )

            db.delete(subscription_plan)
            db.commit()
            return True
        except NotFoundException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa subscription plan ID {plan_id}: {str(e)}")
            raise ServerException(detail=f"Không thể xóa subscription plan: {str(e)}")

    @staticmethod
    async def count(
        db: Session, search: Optional[str] = None, is_active: Optional[bool] = None
    ) -> int:
        """
        Đếm số lượng subscription plans theo bộ lọc.

        Args:
            db: Database session
            search: Từ khóa tìm kiếm
            is_active: Lọc theo trạng thái kích hoạt

        Returns:
            Số lượng subscription plans
        """
        try:
            query = db.query(func.count(SubscriptionPlan.id))

            # Áp dụng bộ lọc
            if search:
                query = query.filter(
                    or_(
                        SubscriptionPlan.name.ilike(f"%{search}%"),
                        SubscriptionPlan.description.ilike(f"%{search}%"),
                    )
                )

            if is_active is not None:
                query = query.filter(SubscriptionPlan.is_active == is_active)

            return query.scalar()
        except Exception as e:
            logger.error(f"Lỗi khi đếm subscription plans: {str(e)}")
            raise ServerException(detail=f"Không thể đếm subscription plans: {str(e)}")
