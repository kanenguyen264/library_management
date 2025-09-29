from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.achievement_repo import AchievementRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.cache.decorators import cached, invalidate_cache
from app.cache import get_cache
from app.cache.keys import CacheKeyBuilder
from app.security.access_control.abac import check_policy, OwnershipPolicy
from app.monitoring.metrics import Metrics
from app.performance.profiling.code_profiler import CodeProfiler


class AchievementService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.achievement_repo = AchievementRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    @invalidate_cache(namespace="achievements", tags=["user_achievements"])
    async def create_achievement(
        self, user_id: int, achievement_id: int, earned_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Tạo thành tựu mới cho người dùng.

        Args:
            user_id: ID của người dùng
            achievement_id: ID của thành tựu
            earned_at: Thời điểm đạt được thành tựu (tùy chọn)

        Returns:
            Thông tin thành tựu đã tạo
        """
        # Track metrics for achievement creation
        with self.metrics.time_request("POST", "/achievements"):
            # Kiểm tra xem người dùng đã có thành tựu này chưa
            existing = await self.achievement_repo.get_by_user_and_achievement(
                user_id, achievement_id
            )
            if existing:
                raise BadRequestException(detail="Người dùng đã có thành tựu này")

            achievement_data = {"user_id": user_id, "achievement_id": achievement_id}

            if earned_at:
                achievement_data["earned_at"] = earned_at

            # Tạo thành tựu
            created = await self.achievement_repo.create(achievement_data)

            # Log the achievement earning
            try:
                await create_user_activity_log(
                    self.db,
                    UserActivityLogCreate(
                        user_id=user_id,
                        activity_type="EARN",
                        entity_type="ACHIEVEMENT",
                        entity_id=achievement_id,
                        description=f"Earned achievement ID: {achievement_id}",
                        metadata={
                            "achievement_id": achievement_id,
                            "earned_at": (
                                str(created.earned_at) if created.earned_at else None
                            ),
                        },
                    ),
                )

                # Track user achievement as a business metric
                self.metrics.track_user_activity("earn_achievement")

            except Exception:
                # Log but don't fail if logging fails
                pass

            # Invalidate related caches
            cache_key = f"user_achievements:{user_id}"
            await self.cache.delete(cache_key)

            return {
                "id": created.id,
                "user_id": created.user_id,
                "achievement_id": created.achievement_id,
                "earned_at": created.earned_at,
                "created_at": created.created_at,
            }

    @cached(ttl=3600, namespace="achievements", tags=["achievement_details"])
    async def get_achievement(self, achievement_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin thành tựu theo ID.

        Args:
            achievement_id: ID của thành tựu

        Returns:
            Thông tin thành tựu

        Raises:
            NotFoundException: Nếu không tìm thấy thành tựu
        """
        with self.profiler.profile_time(name="get_achievement", threshold=0.5):
            achievement = await self.achievement_repo.get_by_id(
                achievement_id, with_relations=True
            )
            if not achievement:
                raise NotFoundException(
                    detail=f"Không tìm thấy thành tựu với ID {achievement_id}"
                )

            return {
                "id": achievement.id,
                "user_id": achievement.user_id,
                "achievement_id": achievement.achievement_id,
                "earned_at": achievement.earned_at,
                "created_at": achievement.created_at,
                "user": (
                    {
                        "id": achievement.user.id,
                        "username": achievement.user.username,
                        "display_name": achievement.user.display_name,
                    }
                    if achievement.user
                    else None
                ),
            }

    @cached(
        ttl=1800,
        namespace="achievements",
        key_builder=lambda *args, **kwargs: f"user_achievements:{kwargs.get('user_id')}:{kwargs.get('skip')}:{kwargs.get('limit')}",
    )
    async def list_user_achievements(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách thành tựu của người dùng.

        Args:
            user_id: ID của người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách thành tựu và thông tin phân trang
        """
        with self.metrics.time_request("GET", f"/users/{user_id}/achievements"):
            achievements = await self.achievement_repo.list_by_user(
                user_id, skip, limit
            )
            total = await self.achievement_repo.count_by_user(user_id)

            return {
                "items": [
                    {
                        "id": achievement.id,
                        "user_id": achievement.user_id,
                        "achievement_id": achievement.achievement_id,
                        "earned_at": achievement.earned_at,
                        "created_at": achievement.created_at,
                    }
                    for achievement in achievements
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }

    @invalidate_cache(
        namespace="achievements", tags=["achievement_details", "user_achievements"]
    )
    async def delete_achievement(
        self, achievement_id: int, current_user_id: Optional[int] = None
    ) -> bool:
        """
        Xóa thành tựu.

        Args:
            achievement_id: ID của thành tựu
            current_user_id: ID của người dùng hiện tại (để kiểm tra quyền)

        Returns:
            True nếu xóa thành công

        Raises:
            NotFoundException: Nếu không tìm thấy thành tựu
            ForbiddenException: Nếu người dùng không có quyền xóa
        """
        # Get achievement info for logging
        achievement = await self.achievement_repo.get_by_id(achievement_id)
        if not achievement:
            raise NotFoundException(
                detail=f"Không tìm thấy thành tựu với ID {achievement_id}"
            )

        # Kiểm tra quyền nếu current_user_id được cung cấp
        if current_user_id is not None and achievement.user_id != current_user_id:
            # Kiểm tra xem current_user có phải admin không
            # Giả sử có một hàm kiểm tra người dùng có phải admin không
            is_admin = False  # Implement admin check logic here

            if not is_admin:
                raise ForbiddenException(detail="Bạn không có quyền xóa thành tựu này")

        result = await self.achievement_repo.delete(achievement_id)

        # Log the achievement removal if successful
        if result:
            try:
                await create_user_activity_log(
                    self.db,
                    UserActivityLogCreate(
                        user_id=achievement.user_id,
                        activity_type="LOSE",
                        entity_type="ACHIEVEMENT",
                        entity_id=achievement.achievement_id,
                        description=f"Lost achievement ID: {achievement.achievement_id}",
                        metadata={"achievement_id": achievement.achievement_id},
                    ),
                )

                # Track as a business metric
                self.metrics.track_user_activity("delete_achievement")

                # Invalidate user achievements cache
                cache_key = f"user_achievements:{achievement.user_id}"
                await self.cache.delete(cache_key)

            except Exception:
                # Log but don't fail if logging fails
                pass

        return result

    @invalidate_cache(namespace="achievements", tags=["user_achievements"])
    async def delete_user_achievement(self, user_id: int, achievement_id: int) -> bool:
        """
        Xóa thành tựu của người dùng.

        Args:
            user_id: ID của người dùng
            achievement_id: ID của thành tựu

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy
        """
        # Get achievement info for logging
        achievement = await self.achievement_repo.get_by_user_and_achievement(
            user_id, achievement_id
        )
        if not achievement:
            return False

        result = await self.achievement_repo.delete_by_user_and_achievement(
            user_id, achievement_id
        )

        # Log the achievement removal if successful
        if result:
            try:
                await create_user_activity_log(
                    self.db,
                    UserActivityLogCreate(
                        user_id=user_id,
                        activity_type="LOSE",
                        entity_type="ACHIEVEMENT",
                        entity_id=achievement_id,
                        description=f"Lost achievement ID: {achievement_id}",
                        metadata={"achievement_id": achievement_id},
                    ),
                )

                # Track as a business metric
                self.metrics.track_user_activity("delete_achievement")

            except Exception:
                # Log but don't fail if logging fails
                pass

        # Invalidate related caches
        cache_key = f"user_achievements:{user_id}"
        await self.cache.delete(cache_key)

        return result

    @cached(ttl=300, namespace="achievements")
    async def check_user_has_achievement(
        self, user_id: int, achievement_id: int
    ) -> bool:
        """
        Kiểm tra xem người dùng đã có thành tựu này chưa.

        Args:
            user_id: ID của người dùng
            achievement_id: ID của thành tựu

        Returns:
            True nếu người dùng đã có thành tựu, ngược lại False
        """
        achievement = await self.achievement_repo.get_by_user_and_achievement(
            user_id, achievement_id
        )
        return achievement is not None

    async def award_achievement_batch(
        self, user_achievements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Tạo nhiều thành tựu cùng lúc cho một hoặc nhiều người dùng.

        Args:
            user_achievements: Danh sách dict chứa {user_id, achievement_id, earned_at}

        Returns:
            Danh sách thành tựu đã tạo
        """
        results = []

        for data in user_achievements:
            user_id = data.get("user_id")
            achievement_id = data.get("achievement_id")
            earned_at = data.get("earned_at")

            if not user_id or not achievement_id:
                continue

            # Kiểm tra người dùng đã có thành tựu chưa
            existing = await self.achievement_repo.get_by_user_and_achievement(
                user_id, achievement_id
            )
            if existing:
                continue

            # Tạo thành tựu
            achievement_data = {"user_id": user_id, "achievement_id": achievement_id}

            if earned_at:
                achievement_data["earned_at"] = earned_at

            created = await self.achievement_repo.create(achievement_data)

            # Ghi log và track metric
            try:
                await create_user_activity_log(
                    self.db,
                    UserActivityLogCreate(
                        user_id=user_id,
                        activity_type="EARN",
                        entity_type="ACHIEVEMENT",
                        entity_id=achievement_id,
                        description=f"Earned achievement ID: {achievement_id}",
                        metadata={
                            "achievement_id": achievement_id,
                            "earned_at": (
                                str(created.earned_at) if created.earned_at else None
                            ),
                        },
                    ),
                )

                self.metrics.track_user_activity("earn_achievement")

                # Invalidate user achievements cache
                cache_key = f"user_achievements:{user_id}"
                await self.cache.delete(cache_key)

            except Exception:
                pass

            results.append(
                {
                    "id": created.id,
                    "user_id": created.user_id,
                    "achievement_id": created.achievement_id,
                    "earned_at": created.earned_at,
                    "created_at": created.created_at,
                }
            )

        return results
