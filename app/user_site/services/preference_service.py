from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.preference_repo import PreferenceRepository
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


class PreferenceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.preference_repo = PreferenceRepository(db)
        self.user_repo = UserRepository(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="preferences", tags=["user_preferences"])
    async def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """Lấy tùy chọn của người dùng.

        Args:
            user_id: ID người dùng

        Returns:
            Tùy chọn của người dùng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy hoặc tạo tùy chọn
        preference = await self.preference_repo.get_by_user_id(user_id)
        if not preference:
            # Tạo tùy chọn mặc định
            preference_data = {
                "user_id": user_id,
                "theme": "system",
                "font_family": "default",
                "font_size": "medium",
                "reading_mode": "continuous",
                "language": "vi",
                "notifications_enabled": True,
                "email_notifications": True,
                "push_notifications": True,
                "reading_speed_wpm": 250,
                "auto_bookmark": True,
                "display_recommendations": True,
                "privacy_level": "public",
            }

            preference = await self.preference_repo.create(preference_data)

        # Metrics
        self.metrics.track_user_activity("get_preferences", "registered")

        return preference

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="preferences", tags=["user_preferences"])
    async def update_user_preferences(
        self, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Cập nhật tùy chọn của người dùng.

        Args:
            user_id: ID người dùng
            data: Dữ liệu cập nhật

        Returns:
            Tùy chọn đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Làm sạch dữ liệu
        clean_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                clean_data[key] = sanitize_html(value)
            else:
                clean_data[key] = value

        # Đảm bảo không thay đổi user_id
        if "user_id" in clean_data:
            del clean_data["user_id"]

        # Kiểm tra tùy chọn hợp lệ
        if "theme" in clean_data and clean_data["theme"] not in [
            "light",
            "dark",
            "system",
        ]:
            raise BadRequestException(
                "Giao diện không hợp lệ. Hỗ trợ: light, dark, system"
            )

        if "font_size" in clean_data and clean_data["font_size"] not in [
            "small",
            "medium",
            "large",
            "x-large",
        ]:
            raise BadRequestException(
                "Kích thước font không hợp lệ. Hỗ trợ: small, medium, large, x-large"
            )

        if "reading_mode" in clean_data and clean_data["reading_mode"] not in [
            "continuous",
            "paginated",
            "scrolled",
        ]:
            raise BadRequestException(
                "Chế độ đọc không hợp lệ. Hỗ trợ: continuous, paginated, scrolled"
            )

        if "privacy_level" in clean_data and clean_data["privacy_level"] not in [
            "public",
            "friends",
            "private",
        ]:
            raise BadRequestException(
                "Mức độ quyền riêng tư không hợp lệ. Hỗ trợ: public, friends, private"
            )

        # Lấy hoặc tạo tùy chọn
        preference = await self.preference_repo.get_by_user_id(user_id)

        # Lưu trạng thái cũ nếu đã tồn tại
        before_state = dict(preference) if preference else None

        if not preference:
            # Tạo tùy chọn mặc định và cập nhật
            preference_data = {
                "user_id": user_id,
                "theme": "system",
                "font_family": "default",
                "font_size": "medium",
                "reading_mode": "continuous",
                "language": "vi",
                "notifications_enabled": True,
                "email_notifications": True,
                "push_notifications": True,
                "reading_speed_wpm": 250,
                "auto_bookmark": True,
                "display_recommendations": True,
                "privacy_level": "public",
                **clean_data,
            }

            updated_preference = await self.preference_repo.create(preference_data)
        else:
            # Cập nhật tùy chọn
            updated_preference = await self.preference_repo.update(
                preference["id"], clean_data
            )

        # Ghi log hoạt động
        updated_fields = list(clean_data.keys())

        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="UPDATE_PREFERENCES",
            resource_type="preferences",
            resource_id=str(updated_preference["id"]),
            before_state=before_state,
            after_state=dict(updated_preference),
            metadata={"updated_fields": updated_fields},
        )

        # Metrics
        self.metrics.track_user_activity("update_preferences", "registered")

        return updated_preference

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="preferences", tags=["user_preferences"])
    async def reset_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """Đặt lại tùy chọn của người dùng về mặc định.

        Args:
            user_id: ID người dùng

        Returns:
            Tùy chọn đã đặt lại

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy tùy chọn hiện tại để lưu trạng thái cũ
        preference = await self.preference_repo.get_by_user_id(user_id)
        before_state = dict(preference) if preference else None

        # Xóa tùy chọn hiện tại nếu có
        if preference:
            await self.preference_repo.delete(preference["id"])

        # Tạo tùy chọn mặc định
        default_preferences = {
            "user_id": user_id,
            "theme": "system",
            "font_family": "default",
            "font_size": "medium",
            "reading_mode": "continuous",
            "language": "vi",
            "notifications_enabled": True,
            "email_notifications": True,
            "push_notifications": True,
            "reading_speed_wpm": 250,
            "auto_bookmark": True,
            "display_recommendations": True,
            "privacy_level": "public",
        }

        new_preference = await self.preference_repo.create(default_preferences)

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="RESET_PREFERENCES",
            resource_type="preferences",
            resource_id=str(new_preference["id"]),
            before_state=before_state,
            after_state=dict(new_preference),
        )

        # Metrics
        self.metrics.track_user_activity("reset_preferences", "registered")

        result = dict(new_preference)
        result["message"] = "Đã đặt lại tùy chọn thành công"

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="preferences", tags=["user_preferences", "notification_settings"]
    )
    async def update_notification_settings(
        self,
        user_id: int,
        notifications_enabled: bool = True,
        email_notifications: bool = True,
        push_notifications: bool = True,
    ) -> Dict[str, Any]:
        """Cập nhật cài đặt thông báo của người dùng.

        Args:
            user_id: ID người dùng
            notifications_enabled: Bật/tắt tất cả thông báo
            email_notifications: Bật/tắt thông báo qua email
            push_notifications: Bật/tắt thông báo đẩy

        Returns:
            Cài đặt thông báo đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Chuẩn bị dữ liệu cập nhật
        data = {
            "notifications_enabled": notifications_enabled,
            "email_notifications": email_notifications,
            "push_notifications": push_notifications,
        }

        # Lấy hoặc tạo tùy chọn
        preference = await self.preference_repo.get_by_user_id(user_id)

        # Lưu trạng thái cũ nếu đã tồn tại
        before_state = dict(preference) if preference else None

        if not preference:
            # Tạo tùy chọn mặc định và cập nhật
            preference_data = {
                "user_id": user_id,
                "theme": "system",
                "font_family": "default",
                "font_size": "medium",
                "reading_mode": "continuous",
                "language": "vi",
                "reading_speed_wpm": 250,
                "auto_bookmark": True,
                "display_recommendations": True,
                "privacy_level": "public",
                **data,
            }

            updated_preference = await self.preference_repo.create(preference_data)
        else:
            # Cập nhật tùy chọn
            updated_preference = await self.preference_repo.update(
                preference["id"], data
            )

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="UPDATE_NOTIFICATION_SETTINGS",
            resource_type="preferences",
            resource_id=str(updated_preference["id"]),
            before_state=before_state,
            after_state=dict(updated_preference),
            metadata={
                "notifications_enabled": notifications_enabled,
                "email_notifications": email_notifications,
                "push_notifications": push_notifications,
            },
        )

        # Metrics
        self.metrics.track_user_activity("update_notification_settings", "registered")

        return {
            "notifications_enabled": updated_preference["notifications_enabled"],
            "email_notifications": updated_preference["email_notifications"],
            "push_notifications": updated_preference["push_notifications"],
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="preferences", tags=["user_preferences", "privacy_settings"]
    )
    async def update_privacy_settings(
        self, user_id: int, privacy_level: str
    ) -> Dict[str, Any]:
        """Cập nhật cài đặt quyền riêng tư của người dùng.

        Args:
            user_id: ID người dùng
            privacy_level: Mức độ quyền riêng tư (public, friends, private)

        Returns:
            Cài đặt quyền riêng tư đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu mức độ quyền riêng tư không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra mức độ quyền riêng tư hợp lệ
        valid_levels = ["public", "friends", "private"]
        if privacy_level not in valid_levels:
            raise BadRequestException(
                f"Mức độ quyền riêng tư không hợp lệ. Hỗ trợ: {', '.join(valid_levels)}"
            )

        # Chuẩn bị dữ liệu cập nhật
        data = {"privacy_level": privacy_level}

        # Lấy hoặc tạo tùy chọn
        preference = await self.preference_repo.get_by_user_id(user_id)

        # Lưu trạng thái cũ nếu đã tồn tại
        before_state = dict(preference) if preference else None

        if not preference:
            # Tạo tùy chọn mặc định và cập nhật
            preference_data = {
                "user_id": user_id,
                "theme": "system",
                "font_family": "default",
                "font_size": "medium",
                "reading_mode": "continuous",
                "language": "vi",
                "notifications_enabled": True,
                "email_notifications": True,
                "push_notifications": True,
                "reading_speed_wpm": 250,
                "auto_bookmark": True,
                "display_recommendations": True,
                **data,
            }

            updated_preference = await self.preference_repo.create(preference_data)
        else:
            # Cập nhật tùy chọn
            updated_preference = await self.preference_repo.update(
                preference["id"], data
            )

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="UPDATE_PRIVACY_SETTINGS",
            resource_type="preferences",
            resource_id=str(updated_preference["id"]),
            before_state=before_state,
            after_state=dict(updated_preference),
            metadata={"privacy_level": privacy_level},
        )

        # Metrics
        self.metrics.track_user_activity("update_privacy_settings", "registered")

        # Đồng bộ với social profile nếu có
        try:
            from app.user_site.services.social_profile_service import (
                SocialProfileService,
            )

            social_profile_service = SocialProfileService(self.db)
            await social_profile_service.sync_privacy_settings(
                user_id, {"is_private": privacy_level == "private"}
            )
        except ImportError:
            # Social profile service không có sẵn
            pass

        return {"privacy_level": updated_preference["privacy_level"]}

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="preferences", tags=["user_preferences", "reading_settings"]
    )
    async def update_reading_settings(
        self,
        user_id: int,
        font_size: Optional[str] = None,
        font_family: Optional[str] = None,
        reading_mode: Optional[str] = None,
        reading_speed_wpm: Optional[int] = None,
        auto_bookmark: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Cập nhật cài đặt đọc sách của người dùng.

        Args:
            user_id: ID người dùng
            font_size: Kích thước font chữ
            font_family: Phông chữ
            reading_mode: Chế độ đọc
            reading_speed_wpm: Tốc độ đọc (từ/phút)
            auto_bookmark: Tự động đánh dấu trang

        Returns:
            Cài đặt đọc sách đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra dữ liệu hợp lệ
        if font_size and font_size not in ["small", "medium", "large", "x-large"]:
            raise BadRequestException(
                "Kích thước font không hợp lệ. Hỗ trợ: small, medium, large, x-large"
            )

        if reading_mode and reading_mode not in ["continuous", "paginated", "scrolled"]:
            raise BadRequestException(
                "Chế độ đọc không hợp lệ. Hỗ trợ: continuous, paginated, scrolled"
            )

        if reading_speed_wpm and (
            not isinstance(reading_speed_wpm, int) or reading_speed_wpm <= 0
        ):
            raise BadRequestException("Tốc độ đọc phải là số nguyên dương")

        # Làm sạch dữ liệu
        if font_family:
            font_family = sanitize_html(font_family)

        # Chuẩn bị dữ liệu cập nhật
        data = {}
        if font_size is not None:
            data["font_size"] = font_size
        if font_family is not None:
            data["font_family"] = font_family
        if reading_mode is not None:
            data["reading_mode"] = reading_mode
        if reading_speed_wpm is not None:
            data["reading_speed_wpm"] = reading_speed_wpm
        if auto_bookmark is not None:
            data["auto_bookmark"] = auto_bookmark

        if not data:
            raise BadRequestException("Không có dữ liệu để cập nhật")

        # Lấy hoặc tạo tùy chọn
        preference = await self.preference_repo.get_by_user_id(user_id)

        # Lưu trạng thái cũ nếu đã tồn tại
        before_state = dict(preference) if preference else None

        if not preference:
            # Tạo tùy chọn mặc định và cập nhật
            preference_data = {
                "user_id": user_id,
                "theme": "system",
                "font_family": "default",
                "font_size": "medium",
                "reading_mode": "continuous",
                "language": "vi",
                "notifications_enabled": True,
                "email_notifications": True,
                "push_notifications": True,
                "reading_speed_wpm": 250,
                "auto_bookmark": True,
                "display_recommendations": True,
                "privacy_level": "public",
                **data,
            }

            updated_preference = await self.preference_repo.create(preference_data)
        else:
            # Cập nhật tùy chọn
            updated_preference = await self.preference_repo.update(
                preference["id"], data
            )

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="UPDATE_READING_SETTINGS",
            resource_type="preferences",
            resource_id=str(updated_preference["id"]),
            before_state=before_state,
            after_state=dict(updated_preference),
            metadata={"updated_fields": list(data.keys())},
        )

        # Metrics
        self.metrics.track_user_activity("update_reading_settings", "registered")

        return {
            "font_size": updated_preference["font_size"],
            "font_family": updated_preference["font_family"],
            "reading_mode": updated_preference["reading_mode"],
            "reading_speed_wpm": updated_preference["reading_speed_wpm"],
            "auto_bookmark": updated_preference["auto_bookmark"],
        }
