from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.social_profile_repo import SocialProfileRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.following_repo import FollowingRepository
from app.user_site.repositories.review_repo import ReviewRepository
from app.user_site.repositories.reading_history_repo import ReadingHistoryRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    ValidationException,
    ConflictException,
)
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.cache.decorators import cached
from app.security.input_validation.sanitizers import sanitize_text
from app.logging.setup import get_logger
from app.monitoring.metrics.business_metrics import business_metrics

logger = get_logger(__name__)


class SocialProfileService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.social_profile_repo = SocialProfileRepository(db)
        self.user_repo = UserRepository(db)
        self.following_repo = FollowingRepository(db)
        self.review_repo = ReviewRepository(db)
        self.reading_history_repo = ReadingHistoryRepository(db)

    @cached(
        ttl=1800, namespace="profiles", key_prefix="user", tags=["profiles", "users"]
    )
    async def get_profile(self, user_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin hồ sơ xã hội của người dùng

        Args:
            user_id: ID người dùng

        Returns:
            Thông tin hồ sơ người dùng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id, with_relations=["preferences"])
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy hồ sơ xã hội
        social_profile = await self.social_profile_repo.get_by_user_id(user_id)

        # Nếu chưa có hồ sơ xã hội, tạo mới
        if not social_profile:
            social_profile = await self.social_profile_repo.create(
                {
                    "user_id": user_id,
                    "bio": "",
                    "website": "",
                    "facebook_url": "",
                    "twitter_url": "",
                    "instagram_url": "",
                    "is_private": False,
                    "show_reading_activity": True,
                    "show_reviews": True,
                    "show_following": True,
                }
            )

        # Lấy các thông tin phụ
        followers_count = await self.following_repo.count_followers(user_id)
        following_count = await self.following_repo.count_following(user_id)
        reviews_count = await self.review_repo.count_reviews(user_id=user_id)
        reading_stats = await self.reading_history_repo.get_user_reading_stats(user_id)

        # Format kết quả
        result = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "bio": social_profile.bio,
            "website": social_profile.website,
            "social_links": {
                "facebook": social_profile.facebook_url,
                "twitter": social_profile.twitter_url,
                "instagram": social_profile.instagram_url,
            },
            "privacy_settings": {
                "is_private": social_profile.is_private,
                "show_reading_activity": social_profile.show_reading_activity,
                "show_reviews": social_profile.show_reviews,
                "show_following": social_profile.show_following,
            },
            "stats": {
                "followers_count": followers_count,
                "following_count": following_count,
                "reviews_count": reviews_count,
                "books_read": reading_stats.get("books_read", 0),
                "pages_read": reading_stats.get("pages_read", 0),
                "reading_time": reading_stats.get("reading_time", 0),
                "currently_reading": reading_stats.get("currently_reading", 0),
            },
            "created_at": user.created_at,
            "last_active": user.last_active,
        }

        # Thêm thông tin sở thích nếu có
        if hasattr(user, "preferences") and user.preferences:
            result["preferences"] = {
                "favorite_genres": (
                    user.preferences.favorite_genres
                    if hasattr(user.preferences, "favorite_genres")
                    else []
                ),
                "favorite_authors": (
                    user.preferences.favorite_authors
                    if hasattr(user.preferences, "favorite_authors")
                    else []
                ),
                "reading_goal": (
                    user.preferences.reading_goal
                    if hasattr(user.preferences, "reading_goal")
                    else None
                ),
            }

        return result

    async def update_profile(
        self, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin hồ sơ xã hội

        Args:
            user_id: ID người dùng
            data: Dữ liệu cập nhật

        Returns:
            Thông tin hồ sơ đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            ValidationException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy hồ sơ xã hội hiện tại
        social_profile = await self.social_profile_repo.get_by_user_id(user_id)
        if not social_profile:
            # Nếu chưa có, tạo mới
            social_profile = await self.social_profile_repo.create(
                {
                    "user_id": user_id,
                    "bio": "",
                    "website": "",
                    "facebook_url": "",
                    "twitter_url": "",
                    "instagram_url": "",
                    "is_private": False,
                    "show_reading_activity": True,
                    "show_reviews": True,
                    "show_following": True,
                }
            )

        # Chuẩn bị dữ liệu cập nhật
        user_update = {}
        profile_update = {}

        # Xử lý dữ liệu người dùng
        if "display_name" in data:
            user_update["display_name"] = sanitize_text(data["display_name"])

        if "full_name" in data:
            user_update["full_name"] = sanitize_text(data["full_name"])

        if "avatar_url" in data:
            user_update["avatar_url"] = data["avatar_url"]

        # Xử lý dữ liệu hồ sơ xã hội
        if "bio" in data:
            bio = sanitize_text(data["bio"])
            if len(bio) > 500:
                raise ValidationException("Tiểu sử không được quá 500 ký tự")
            profile_update["bio"] = bio

        if "website" in data:
            website = data["website"]
            # Kiểm tra URL hợp lệ
            if website and not (
                website.startswith("http://") or website.startswith("https://")
            ):
                website = "https://" + website
            profile_update["website"] = website

        if "social_links" in data and isinstance(data["social_links"], dict):
            social_links = data["social_links"]

            if "facebook" in social_links:
                profile_update["facebook_url"] = social_links["facebook"]

            if "twitter" in social_links:
                profile_update["twitter_url"] = social_links["twitter"]

            if "instagram" in social_links:
                profile_update["instagram_url"] = social_links["instagram"]

        # Cập nhật dữ liệu
        if user_update:
            await self.user_repo.update(user_id, user_update)

        if profile_update:
            await self.social_profile_repo.update(social_profile.id, profile_update)

        # Vô hiệu hóa cache
        await self._invalidate_profile_cache(user_id)

        # Trả về hồ sơ đã cập nhật
        return await self.get_profile(user_id)

    @cached(
        ttl=3600, namespace="profiles", key_prefix="public", tags=["profiles", "users"]
    )
    async def get_public_profile(
        self, username: str, current_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin hồ sơ công khai của người dùng

        Args:
            username: Tên người dùng
            current_user_id: ID người dùng hiện tại (tùy chọn)

        Returns:
            Thông tin hồ sơ công khai

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            ForbiddenException: Nếu người dùng không cho phép xem hồ sơ
        """
        # Tìm người dùng theo username
        user = await self.user_repo.get_by_username(username)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với tên {username}")

        user_id = user.id

        # Lấy hồ sơ xã hội
        social_profile = await self.social_profile_repo.get_by_user_id(user_id)
        if not social_profile:
            # Nếu chưa có, tạo mới với cài đặt mặc định
            social_profile = await self.social_profile_repo.create(
                {
                    "user_id": user_id,
                    "bio": "",
                    "website": "",
                    "facebook_url": "",
                    "twitter_url": "",
                    "instagram_url": "",
                    "is_private": False,
                    "show_reading_activity": True,
                    "show_reviews": True,
                    "show_following": True,
                }
            )

        # Kiểm tra quyền xem hồ sơ
        if social_profile.is_private and current_user_id != user_id:
            # Kiểm tra xem người dùng hiện tại có đang theo dõi không
            if current_user_id:
                is_following = await self.following_repo.check_following(
                    follower_id=current_user_id, following_id=user_id
                )

                if not is_following:
                    raise ForbiddenException("Hồ sơ này đã được đặt riêng tư")
            else:
                raise ForbiddenException("Hồ sơ này đã được đặt riêng tư")

        # Lấy các thông tin phụ
        followers_count = await self.following_repo.count_followers(user_id)
        following_count = await self.following_repo.count_following(user_id)

        # Hiển thị số lượng người theo dõi/đang theo dõi tùy theo cài đặt riêng tư
        if not social_profile.show_following and current_user_id != user_id:
            followers_count = 0
            following_count = 0

        # Lấy thông tin đánh giá nếu cho phép hiển thị
        reviews_count = 0
        if social_profile.show_reviews or current_user_id == user_id:
            reviews_count = await self.review_repo.count_reviews(user_id=user_id)

        # Lấy thông tin đọc sách nếu cho phép hiển thị
        reading_stats = {}
        if social_profile.show_reading_activity or current_user_id == user_id:
            reading_stats = await self.reading_history_repo.get_user_reading_stats(
                user_id
            )

        # Kiểm tra xem người dùng hiện tại có đang theo dõi không
        is_following = False
        if current_user_id and current_user_id != user_id:
            is_following = await self.following_repo.check_following(
                follower_id=current_user_id, following_id=user_id
            )

        # Format kết quả
        result = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "bio": social_profile.bio,
            "website": social_profile.website,
            "social_links": {
                "facebook": social_profile.facebook_url,
                "twitter": social_profile.twitter_url,
                "instagram": social_profile.instagram_url,
            },
            "stats": {
                "followers_count": followers_count,
                "following_count": following_count,
                "reviews_count": reviews_count,
            },
            "privacy": {
                "is_private": social_profile.is_private,
                "show_reading_activity": social_profile.show_reading_activity,
                "show_reviews": social_profile.show_reviews,
                "show_following": social_profile.show_following,
            },
            "is_following": is_following,
            "is_current_user": current_user_id == user_id,
            "created_at": user.created_at,
        }

        # Thêm thông tin đọc sách nếu có
        if reading_stats and (
            social_profile.show_reading_activity or current_user_id == user_id
        ):
            result["stats"]["books_read"] = reading_stats.get("books_read", 0)
            result["stats"]["pages_read"] = reading_stats.get("pages_read", 0)
            result["stats"]["reading_time"] = reading_stats.get("reading_time", 0)
            result["stats"]["currently_reading"] = reading_stats.get(
                "currently_reading", 0
            )

        return result

    async def update_privacy_settings(
        self,
        user_id: int,
        is_private: bool,
        show_reading_activity: bool,
        show_reviews: bool,
        show_following: bool,
    ) -> Dict[str, Any]:
        """
        Cập nhật cài đặt quyền riêng tư

        Args:
            user_id: ID người dùng
            is_private: Hồ sơ riêng tư chỉ người theo dõi mới xem được
            show_reading_activity: Hiển thị hoạt động đọc sách
            show_reviews: Hiển thị đánh giá
            show_following: Hiển thị người theo dõi/đang theo dõi

        Returns:
            Cài đặt quyền riêng tư đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy hồ sơ xã hội hiện tại
        social_profile = await self.social_profile_repo.get_by_user_id(user_id)
        if not social_profile:
            # Nếu chưa có, tạo mới
            social_profile = await self.social_profile_repo.create(
                {
                    "user_id": user_id,
                    "bio": "",
                    "website": "",
                    "facebook_url": "",
                    "twitter_url": "",
                    "instagram_url": "",
                    "is_private": is_private,
                    "show_reading_activity": show_reading_activity,
                    "show_reviews": show_reviews,
                    "show_following": show_following,
                }
            )
        else:
            # Cập nhật cài đặt
            await self.social_profile_repo.update(
                social_profile.id,
                {
                    "is_private": is_private,
                    "show_reading_activity": show_reading_activity,
                    "show_reviews": show_reviews,
                    "show_following": show_following,
                },
            )

        # Vô hiệu hóa cache
        await self._invalidate_profile_cache(user_id)

        # Trả về cài đặt đã cập nhật
        return {
            "user_id": user_id,
            "privacy_settings": {
                "is_private": is_private,
                "show_reading_activity": show_reading_activity,
                "show_reviews": show_reviews,
                "show_following": show_following,
            },
            "updated_at": social_profile.updated_at,
        }

    @cached(ttl=3600, namespace="profiles", key_prefix="popular", tags=["profiles"])
    async def list_popular_profiles(
        self, current_user_id: Optional[int] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách hồ sơ người dùng phổ biến

        Args:
            current_user_id: ID người dùng hiện tại (tùy chọn)
            limit: Số lượng hồ sơ tối đa

        Returns:
            Danh sách hồ sơ người dùng phổ biến
        """
        # Lấy người dùng có nhiều người theo dõi nhất
        popular_users = await self.following_repo.find_users_with_most_followers(
            limit=limit * 2
        )

        # Format kết quả và lọc người dùng riêng tư
        result = []
        for user in popular_users:
            # Lấy hồ sơ xã hội
            social_profile = await self.social_profile_repo.get_by_user_id(user.id)

            # Bỏ qua người dùng riêng tư (trừ khi người dùng hiện tại đang theo dõi)
            if (
                social_profile
                and social_profile.is_private
                and current_user_id != user.id
            ):
                # Kiểm tra xem người dùng hiện tại có đang theo dõi không
                if current_user_id:
                    is_following = await self.following_repo.check_following(
                        follower_id=current_user_id, following_id=user.id
                    )

                    if not is_following:
                        continue
                else:
                    continue

            # Lấy số lượng người theo dõi
            followers_count = await self.following_repo.count_followers(user.id)

            # Kiểm tra xem người dùng hiện tại có đang theo dõi không
            is_following = False
            if current_user_id and current_user_id != user.id:
                is_following = await self.following_repo.check_following(
                    follower_id=current_user_id, following_id=user.id
                )

            # Thêm vào kết quả
            result.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar_url": user.avatar_url,
                    "followers_count": followers_count,
                    "is_following": is_following,
                    "is_current_user": current_user_id == user.id,
                }
            )

            # Giới hạn số lượng
            if len(result) >= limit:
                break

        return result

    async def check_can_view_profile(
        self, viewer_id: Optional[int], profile_user_id: int
    ) -> Dict[str, Any]:
        """
        Kiểm tra người dùng có thể xem hồ sơ không

        Args:
            viewer_id: ID người xem (tùy chọn)
            profile_user_id: ID người dùng có hồ sơ

        Returns:
            Kết quả kiểm tra
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(profile_user_id)
        if not user:
            return {"can_view": False, "reason": "Không tìm thấy người dùng"}

        # Nếu đang xem hồ sơ của chính mình
        if viewer_id == profile_user_id:
            return {"can_view": True, "is_owner": True}

        # Lấy hồ sơ xã hội
        social_profile = await self.social_profile_repo.get_by_user_id(profile_user_id)
        if not social_profile:
            # Nếu chưa có hồ sơ xã hội, mặc định là công khai
            return {"can_view": True, "is_owner": False}

        # Kiểm tra hồ sơ riêng tư
        if social_profile.is_private:
            # Kiểm tra xem có đang theo dõi không
            if viewer_id:
                is_following = await self.following_repo.check_following(
                    follower_id=viewer_id, following_id=profile_user_id
                )

                if is_following:
                    return {"can_view": True, "is_owner": False, "is_following": True}
                else:
                    return {
                        "can_view": False,
                        "reason": "Hồ sơ này đã được đặt riêng tư",
                        "is_following": False,
                    }
            else:
                return {"can_view": False, "reason": "Hồ sơ này đã được đặt riêng tư"}

        # Hồ sơ công khai
        return {
            "can_view": True,
            "is_owner": False,
            "is_following": viewer_id
            and await self.following_repo.check_following(
                follower_id=viewer_id, following_id=profile_user_id
            ),
        }

    async def check_can_view_activity(
        self, viewer_id: Optional[int], profile_user_id: int, activity_type: str
    ) -> Dict[str, Any]:
        """
        Kiểm tra người dùng có thể xem hoạt động cụ thể không

        Args:
            viewer_id: ID người xem (tùy chọn)
            profile_user_id: ID người dùng có hồ sơ
            activity_type: Loại hoạt động (reading, reviews, following)

        Returns:
            Kết quả kiểm tra
        """
        # Trước tiên kiểm tra quyền xem hồ sơ
        profile_access = await self.check_can_view_profile(viewer_id, profile_user_id)
        if not profile_access["can_view"]:
            return profile_access

        # Nếu đang xem hồ sơ của chính mình
        if viewer_id == profile_user_id:
            return {"can_view": True, "is_owner": True, "activity_type": activity_type}

        # Lấy hồ sơ xã hội
        social_profile = await self.social_profile_repo.get_by_user_id(profile_user_id)
        if not social_profile:
            # Nếu chưa có hồ sơ xã hội, mặc định là công khai
            return {"can_view": True, "is_owner": False, "activity_type": activity_type}

        # Kiểm tra cài đặt hiển thị hoạt động
        if activity_type == "reading" and not social_profile.show_reading_activity:
            return {
                "can_view": False,
                "reason": "Người dùng này không chia sẻ hoạt động đọc sách",
                "activity_type": activity_type,
            }

        if activity_type == "reviews" and not social_profile.show_reviews:
            return {
                "can_view": False,
                "reason": "Người dùng này không chia sẻ đánh giá sách",
                "activity_type": activity_type,
            }

        if activity_type == "following" and not social_profile.show_following:
            return {
                "can_view": False,
                "reason": "Người dùng này không chia sẻ thông tin người theo dõi",
                "activity_type": activity_type,
            }

        # Có thể xem hoạt động
        return {
            "can_view": True,
            "is_owner": False,
            "is_following": viewer_id
            and await self.following_repo.check_following(
                follower_id=viewer_id, following_id=profile_user_id
            ),
            "activity_type": activity_type,
        }

    async def follow_user(self, follower_id: int, following_id: int) -> Dict[str, Any]:
        """
        Theo dõi một người dùng

        Args:
            follower_id: ID người theo dõi
            following_id: ID người được theo dõi

        Returns:
            Thông tin kết quả theo dõi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            ValidationException: Nếu người dùng tự theo dõi chính mình
        """
        # Kiểm tra người dùng tồn tại
        follower = await self.user_repo.get_by_id(follower_id)
        if not follower:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {follower_id}")

        following = await self.user_repo.get_by_id(following_id)
        if not following:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {following_id}")

        # Kiểm tra không tự theo dõi chính mình
        if follower_id == following_id:
            raise ValidationException("Bạn không thể tự theo dõi chính mình")

        # Kiểm tra đã theo dõi chưa
        is_following = await self.following_repo.check_following(
            follower_id=follower_id, following_id=following_id
        )

        if is_following:
            return {
                "success": True,
                "message": f"Bạn đã theo dõi {following.username}",
                "following_id": following_id,
                "already_following": True,
            }

        # Tạo theo dõi mới
        following_data = {"follower_id": follower_id, "following_id": following_id}

        await self.following_repo.create(following_data)

        # Theo dõi số liệu
        business_metrics.track_social_action("follow", "user")

        # Vô hiệu hóa cache liên quan
        await self._invalidate_profile_cache(follower_id)
        await self._invalidate_profile_cache(following_id)

        return {
            "success": True,
            "message": f"Đã theo dõi {following.username}",
            "following_id": following_id,
            "already_following": False,
        }

    async def unfollow_user(
        self, follower_id: int, following_id: int
    ) -> Dict[str, Any]:
        """
        Hủy theo dõi một người dùng

        Args:
            follower_id: ID người theo dõi
            following_id: ID người được theo dõi

        Returns:
            Thông tin kết quả hủy theo dõi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            ValidationException: Nếu người dùng tự hủy theo dõi chính mình
        """
        # Kiểm tra người dùng tồn tại
        follower = await self.user_repo.get_by_id(follower_id)
        if not follower:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {follower_id}")

        following = await self.user_repo.get_by_id(following_id)
        if not following:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {following_id}")

        # Kiểm tra không tự hủy theo dõi chính mình
        if follower_id == following_id:
            raise ValidationException("Bạn không thể tự hủy theo dõi chính mình")

        # Kiểm tra đang theo dõi
        following_entry = await self.following_repo.get_by_follower_and_following(
            follower_id=follower_id, following_id=following_id
        )

        if not following_entry:
            return {
                "success": True,
                "message": f"Bạn chưa theo dõi {following.username}",
                "following_id": following_id,
                "was_following": False,
            }

        # Xóa theo dõi
        await self.following_repo.delete(following_entry.id)

        # Vô hiệu hóa cache liên quan
        await self._invalidate_profile_cache(follower_id)
        await self._invalidate_profile_cache(following_id)

        return {
            "success": True,
            "message": f"Đã hủy theo dõi {following.username}",
            "following_id": following_id,
            "was_following": True,
        }

    async def get_followers(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách người theo dõi

        Args:
            user_id: ID người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa

        Returns:
            Danh sách người theo dõi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy danh sách người theo dõi
        followers = await self.following_repo.get_followers(
            user_id=user_id, skip=skip, limit=limit
        )

        # Đếm tổng số người theo dõi
        total_count = await self.following_repo.count_followers(user_id)

        # Format kết quả
        formatted_followers = []
        for follower in followers:
            formatted_followers.append(
                {
                    "id": follower.id,
                    "username": follower.username,
                    "display_name": follower.display_name,
                    "avatar_url": follower.avatar_url,
                    "followed_at": getattr(follower, "followed_at", None),
                }
            )

        return {
            "items": formatted_followers,
            "total": total_count,
            "page": skip // limit + 1,
            "size": limit,
        }

    async def get_following(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách người đang theo dõi

        Args:
            user_id: ID người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa

        Returns:
            Danh sách người đang theo dõi

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy danh sách người đang theo dõi
        following = await self.following_repo.get_following(
            user_id=user_id, skip=skip, limit=limit
        )

        # Đếm tổng số người đang theo dõi
        total_count = await self.following_repo.count_following(user_id)

        # Format kết quả
        formatted_following = []
        for followed in following:
            formatted_following.append(
                {
                    "id": followed.id,
                    "username": followed.username,
                    "display_name": followed.display_name,
                    "avatar_url": followed.avatar_url,
                    "following_since": getattr(followed, "following_since", None),
                }
            )

        return {
            "items": formatted_following,
            "total": total_count,
            "page": skip // limit + 1,
            "size": limit,
        }

    # --- Helper methods --- #

    async def _invalidate_profile_cache(self, user_id: int) -> None:
        """
        Vô hiệu hóa cache liên quan đến hồ sơ người dùng

        Args:
            user_id: ID người dùng
        """
        # Giả sử đã thiết lập cache_manager từ app/cache/manager.py
        from app.cache.manager import cache_manager

        # Vô hiệu hóa cache hồ sơ người dùng
        await cache_manager.invalidate_by_tags([f"user:{user_id}", "profiles"])

        # Vô hiệu hóa cache danh sách hồ sơ phổ biến
        await cache_manager.invalidate_by_tags(["profiles:popular"])
