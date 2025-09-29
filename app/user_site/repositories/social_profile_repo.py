from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.social_profile import SocialProfile, SocialProvider
from app.user_site.models.user import User
from app.core.exceptions import (
    NotFoundException,
    ValidationException,
    ConflictException,
)

# Có thể định nghĩa các provider hợp lệ
VALID_PROVIDERS = ["google", "facebook", "github", "apple"]  # Ví dụ


class SocialProfileRepository:
    """Repository cho các thao tác với Hồ sơ Mạng xã hội (SocialProfile)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def _validate_user(self, user_id: int):
        """Kiểm tra sự tồn tại của người dùng."""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValidationException(f"Người dùng với ID {user_id} không tồn tại.")

    async def create(self, profile_data: Dict[str, Any]) -> SocialProfile:
        """Tạo hồ sơ mạng xã hội mới.
           Nên sử dụng get_or_create thay vì gọi trực tiếp.

        Args:
            profile_data: Dict chứa dữ liệu (user_id, provider, provider_id, profile_data?).

        Returns:
            Đối tượng SocialProfile đã tạo.

        Raises:
            ValidationException, ConflictException.
        """
        user_id = profile_data.get("user_id")
        provider = profile_data.get("provider")
        provider_id = profile_data.get("provider_id")

        if not all([user_id, provider, provider_id]):
            raise ValidationException(
                "Thiếu thông tin bắt buộc: user_id, provider, provider_id."
            )

        await self._validate_user(user_id)

        if provider not in VALID_PROVIDERS:
            # Có thể cho phép provider tùy ý hoặc chỉ các provider được định nghĩa
            # raise ValidationException(f"Provider không hợp lệ: {provider}")
            pass  # Bỏ qua validation nếu cho phép provider tùy ý

        # Lọc dữ liệu
        allowed_fields = {
            col.name for col in SocialProfile.__table__.columns if col.name != "id"
        }
        filtered_data = {
            k: v
            for k, v in profile_data.items()
            if k in allowed_fields and v is not None
        }

        profile = SocialProfile(**filtered_data)
        self.db.add(profile)
        try:
            await self.db.commit()
            await self.db.refresh(profile, attribute_names=["user"])  # Load user
            return profile
        except IntegrityError as e:
            await self.db.rollback()
            # Kiểm tra lỗi unique constraint trên (provider, provider_id) hoặc (user_id, provider)
            existing_by_provider = await self.get_by_provider_id(provider, provider_id)
            if existing_by_provider:
                raise ConflictException(
                    f"Provider {provider} với ID {provider_id} đã được liên kết với người dùng khác (ID: {existing_by_provider.user_id})."
                )
            existing_by_user = await self.get_by_user_provider(user_id, provider)
            if existing_by_user:
                raise ConflictException(
                    f"Người dùng {user_id} đã liên kết với provider {provider} rồi (ID: {existing_by_user.id})."
                )
            raise ConflictException(f"Không thể tạo hồ sơ MXH: {e}")

    async def get_by_id(
        self, profile_id: int, with_user: bool = False
    ) -> Optional[SocialProfile]:
        """Lấy hồ sơ mạng xã hội theo ID.

        Args:
            profile_id: ID hồ sơ.
            with_user: Có tải thông tin User liên quan không.

        Returns:
            Đối tượng SocialProfile hoặc None.
        """
        query = select(SocialProfile).where(SocialProfile.id == profile_id)
        if with_user:
            query = query.options(selectinload(SocialProfile.user))
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_provider(
        self, user_id: int, provider: str, with_user: bool = False
    ) -> Optional[SocialProfile]:
        """Lấy hồ sơ mạng xã hội theo user_id và provider.

        Args:
            user_id: ID người dùng.
            provider: Tên nhà cung cấp (vd: 'google').
            with_user: Có tải User không.

        Returns:
            Đối tượng SocialProfile hoặc None.
        """
        query = select(SocialProfile).where(
            SocialProfile.user_id == user_id, SocialProfile.provider == provider
        )
        if with_user:
            query = query.options(selectinload(SocialProfile.user))
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_provider_id(
        self, provider: str, provider_id: str, with_user: bool = True
    ) -> Optional[SocialProfile]:
        """Lấy hồ sơ mạng xã hội theo provider và provider_id.
           Thường dùng để tìm user khi đăng nhập bằng MXH.

        Args:
            provider: Tên nhà cung cấp.
            provider_id: ID người dùng trên nhà cung cấp đó.
            with_user: Có tải User không (thường là True).

        Returns:
            Đối tượng SocialProfile hoặc None.
        """
        query = select(SocialProfile).where(
            SocialProfile.provider == provider,
            SocialProfile.provider_id == provider_id,
        )
        if with_user:
            query = query.options(selectinload(SocialProfile.user))
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(self, user_id: int) -> List[SocialProfile]:
        """Liệt kê tất cả hồ sơ mạng xã hội của một người dùng."""
        query = select(SocialProfile).where(SocialProfile.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update(
        self, profile_id: int, profile_data: Dict[str, Any]
    ) -> Optional[SocialProfile]:
        """Cập nhật thông tin hồ sơ mạng xã hội (thường là profile_data).

        Args:
            profile_id: ID hồ sơ.
            profile_data: Dict chứa dữ liệu cập nhật (chủ yếu là 'profile_data').

        Returns:
            Đối tượng SocialProfile đã cập nhật hoặc None nếu không tìm thấy.
        """
        profile = await self.get_by_id(profile_id)
        if not profile:
            return None  # Hoặc raise NotFoundException

        allowed_fields = {"profile_data"}  # Chỉ nên cho cập nhật trường này?
        updated = False

        for key, value in profile_data.items():
            if key in allowed_fields and value is not None:
                # Cần so sánh sâu nếu profile_data là JSON/Dict
                if getattr(profile, key) != value:
                    setattr(profile, key, value)
                    updated = True

        if updated:
            try:
                await self.db.commit()
                await self.db.refresh(profile, attribute_names=["user"])
            except IntegrityError as e:
                await self.db.rollback()
                raise ConflictException(f"Không thể cập nhật hồ sơ MXH: {e}")

        return profile

    async def delete(self, profile_id: int) -> bool:
        """Xóa hồ sơ mạng xã hội theo ID.

        Args:
            profile_id: ID hồ sơ cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        query = delete(SocialProfile).where(SocialProfile.id == profile_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def delete_by_user_provider(self, user_id: int, provider: str) -> bool:
        """Xóa hồ sơ mạng xã hội theo user_id và provider.

        Args:
            user_id: ID người dùng.
            provider: Tên nhà cung cấp.

        Returns:
            True nếu tìm thấy và xóa thành công, False nếu không tìm thấy.
        """
        query = delete(SocialProfile).where(
            SocialProfile.user_id == user_id, SocialProfile.provider == provider
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def get_or_create(
        self,
        provider: str,
        provider_id: str,
        user_id: Optional[int] = None,  # Cung cấp nếu user đã login và muốn liên kết
        profile_info: Optional[Dict[str, Any]] = None,  # Thông tin bổ sung từ provider
    ) -> Tuple[SocialProfile, bool]:
        """Lấy hoặc tạo mới hồ sơ mạng xã hội, xử lý liên kết tài khoản.

        Args:
            provider: Tên nhà cung cấp.
            provider_id: ID người dùng trên nhà cung cấp đó.
            user_id: ID người dùng hiện tại trong hệ thống (nếu có, để liên kết).
            profile_info: Thông tin hồ sơ từ provider (để cập nhật hoặc tạo mới).

        Returns:
            Tuple[SocialProfile, bool]: (Đối tượng hồ sơ, True nếu được tạo mới).

        Raises:
            ConflictException: Nếu tài khoản MXH đã liên kết với user khác.
            ValidationException: Nếu user_id cung cấp không tồn tại.
        """
        if not provider or not provider_id:
            raise ValidationException("Thiếu thông tin provider hoặc provider_id.")

        # 1. Tìm xem hồ sơ MXH này đã tồn tại chưa
        existing_profile = await self.get_by_provider_id(
            provider, provider_id, with_user=True
        )

        if existing_profile:
            # Đã tồn tại hồ sơ MXH
            # Kiểm tra xem nó có đang liên kết với user hiện tại không (nếu user_id được cung cấp)
            if user_id is not None and existing_profile.user_id != user_id:
                # Lỗi: Tài khoản MXH này đã được liên kết với người dùng khác
                raise ConflictException(
                    f"Tài khoản {provider} này đã được liên kết với người dùng khác (ID: {existing_profile.user_id})."
                )

            # Cập nhật profile_info nếu có và khác biệt
            updated = False
            if profile_info and existing_profile.profile_data != profile_info:
                existing_profile.profile_data = profile_info
                updated = True

            if updated:
                try:
                    await self.db.commit()
                    await self.db.refresh(existing_profile)
                except IntegrityError as e:
                    await self.db.rollback()
                    # Lỗi không mong muốn khi cập nhật
                    raise ConflictException(
                        f"Lỗi khi cập nhật hồ sơ MXH đã tồn tại: {e}"
                    )

            return existing_profile, False  # Trả về hồ sơ hiện có, không phải tạo mới

        # 2. Hồ sơ MXH chưa tồn tại
        if user_id is None:
            # Trường hợp đăng ký mới bằng MXH -> cần tạo User mới trước (logic này thường ở service layer)
            # Repository này chỉ nên tạo SocialProfile khi đã có user_id.
            # Hoặc có thể trả về lỗi/None để service xử lý.
            raise ValidationException("Cần user_id để tạo hồ sơ MXH mới.")

        # Đã có user_id (đăng nhập và liên kết hoặc vừa tạo user mới)
        # Kiểm tra xem user này đã liên kết với provider này chưa (dù provider_id khác)
        user_profile_for_provider = await self.get_by_user_provider(user_id, provider)
        if user_profile_for_provider:
            # Lỗi: User này đã liên kết với provider này rồi (bằng tài khoản MXH khác)
            raise ConflictException(
                f"Người dùng {user_id} đã liên kết với {provider} bằng tài khoản khác (ID: {user_profile_for_provider.provider_id})."
            )

        # Tạo hồ sơ mới và liên kết với user_id
        create_data = {
            "user_id": user_id,
            "provider": provider,
            "provider_id": provider_id,
            "profile_data": profile_info,
        }
        try:
            new_profile = await self.create(create_data)
            return new_profile, True  # Tạo mới thành công
        except ConflictException as e:
            # Bắt lỗi Conflict từ self.create (dù đã kiểm tra nhưng đề phòng race condition)
            # Thử lấy lại lần nữa
            existing = await self.get_by_provider_id(provider, provider_id)
            if existing:
                # Kiểm tra lại user_id phòng trường hợp cực hiếm
                if user_id is not None and existing.user_id != user_id:
                    raise ConflictException(
                        f"Tài khoản {provider} này vừa được liên kết với người dùng khác (ID: {existing.user_id}) trong lúc xử lý."
                    )
                return existing, False  # Trả về cái vừa được tạo bởi tiến trình khác
            else:
                raise e  # Raise lỗi gốc nếu không tìm thấy sau race condition
