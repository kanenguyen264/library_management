from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.badge_repo import BadgeRepository
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
from app.logs_manager.services.user_activity_log_service import UserActivityLogService
from app.core.config import get_settings

settings = get_settings()


class BadgeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.badge_repo = BadgeRepository(db)
        self.user_repo = UserRepository(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="badges", tags=["user_badges"])
    async def create_badge(
        self, user_id: int, badge_id: int, earned_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cấp huy hiệu cho người dùng.

        Args:
            user_id: ID người dùng
            badge_id: ID huy hiệu
            earned_at: Thời gian đạt được (nếu để trống sẽ dùng thời gian hiện tại)

        Returns:
            Thông tin huy hiệu đã cấp

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc huy hiệu
            BadRequestException: Nếu người dùng đã có huy hiệu này
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra badge tồn tại
        badge = await self.badge_repo.get(badge_id)
        if not badge:
            raise NotFoundException(f"Không tìm thấy huy hiệu với ID {badge_id}")

        # Kiểm tra xem user đã có badge này chưa
        has_badge = await self.check_user_has_badge(user_id, badge_id)
        if has_badge:
            raise BadRequestException(f"Người dùng đã có huy hiệu '{badge['name']}'")

        # Thêm badge cho user
        data = {
            "user_id": user_id,
            "badge_id": badge_id,
            "earned_at": earned_at or datetime.now().isoformat(),
        }

        user_badge = await self.badge_repo.add_user_badge(data)

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="EARN_BADGE",
            resource_type="badge",
            resource_id=str(badge_id),
            metadata={
                "badge_name": badge["name"],
                "badge_description": badge["description"],
            },
        )

        # Metrics
        self.metrics.track_user_activity("earn_badge", "registered")

        return user_badge

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="badges", tags=["badge_details"])
    async def get_badge(self, badge_id: int) -> Dict[str, Any]:
        """Lấy thông tin huy hiệu.

        Args:
            badge_id: ID huy hiệu

        Returns:
            Thông tin huy hiệu

        Raises:
            NotFoundException: Nếu không tìm thấy huy hiệu
        """
        badge = await self.badge_repo.get(badge_id)
        if not badge:
            raise NotFoundException(f"Không tìm thấy huy hiệu với ID {badge_id}")

        # Lấy số người dùng có huy hiệu này
        user_count = await self.badge_repo.count_users_with_badge(badge_id)
        badge["user_count"] = user_count

        return badge

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="badges", tags=["user_badges"])
    async def list_user_badges(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """Lấy danh sách huy hiệu của người dùng.

        Args:
            user_id: ID người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi lấy

        Returns:
            Danh sách huy hiệu và tổng số lượng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy danh sách badge
        badges = await self.badge_repo.get_user_badges(user_id, skip, limit)

        # Lấy tổng số lượng
        total = await self.badge_repo.count_user_badges(user_id)

        return {"items": badges, "total": total, "skip": skip, "limit": limit}

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="badges", tags=["badge_details"])
    async def delete_badge(self, badge_id: int) -> bool:
        """Xóa huy hiệu.

        Args:
            badge_id: ID huy hiệu

        Returns:
            True nếu xóa thành công

        Raises:
            NotFoundException: Nếu không tìm thấy huy hiệu
            ForbiddenException: Nếu huy hiệu đã cấp cho người dùng
        """
        # Kiểm tra badge tồn tại
        badge = await self.badge_repo.get(badge_id)
        if not badge:
            raise NotFoundException(f"Không tìm thấy huy hiệu với ID {badge_id}")

        # Kiểm tra có user nào đang có badge này không
        user_count = await self.badge_repo.count_users_with_badge(badge_id)
        if user_count > 0:
            raise ForbiddenException(
                f"Không thể xóa huy hiệu '{badge['name']}' vì đã cấp cho {user_count} người dùng"
            )

        # Xóa badge
        result = await self.badge_repo.delete(badge_id)

        # Metrics
        self.metrics.track_user_activity("delete_badge", "admin")

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="badges", tags=["user_badges"])
    async def delete_user_badge(self, user_id: int, badge_id: int) -> bool:
        """Xóa huy hiệu của người dùng.

        Args:
            user_id: ID người dùng
            badge_id: ID huy hiệu

        Returns:
            True nếu xóa thành công

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc huy hiệu
            BadRequestException: Nếu người dùng không có huy hiệu này
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra badge tồn tại
        badge = await self.badge_repo.get(badge_id)
        if not badge:
            raise NotFoundException(f"Không tìm thấy huy hiệu với ID {badge_id}")

        # Kiểm tra xem user có badge này không
        has_badge = await self.check_user_has_badge(user_id, badge_id)
        if not has_badge:
            raise BadRequestException(f"Người dùng không có huy hiệu '{badge['name']}'")

        # Xóa badge của user
        result = await self.badge_repo.remove_user_badge(user_id, badge_id)

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="REMOVE_BADGE",
            resource_type="badge",
            resource_id=str(badge_id),
            metadata={"badge_name": badge["name"]},
        )

        # Metrics
        self.metrics.track_user_activity("remove_badge", "admin")

        return result

    @CodeProfiler.profile_time()
    async def check_user_has_badge(self, user_id: int, badge_id: int) -> bool:
        """Kiểm tra người dùng có huy hiệu không.

        Args:
            user_id: ID người dùng
            badge_id: ID huy hiệu

        Returns:
            True nếu người dùng có huy hiệu, False nếu không
        """
        return await self.badge_repo.user_has_badge(user_id, badge_id)

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="badges", tags=["user_badges"])
    async def award_badge(self, user_id: int, badge_id: int) -> Dict[str, Any]:
        """Trao huy hiệu cho người dùng.

        Args:
            user_id: ID người dùng
            badge_id: ID huy hiệu

        Returns:
            Thông tin huy hiệu đã trao

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc huy hiệu
            BadRequestException: Nếu người dùng đã có huy hiệu
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra badge tồn tại
        badge = await self.badge_repo.get(badge_id)
        if not badge:
            raise NotFoundException(f"Không tìm thấy huy hiệu với ID {badge_id}")

        # Kiểm tra xem user đã có badge này chưa
        has_badge = await self.check_user_has_badge(user_id, badge_id)
        if has_badge:
            raise BadRequestException(f"Người dùng đã có huy hiệu '{badge['name']}'")

        # Trao badge
        user_badge = await self.create_badge(user_id, badge_id)

        # Gởi thông báo nếu có (optional)
        try:
            from app.user_site.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)
            await notification_service.create_notification(
                user_id=user_id,
                type="BADGE_EARNED",
                title=f"Đã nhận huy hiệu {badge['name']}",
                message=f"Chúc mừng! Bạn đã nhận được huy hiệu {badge['name']}",
                link=f"/profile/badges",
            )
        except ImportError:
            # Notification service not available
            pass

        return user_badge
