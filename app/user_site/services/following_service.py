from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.following_repo import FollowingRepository
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


class FollowingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.following_repo = FollowingRepository(db)
        self.user_repo = UserRepository(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="followers", tags=["user_followers", "user_following"])
    async def follow_user(self, follower_id: int, following_id: int) -> Dict[str, Any]:
        """Theo dõi người dùng.

        Args:
            follower_id: ID người theo dõi
            following_id: ID người được theo dõi

        Returns:
            Thông tin theo dõi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu đã theo dõi hoặc tự theo dõi bản thân
        """
        # Kiểm tra follower tồn tại
        follower = await self.user_repo.get(follower_id)
        if not follower:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {follower_id}")

        # Kiểm tra following tồn tại
        following = await self.user_repo.get(following_id)
        if not following:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {following_id}")

        # Kiểm tra tự theo dõi bản thân
        if follower_id == following_id:
            raise BadRequestException("Không thể tự theo dõi bản thân")

        # Kiểm tra đã theo dõi
        is_following = await self.following_repo.check_following(
            follower_id, following_id
        )
        if is_following:
            raise BadRequestException(f"Đã theo dõi người dùng với ID {following_id}")

        # Tạo theo dõi
        following_data = {"follower_id": follower_id, "following_id": following_id}

        following_info = await self.following_repo.create(following_data)

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=follower_id,
            activity_type="FOLLOW_USER",
            resource_type="user",
            resource_id=str(following_id),
            metadata={
                "follower_username": follower["username"],
                "following_username": following["username"],
            },
        )

        # Metrics
        self.metrics.track_user_activity("follow_user", "registered")

        # Thông báo cho người được theo dõi (optional)
        try:
            from app.user_site.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)
            await notification_service.create_notification(
                user_id=following_id,
                type="NEW_FOLLOWER",
                title=f"{follower['username']} đã theo dõi bạn",
                message=f"{follower['username']} đã bắt đầu theo dõi bạn",
                link=f"/user/{follower['username']}",
            )
        except ImportError:
            # Notification service not available
            pass

        return {
            "id": following_info["id"],
            "follower": {
                "id": follower["id"],
                "username": follower["username"],
                "avatar": follower.get("avatar"),
            },
            "following": {
                "id": following["id"],
                "username": following["username"],
                "avatar": following.get("avatar"),
            },
            "created_at": following_info["created_at"],
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="followers", tags=["user_followers", "user_following"])
    async def unfollow_user(
        self, follower_id: int, following_id: int
    ) -> Dict[str, Any]:
        """Hủy theo dõi người dùng.

        Args:
            follower_id: ID người theo dõi
            following_id: ID người được theo dõi

        Returns:
            Kết quả hủy theo dõi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu chưa theo dõi
        """
        # Kiểm tra follower tồn tại
        follower = await self.user_repo.get(follower_id)
        if not follower:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {follower_id}")

        # Kiểm tra following tồn tại
        following = await self.user_repo.get(following_id)
        if not following:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {following_id}")

        # Kiểm tra đã theo dõi
        is_following = await self.following_repo.check_following(
            follower_id, following_id
        )
        if not is_following:
            raise BadRequestException(f"Chưa theo dõi người dùng với ID {following_id}")

        # Hủy theo dõi
        result = await self.following_repo.delete_following(follower_id, following_id)

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=follower_id,
            activity_type="UNFOLLOW_USER",
            resource_type="user",
            resource_id=str(following_id),
            metadata={
                "follower_username": follower["username"],
                "following_username": following["username"],
            },
        )

        # Metrics
        self.metrics.track_user_activity("unfollow_user", "registered")

        return {
            "success": result,
            "message": f"Đã hủy theo dõi người dùng {following['username']}",
        }

    @CodeProfiler.profile_time()
    @cached(ttl=300, namespace="followers", tags=["user_followers"])
    async def check_following(
        self, follower_id: int, following_id: int
    ) -> Dict[str, Any]:
        """Kiểm tra trạng thái theo dõi.

        Args:
            follower_id: ID người theo dõi
            following_id: ID người được theo dõi

        Returns:
            Trạng thái theo dõi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra follower tồn tại
        follower = await self.user_repo.get(follower_id)
        if not follower:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {follower_id}")

        # Kiểm tra following tồn tại
        following = await self.user_repo.get(following_id)
        if not following:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {following_id}")

        # Kiểm tra trạng thái theo dõi
        is_following = await self.following_repo.check_following(
            follower_id, following_id
        )

        return {
            "follower_id": follower_id,
            "following_id": following_id,
            "is_following": is_following,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="followers", tags=["user_followers"])
    async def list_followers(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """Lấy danh sách người theo dõi.

        Args:
            user_id: ID người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi lấy

        Returns:
            Danh sách người theo dõi và tổng số lượng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy danh sách follower
        followers = await self.following_repo.get_followers(user_id, skip, limit)

        # Lấy tổng số lượng
        total = await self.following_repo.count_followers(user_id)

        # Bổ sung thông tin chi tiết cho mỗi người dùng
        follower_list = []
        for follower in followers:
            follower_user = await self.user_repo.get(follower["follower_id"])
            if follower_user:
                follower_list.append(
                    {
                        "id": follower["id"],
                        "follower_id": follower["follower_id"],
                        "created_at": follower["created_at"],
                        "user": {
                            "id": follower_user["id"],
                            "username": follower_user["username"],
                            "fullname": follower_user.get("fullname"),
                            "avatar": follower_user.get("avatar"),
                        },
                    }
                )

        return {"items": follower_list, "total": total, "skip": skip, "limit": limit}

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="followers", tags=["user_following"])
    async def list_following(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """Lấy danh sách người được theo dõi.

        Args:
            user_id: ID người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi lấy

        Returns:
            Danh sách người được theo dõi và tổng số lượng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy danh sách following
        following_list = await self.following_repo.get_following(user_id, skip, limit)

        # Lấy tổng số lượng
        total = await self.following_repo.count_following(user_id)

        # Bổ sung thông tin chi tiết cho mỗi người dùng
        following_users = []
        for following in following_list:
            following_user = await self.user_repo.get(following["following_id"])
            if following_user:
                following_users.append(
                    {
                        "id": following["id"],
                        "following_id": following["following_id"],
                        "created_at": following["created_at"],
                        "user": {
                            "id": following_user["id"],
                            "username": following_user["username"],
                            "fullname": following_user.get("fullname"),
                            "avatar": following_user.get("avatar"),
                        },
                    }
                )

        return {"items": following_users, "total": total, "skip": skip, "limit": limit}

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="followers", tags=["user_stats"])
    async def get_following_stats(self, user_id: int) -> Dict[str, Any]:
        """Lấy thống kê theo dõi.

        Args:
            user_id: ID người dùng

        Returns:
            Thống kê theo dõi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy số lượng follower và following
        follower_count = await self.following_repo.count_followers(user_id)
        following_count = await self.following_repo.count_following(user_id)

        return {
            "user_id": user_id,
            "follower_count": follower_count,
            "following_count": following_count,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="followers", tags=["mutual_followers"])
    async def get_mutual_followers(
        self, user_id: int, other_user_id: int, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách người dùng theo dõi chung.

        Args:
            user_id: ID người dùng
            other_user_id: ID người dùng thứ hai
            limit: Số lượng kết quả trả về

        Returns:
            Danh sách người dùng theo dõi chung

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra other_user tồn tại
        other_user = await self.user_repo.get(other_user_id)
        if not other_user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {other_user_id}")

        # Lấy danh sách người dùng chung
        mutual_ids = await self.following_repo.get_mutual_followers(
            user_id, other_user_id, limit
        )

        # Lấy thông tin chi tiết cho mỗi người dùng
        mutual_users = []
        for mutual_id in mutual_ids:
            mutual_user = await self.user_repo.get(mutual_id)
            if mutual_user:
                mutual_users.append(
                    {
                        "id": mutual_user["id"],
                        "username": mutual_user["username"],
                        "fullname": mutual_user.get("fullname"),
                        "avatar": mutual_user.get("avatar"),
                    }
                )

        return mutual_users
