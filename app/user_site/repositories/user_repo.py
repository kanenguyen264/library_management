from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.user import User, Gender
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ValidationException,
)


class UserRepository:
    """Repository cho các thao tác CRUD và quản lý Người dùng (User)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    def _convert_to_naive_datetime(self, dt: datetime) -> datetime:
        """
        Chuyển đổi datetime với timezone sang datetime không timezone
        để tương thích với cột TIMESTAMP WITHOUT TIME ZONE trong cơ sở dữ liệu.

        Args:
            dt: Đối tượng datetime cần chuyển đổi

        Returns:
            datetime không có timezone thông tin
        """
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    async def create(self, user_data: Dict[str, Any]) -> User:
        """Tạo người dùng mới.
           Lưu ý: password_hash phải được tạo ở service layer.

        Args:
            user_data: Dict chứa dữ liệu người dùng (username, email, password_hash, ...).

        Returns:
            Đối tượng User đã tạo.

        Raises:
            ConflictException: Nếu username hoặc email đã tồn tại.
            ValidationException: Nếu thiếu trường bắt buộc.
            IntegrityError: Nếu có lỗi ràng buộc CSDL khác.
        """
        username = user_data.get("username")
        email = user_data.get("email")
        password_hash = user_data.get("password_hash")  # Quan trọng: chỉ nhận hash

        if not all([username, email, password_hash]):
            raise ValidationException(
                "Thiếu thông tin bắt buộc: username, email, password_hash."
            )

        # Kiểm tra username và email đã tồn tại chưa (trong cùng một query cho hiệu quả)
        existing_user = await self.get_by_username_or_email(username, email)
        if existing_user:
            if existing_user.username.lower() == username.lower():
                raise ConflictException(f"Username '{username}' đã được sử dụng")
            if existing_user.email.lower() == email.lower():
                raise ConflictException(f"Email '{email}' đã được sử dụng")

        # Lọc các trường hợp lệ của model User
        allowed_fields = {
            col.name
            for col in User.__table__.columns
            if col.name not in ["id", "created_at", "updated_at"]
        }
        # Không cho phép set các trường boolean nhạy cảm trực tiếp khi tạo (vd: is_admin)
        protected_fields = {"is_admin", "is_superuser", "is_staff"}
        filtered_data = {
            k: v
            for k, v in user_data.items()
            if k in allowed_fields and k not in protected_fields and v is not None
        }

        # Đặt giá trị mặc định cho các trường boolean quan trọng
        filtered_data["is_active"] = filtered_data.get(
            "is_active", True
        )  # Mặc định active
        filtered_data["is_verified"] = filtered_data.get(
            "is_verified", False
        )  # Mặc định chưa verify
        filtered_data["is_premium"] = filtered_data.get("is_premium", False)

        user = User(**filtered_data)
        self.db.add(user)
        try:
            await self.db.commit()
            await self.db.refresh(
                user
            )  # Refresh để lấy ID và các giá trị default từ DB
            return user
        except IntegrityError as e:
            await self.db.rollback()
            # Bắt lại lỗi unique nếu race condition xảy ra
            existing_user = await self.get_by_username_or_email(username, email)
            if existing_user:
                if existing_user.username.lower() == username.lower():
                    raise ConflictException(
                        f"Username '{username}' đã được sử dụng (race condition)"
                    )
                if existing_user.email.lower() == email.lower():
                    raise ConflictException(
                        f"Email '{email}' đã được sử dụng (race condition)"
                    )
            raise  # Re-raise lỗi IntegrityError gốc nếu không phải do unique constraint

    async def get_by_id(
        self, user_id: int, with_relations: List[str] = None
    ) -> Optional[User]:
        """Lấy người dùng theo ID.

        Args:
            user_id: ID người dùng.
            with_relations: Danh sách quan hệ cần tải (vd: ['social_profiles', 'preferences', 'followers']).

        Returns:
            Đối tượng User hoặc None.
        """
        query = select(User).where(User.id == user_id)

        if with_relations:
            options = []
            if "social_profiles" in with_relations:
                options.append(selectinload(User.social_profiles))
            if "preferences" in with_relations:
                options.append(selectinload(User.preferences))
            if "badges" in with_relations:
                options.append(selectinload(User.badges))
            if "achievements" in with_relations:
                options.append(selectinload(User.achievements))
            if "followers" in with_relations:
                options.append(
                    selectinload(User.followers).selectinload("follower")
                )  # Load cả user follower
            if "following" in with_relations:
                options.append(
                    selectinload(User.following).selectinload("followed")
                )  # Load cả user followed
            # Thêm các quan hệ khác nếu cần
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_username(
        self, username: str, with_relations: List[str] = None
    ) -> Optional[User]:
        """Lấy người dùng theo username (không phân biệt hoa thường)."""
        query = select(User).where(User.username.ilike(username))
        if with_relations:  # Copy logic tải quan hệ từ get_by_id nếu cần
            options = []
            if "social_profiles" in with_relations:
                options.append(selectinload(User.social_profiles))
            if "preferences" in with_relations:
                options.append(selectinload(User.preferences))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_email(
        self, email: str, with_relations: List[str] = None
    ) -> Optional[User]:
        """Lấy người dùng theo email (không phân biệt hoa thường)."""
        query = select(User).where(User.email.ilike(email))
        if with_relations:  # Copy logic tải quan hệ từ get_by_id nếu cần
            options = []
            if "social_profiles" in with_relations:
                options.append(selectinload(User.social_profiles))
            if "preferences" in with_relations:
                options.append(selectinload(User.preferences))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_username_or_email(
        self, username: str, email: str, with_relations: List[str] = None
    ) -> Optional[User]:
        """Lấy người dùng theo username hoặc email (không phân biệt hoa thường)."""
        query = select(User).where(
            or_(User.username.ilike(username), User.email.ilike(email))
        )
        if with_relations:  # Copy logic tải quan hệ từ get_by_id nếu cần
            options = []
            if "social_profiles" in with_relations:
                options.append(selectinload(User.social_profiles))
            if "preferences" in with_relations:
                options.append(selectinload(User.preferences))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update(self, user_id: int, user_data: Dict[str, Any]) -> Optional[User]:
        """Cập nhật thông tin người dùng.
           Không cho phép cập nhật trực tiếp username, email, password_hash qua phương thức này.
           Sử dụng các phương thức chuyên biệt (vd: update_password, request_email_change).

        Args:
            user_id: ID người dùng.
            user_data: Dict chứa dữ liệu cập nhật (vd: full_name, display_name, bio, avatar_url, gender, dob,...).

        Returns:
            Đối tượng User đã cập nhật hoặc None nếu không tìm thấy.

        Raises:
            ConflictException: Nếu có lỗi ràng buộc khi cập nhật.
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None  # Hoặc raise NotFoundException

        # Các trường được phép cập nhật qua phương thức chung này
        allowed_fields = {
            "full_name",
            "display_name",
            "bio",
            "avatar_url",
            "cover_url",
            "gender",
            "date_of_birth",
            "location",
            "website_url",
            "last_login",
            "last_active",  # Các trường này thường cập nhật tự động
            # Không bao gồm: username, email, password_hash, is_active, is_verified, is_premium, tokens
        }
        updated = False

        for key, value in user_data.items():
            if key in allowed_fields:
                # Validate Gender enum nếu có
                if (
                    key == "gender"
                    and value is not None
                    and not isinstance(value, Gender)
                ):
                    try:
                        value = Gender(value)  # Thử chuyển đổi string thành Enum
                    except ValueError:
                        raise ValidationException(
                            f"Giá trị giới tính không hợp lệ: {value}"
                        )

                if getattr(user, key) != value:
                    setattr(user, key, value)
                    updated = True

        if updated:
            # Chuyển đổi datetime với timezone sang datetime không timezone
            now_with_tz = datetime.now(timezone.utc)
            user.updated_at = self._convert_to_naive_datetime(now_with_tz)
            try:
                await self.db.commit()
                await self.db.refresh(user)  # Refresh để lấy updated_at từ DB
            except IntegrityError as e:
                await self.db.rollback()
                raise ConflictException(f"Không thể cập nhật người dùng: {e}")

        return user

    async def delete(self, user_id: int) -> bool:
        """Xóa người dùng.
           Lưu ý: Việc xóa dữ liệu liên quan (posts, comments, likes, ...) cần được xử lý
           ở service layer hoặc bằng cascade delete trong CSDL.

        Args:
            user_id: ID người dùng cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        # Thay vì xóa cứng, có thể chỉ đánh dấu is_active = False
        # return await self.deactivate_user(user_id) is not None

        # Xóa cứng:
        query = delete(User).where(User.id == user_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def set_premium_status(
        self, user_id: int, is_premium: bool, premium_until: Optional[datetime] = None
    ) -> Optional[User]:
        """Cập nhật trạng thái premium cho người dùng."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        updated = False
        if user.is_premium != is_premium:
            user.is_premium = is_premium
            updated = True
        # Chỉ cập nhật premium_until nếu đang set premium
        if is_premium and user.premium_until != premium_until:
            user.premium_until = premium_until
            updated = True
        # Nếu bỏ premium, xóa premium_until
        elif not is_premium and user.premium_until is not None:
            user.premium_until = None
            updated = True

        if updated:
            # Chuyển đổi datetime với timezone sang datetime không timezone
            now_with_tz = datetime.now(timezone.utc)
            user.updated_at = self._convert_to_naive_datetime(now_with_tz)
            try:
                await self.db.commit()
                await self.db.refresh(user)  # Refresh để lấy updated_at từ DB
            except IntegrityError as e:
                await self.db.rollback()
                raise ConflictException(f"Không thể cập nhật người dùng: {e}")

        return user

    async def update_last_login(self, user_id: int) -> Optional[User]:
        """Cập nhật thời gian đăng nhập cuối."""
        # Chuyển đổi datetime với timezone sang datetime không timezone
        # để tương thích với cột TIMESTAMP WITHOUT TIME ZONE trong cơ sở dữ liệu
        now_with_tz = datetime.now(timezone.utc)
        now_without_tz = self._convert_to_naive_datetime(now_with_tz)
        return await self.update(user_id, {"last_login": now_without_tz})

    async def update_last_active(self, user_id: int) -> Optional[User]:
        """Cập nhật thời gian hoạt động cuối."""
        # Chuyển đổi datetime với timezone sang datetime không timezone
        # để tương thích với cột TIMESTAMP WITHOUT TIME ZONE trong cơ sở dữ liệu
        now_with_tz = datetime.now(timezone.utc)
        now_without_tz = self._convert_to_naive_datetime(now_with_tz)
        return await self.update(user_id, {"last_active": now_without_tz})

    async def verify_email(self, user_id: int) -> Optional[User]:
        """Xác thực email người dùng và xóa token."""
        user = await self.get_by_id(user_id)
        if not user:
            return None
        if user.is_verified:
            return user  # Đã xác thực rồi

        user.is_verified = True
        user.verification_token = None  # Xóa token sau khi xác thực
        # Cập nhật thời gian chỉnh sửa
        now_with_tz = datetime.now(timezone.utc)
        user.updated_at = self._convert_to_naive_datetime(now_with_tz)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def set_verification_token(self, user_id: int, token: str) -> Optional[User]:
        """Đặt token xác thực email.
        Cũng có thể đặt thời gian hết hạn cho token nếu cần.
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None
        if user.is_verified:
            raise ValidationException("Email đã được xác thực.")  # Không cần token nữa

        user.verification_token = token
        user.is_verified = False  # Đảm bảo trạng thái là chưa xác thực
        # Cập nhật thời gian chỉnh sửa
        now_with_tz = datetime.now(timezone.utc)
        user.updated_at = self._convert_to_naive_datetime(now_with_tz)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_by_verification_token(self, token: str) -> Optional[User]:
        """Lấy người dùng theo token xác thực.
        Có thể thêm kiểm tra token hết hạn nếu có.
        """
        if not token:
            return None
        query = select(User).where(User.verification_token == token)
        # Thêm điều kiện kiểm tra hết hạn nếu có trường expires
        # now_without_tz = self._convert_to_naive_datetime(datetime.now(timezone.utc))
        # query = query.where(User.verification_token_expires > now_without_tz)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def set_password_reset_token(
        self, user_id: int, token: str, expires: datetime
    ) -> Optional[User]:
        """Đặt token đặt lại mật khẩu và thời gian hết hạn."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.reset_password_token = token
        # Đảm bảo expires không có timezone
        user.reset_token_expires = self._convert_to_naive_datetime(expires)

        # Cập nhật thời gian chỉnh sửa
        now_with_tz = datetime.now(timezone.utc)
        user.updated_at = self._convert_to_naive_datetime(now_with_tz)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_by_reset_password_token(self, token: str) -> Optional[User]:
        """Lấy người dùng theo token đặt lại mật khẩu hợp lệ (chưa hết hạn)."""
        if not token:
            return None

        # Chuyển đổi datetime hiện tại sang định dạng không có timezone để so sánh
        now_with_tz = datetime.now(timezone.utc)
        now_without_tz = self._convert_to_naive_datetime(now_with_tz)

        query = select(User).where(
            User.reset_password_token == token,
            User.reset_token_expires > now_without_tz,  # Chỉ lấy token còn hạn
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_password(self, user_id: int, password_hash: str) -> Optional[User]:
        """Cập nhật mật khẩu (hash) và xóa token reset.

        Args:
            user_id: ID người dùng.
            password_hash: Hash mật khẩu mới.

        Returns:
            Đối tượng User đã cập nhật hoặc None.
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.password_hash = password_hash
        # Xóa token reset sau khi đổi mật khẩu thành công
        user.reset_password_token = None
        user.reset_token_expires = None
        # Cập nhật thời gian chỉnh sửa
        now_with_tz = datetime.now(timezone.utc)
        user.updated_at = self._convert_to_naive_datetime(now_with_tz)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_premium: Optional[bool] = None,
        sort_by: str = "created_at",  # 'created_at', 'username', 'last_login'
        sort_desc: bool = False,
        with_relations: List[str] = None,
    ) -> List[User]:
        """Liệt kê danh sách người dùng với bộ lọc và sắp xếp.

        Args:
            skip, limit: Phân trang.
            search: Từ khóa tìm kiếm (username, email, full_name, display_name).
            is_active: Lọc theo trạng thái active.
            is_premium: Lọc theo trạng thái premium.
            sort_by: Trường sắp xếp.
            sort_desc: Sắp xếp giảm dần.
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Danh sách User.
        """
        query = select(User)

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.full_name.ilike(search_pattern),
                    User.display_name.ilike(search_pattern),
                )
            )
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if is_premium is not None:
            query = query.where(User.is_premium == is_premium)

        # Sắp xếp
        sort_column_map = {
            "username": User.username,
            "email": User.email,
            "created_at": User.created_at,
            "last_login": User.last_login,
            "last_active": User.last_active,
            "display_name": User.display_name,
        }
        sort_column = sort_column_map.get(sort_by, User.created_at)

        # Xử lý None khi sắp xếp (vd: last_login có thể là None)
        if sort_desc:
            order = (
                desc(sort_column.nullslast())
                if sort_column is not None
                else desc(User.created_at)
            )
        else:
            order = (
                asc(sort_column.nullsfirst())
                if sort_column is not None
                else asc(User.created_at)
            )
        query = query.order_by(order)

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load relations
        if with_relations:
            options = []
            if "social_profiles" in with_relations:
                options.append(selectinload(User.social_profiles))
            if "preferences" in with_relations:
                options.append(selectinload(User.preferences))
            # Thêm các quan hệ khác nếu cần
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_users(
        self,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_premium: Optional[bool] = None,
    ) -> int:
        """Đếm số lượng người dùng với bộ lọc."""
        query = select(func.count(User.id)).select_from(User)

        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.full_name.ilike(search_pattern),
                    User.display_name.ilike(search_pattern),
                )
            )
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if is_premium is not None:
            query = query.where(User.is_premium == is_premium)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def deactivate_user(self, user_id: int) -> Optional[User]:
        """Vô hiệu hóa tài khoản người dùng (đặt is_active = False)."""
        user = await self.get_by_id(user_id)
        if not user:
            return None
        if not user.is_active:
            return user  # Đã vô hiệu hóa rồi

        user.is_active = False
        # Cập nhật thời gian chỉnh sửa
        now_with_tz = datetime.now(timezone.utc)
        user.updated_at = self._convert_to_naive_datetime(now_with_tz)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def reactivate_user(self, user_id: int) -> Optional[User]:
        """Kích hoạt lại tài khoản người dùng (đặt is_active = True)."""
        user = await self.get_by_id(user_id)
        if not user:
            return None
        if user.is_active:
            return user  # Đã active rồi

        user.is_active = True
        # Cập nhật thời gian chỉnh sửa
        now_with_tz = datetime.now(timezone.utc)
        user.updated_at = self._convert_to_naive_datetime(now_with_tz)
        await self.db.commit()
        await self.db.refresh(user)
        return user
