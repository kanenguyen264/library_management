from typing import Optional, Dict, Any, List
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload  # Dùng nếu cần load user

from app.user_site.models.preference import UserPreference
from app.user_site.models.user import User  # Để kiểm tra user_id
from app.core.exceptions import NotFoundException, ValidationException


class PreferenceRepository:
    """Repository cho các thao tác với Tùy chọn người dùng (UserPreference)."""

    # Định nghĩa các giá trị hợp lệ (nếu cần validate)
    VALID_THEMES = ["system", "light", "dark"]
    VALID_READING_MODES = ["continuous", "paged", "scroll"]
    VALID_PRIVACY_LEVELS = ["public", "followers_only", "private"]
    VALID_LANGUAGES = ["vi", "en"]  # Ví dụ

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession.

        Args:
            db: Đối tượng AsyncSession để tương tác với cơ sở dữ liệu.
        """
        self.db = db

    async def _create_default(self, user_id: int) -> UserPreference:
        """(Nội bộ) Tạo bản ghi tùy chọn với các giá trị mặc định."""
        default_prefs = UserPreference(
            user_id=user_id,
            theme="system",
            font_family="Open Sans",
            font_size=16.0,
            reading_mode="continuous",
            language="vi",
            notifications_enabled=True,
            email_notifications=True,
            push_notifications=True,
            reading_speed_wpm=200,
            auto_bookmark=True,
            display_recommendations=True,
            privacy_level="public",
        )
        self.db.add(default_prefs)
        await self.db.commit()
        await self.db.refresh(default_prefs)
        return default_prefs

    async def get_by_user_id(self, user_id: int) -> Optional[UserPreference]:
        """Lấy bản ghi tùy chọn người dùng theo user_id.

        Args:
            user_id: ID của người dùng.

        Returns:
            Đối tượng UserPreference hoặc None nếu không tìm thấy.
        """
        query = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_or_create(self, user_id: int) -> UserPreference:
        """Lấy tùy chọn người dùng, tạo mới với giá trị mặc định nếu chưa có.

        Args:
            user_id: ID của người dùng.

        Returns:
            Đối tượng UserPreference.
        """
        preference = await self.get_by_user_id(user_id)
        if not preference:
            # Kiểm tra user có tồn tại không trước khi tạo default?
            user = await self.db.get(User, user_id)
            if not user:
                raise NotFoundException(
                    f"Người dùng với ID {user_id} không tồn tại để tạo tùy chọn."
                )
            preference = await self._create_default(user_id)
        return preference

    async def update(self, user_id: int, data: Dict[str, Any]) -> UserPreference:
        """Cập nhật một hoặc nhiều tùy chọn người dùng.
           Nếu chưa có bản ghi tùy chọn, sẽ tạo mới.

        Args:
            user_id: ID của người dùng.
            data: Dict chứa các tùy chọn cần cập nhật và giá trị mới.

        Returns:
            Đối tượng UserPreference đã được cập nhật.

        Raises:
            ValidationException: Nếu giá trị cung cấp không hợp lệ.
        """
        preference = await self.get_or_create(user_id)

        allowed_fields = {  # Lấy các trường từ model hoặc định nghĩa ở đây
            field.name
            for field in UserPreference.__table__.columns
            if field.name != "user_id"
        }
        updated = False

        for key, value in data.items():
            if key in allowed_fields and value is not None:
                # --- Validation --- #
                if key == "theme" and value not in self.VALID_THEMES:
                    raise ValidationException(
                        f"Theme không hợp lệ: {value}. Các giá trị hợp lệ: {self.VALID_THEMES}"
                    )
                if key == "reading_mode" and value not in self.VALID_READING_MODES:
                    raise ValidationException(
                        f"Chế độ đọc không hợp lệ: {value}. Các giá trị hợp lệ: {self.VALID_READING_MODES}"
                    )
                if key == "privacy_level" and value not in self.VALID_PRIVACY_LEVELS:
                    raise ValidationException(
                        f"Mức độ riêng tư không hợp lệ: {value}. Các giá trị hợp lệ: {self.VALID_PRIVACY_LEVELS}"
                    )
                if key == "language" and value not in self.VALID_LANGUAGES:
                    raise ValidationException(
                        f"Ngôn ngữ không hợp lệ: {value}. Các giá trị hợp lệ: {self.VALID_LANGUAGES}"
                    )
                if key == "font_size" and not isinstance(value, (int, float)):
                    raise ValidationException(
                        f"Kích thước font không hợp lệ: {value}. Phải là số."
                    )
                # Thêm các validation khác nếu cần...
                # --- End Validation --- #

                if getattr(preference, key) != value:
                    setattr(preference, key, value)
                    updated = True

        if updated:
            await self.db.commit()
            await self.db.refresh(preference)

        return preference

    # Các phương thức tiện ích để cập nhật từng nhóm cài đặt

    async def update_theme(self, user_id: int, theme: str) -> UserPreference:
        """Cập nhật tùy chọn theme của người dùng."""
        if theme not in self.VALID_THEMES:
            raise ValidationException(
                f"Theme không hợp lệ: {theme}. Các giá trị hợp lệ: {self.VALID_THEMES}"
            )
        return await self.update(user_id, {"theme": theme})

    async def update_reading_preferences(
        self,
        user_id: int,
        font_family: Optional[str] = None,
        font_size: Optional[float] = None,
        reading_mode: Optional[str] = None,
    ) -> UserPreference:
        """Cập nhật tùy chọn đọc sách của người dùng."""
        data = {}
        if font_family is not None:
            data["font_family"] = font_family
        if font_size is not None:
            if not isinstance(font_size, (int, float)):
                raise ValidationException(
                    f"Kích thước font không hợp lệ: {font_size}. Phải là số."
                )
            data["font_size"] = font_size
        if reading_mode is not None:
            if reading_mode not in self.VALID_READING_MODES:
                raise ValidationException(
                    f"Chế độ đọc không hợp lệ: {reading_mode}. Các giá trị hợp lệ: {self.VALID_READING_MODES}"
                )
            data["reading_mode"] = reading_mode

        if not data:
            return await self.get_or_create(
                user_id
            )  # Trả về giá trị hiện tại nếu không có gì cập nhật

        return await self.update(user_id, data)

    async def update_notification_preferences(
        self,
        user_id: int,
        notifications_enabled: Optional[bool] = None,
        email_notifications: Optional[bool] = None,
        push_notifications: Optional[bool] = None,
    ) -> UserPreference:
        """Cập nhật tùy chọn thông báo của người dùng."""
        data = {}
        if notifications_enabled is not None:
            data["notifications_enabled"] = notifications_enabled
        if email_notifications is not None:
            data["email_notifications"] = email_notifications
        if push_notifications is not None:
            data["push_notifications"] = push_notifications

        if not data:
            return await self.get_or_create(user_id)

        return await self.update(user_id, data)

    async def update_privacy_level(
        self, user_id: int, privacy_level: str
    ) -> UserPreference:
        """Cập nhật mức độ riêng tư của người dùng."""
        if privacy_level not in self.VALID_PRIVACY_LEVELS:
            raise ValidationException(
                f"Mức độ riêng tư không hợp lệ: {privacy_level}. Các giá trị hợp lệ: {self.VALID_PRIVACY_LEVELS}"
            )
        return await self.update(user_id, {"privacy_level": privacy_level})

    async def update_language(self, user_id: int, language: str) -> UserPreference:
        """Cập nhật ngôn ngữ ưa thích của người dùng."""
        if language not in self.VALID_LANGUAGES:
            raise ValidationException(
                f"Ngôn ngữ không hợp lệ: {language}. Các giá trị hợp lệ: {self.VALID_LANGUAGES}"
            )
        return await self.update(user_id, {"language": language})

    # Các phương thức để lấy các nhóm cài đặt

    async def get_reading_settings(self, user_id: int) -> Dict[str, Any]:
        """Lấy các cài đặt liên quan đến đọc sách."""
        preference = await self.get_or_create(user_id)
        return {
            "font_family": preference.font_family,
            "font_size": preference.font_size,
            "reading_mode": preference.reading_mode,
            "reading_speed_wpm": preference.reading_speed_wpm,
            "auto_bookmark": preference.auto_bookmark,
        }

    async def get_notification_settings(self, user_id: int) -> Dict[str, bool]:
        """Lấy các cài đặt liên quan đến thông báo."""
        preference = await self.get_or_create(user_id)
        return {
            "notifications_enabled": preference.notifications_enabled,
            "email_notifications": preference.email_notifications,
            "push_notifications": preference.push_notifications,
        }

    async def get_privacy_settings(self, user_id: int) -> Dict[str, Any]:
        """Lấy các cài đặt liên quan đến riêng tư."""
        preference = await self.get_or_create(user_id)
        return {
            "privacy_level": preference.privacy_level,
            "display_recommendations": preference.display_recommendations,
            # Thêm các cài đặt riêng tư khác nếu có
        }

    # Đổi tên batch_update thành update cho nhất quán
    # async def batch_update(self, user_id: int, preferences: Dict[str, Any]) -> UserPreference:
    #     """Cập nhật hàng loạt các tùy chọn của người dùng."""
    #     return await self.update(user_id, preferences)
