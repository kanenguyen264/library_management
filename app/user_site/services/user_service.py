from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import uuid
import secrets
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.social_profile_repo import SocialProfileRepository
from app.user_site.repositories.preference_repo import PreferenceRepository
from app.user_site.repositories.following_repo import FollowingRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ConflictException,
    ForbiddenException,
)
from app.core.security import hash_password, verify_password
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.social_profile_repo = SocialProfileRepository(db)
        self.preference_repo = PreferenceRepository(db)
        self.following_repo = FollowingRepository(db)

    async def create_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tạo người dùng mới.

        Args:
            data: Dữ liệu người dùng

        Returns:
            Thông tin người dùng đã tạo

        Raises:
            BadRequestException: Nếu thiếu thông tin bắt buộc
            ConflictException: Nếu username hoặc email đã tồn tại
        """
        # Kiểm tra các trường bắt buộc
        required_fields = ["username", "email", "password"]
        for field in required_fields:
            if field not in data or not data[field]:
                raise BadRequestException(detail=f"Trường {field} là bắt buộc")

        # Băm mật khẩu
        if "password" in data:
            data["password_hash"] = hash_password(data["password"])
            del data["password"]

        # Tạo token xác thực email
        data["verification_token"] = str(uuid.uuid4())

        # Mặc định các trường khác
        if "is_active" not in data:
            data["is_active"] = True

        if "is_verified" not in data:
            data["is_verified"] = False

        if "display_name" not in data or not data["display_name"]:
            data["display_name"] = data["username"]

        if "last_login" not in data:
            data["last_login"] = datetime.now()

        if "last_active" not in data:
            data["last_active"] = datetime.now()

        # Tạo người dùng
        user = await self.user_repo.create(data)

        # Khởi tạo hồ sơ xã hội và tùy chọn cho người dùng mới
        if user:
            profile_data = {
                "user_id": user.id,
                "display_name": user.display_name,
                "bio": "",
                "website": "",
                "facebook": "",
                "twitter": "",
                "instagram": "",
                "goodreads": "",
                "is_private": False,
                "show_reading_activity": True,
                "show_reviews": True,
                "show_following": True,
            }

            preference_data = {
                "user_id": user.id,
                "theme": "light",
                "language": "vi",
                "font_size": "medium",
                "font_family": "system",
                "reading_mode": "day",
                "notifications_enabled": True,
                "email_notifications": True,
                "push_notifications": True,
                "privacy_level": "public",
                "reading_speed_wpm": 250,
                "auto_bookmark": True,
            }

            await self.social_profile_repo.create(profile_data)
            await self.preference_repo.create(preference_data)

            # Log user registration activity
            await create_user_activity_log(
                self.db,
                UserActivityLogCreate(
                    user_id=user.id,
                    activity_type="REGISTRATION",
                    entity_type="USER",
                    entity_id=user.id,
                    description=f"User registered with username {user.username}",
                    metadata={"email": user.email},
                ),
            )

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "full_name": user.full_name,
            "avatar": user.avatar_url,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_premium": user.is_premium,
            "premium_until": user.premium_until,
            "verification_token": user.verification_token,
            "gender": user.gender,
            "birth_date": user.birth_date,
            "country": user.country,
            "bio": user.bio,
            "last_login": user.last_login,
            "last_active": user.last_active,
        }

    async def get_user(self, user_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin người dùng theo ID.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông tin người dùng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Lấy số lượng người theo dõi và đang theo dõi
        followers_count = await self.following_repo.count_followers(user_id)
        following_count = await self.following_repo.count_following(user_id)

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "full_name": user.full_name,
            "avatar": user.avatar_url,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_premium": user.is_premium,
            "premium_until": user.premium_until,
            "gender": user.gender,
            "birth_date": user.birth_date,
            "country": user.country,
            "bio": user.bio,
            "last_login": user.last_login,
            "last_active": user.last_active,
            "followers_count": followers_count,
            "following_count": following_count,
        }

    async def get_user_by_username(self, username: str) -> Dict[str, Any]:
        """
        Lấy thông tin người dùng theo username.

        Args:
            username: Username của người dùng

        Returns:
            Thông tin người dùng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        user = await self.user_repo.get_by_username(username)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với username {username}"
            )

        # Lấy số lượng người theo dõi và đang theo dõi
        followers_count = await self.following_repo.count_followers(user.id)
        following_count = await self.following_repo.count_following(user.id)

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "full_name": user.full_name,
            "avatar": user.avatar_url,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_premium": user.is_premium,
            "premium_until": user.premium_until,
            "gender": user.gender,
            "birth_date": user.birth_date,
            "country": user.country,
            "bio": user.bio,
            "last_login": user.last_login,
            "last_active": user.last_active,
            "followers_count": followers_count,
            "following_count": following_count,
        }

    async def get_user_by_email(self, email: str) -> Dict[str, Any]:
        """
        Lấy thông tin người dùng theo email.

        Args:
            email: Email của người dùng

        Returns:
            Thông tin người dùng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với email {email}"
            )

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "full_name": user.full_name,
            "avatar": user.avatar_url,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_premium": user.is_premium,
            "premium_until": user.premium_until,
        }

    async def update_user(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cập nhật thông tin người dùng.

        Args:
            user_id: ID của người dùng
            data: Dữ liệu cập nhật

        Returns:
            Thông tin người dùng đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            ConflictException: Nếu username hoặc email đã tồn tại
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra username đã tồn tại chưa (nếu có)
        if "username" in data and data["username"] != user.username:
            existing = await self.user_repo.get_by_username(data["username"])
            if existing:
                raise ConflictException(
                    detail=f"Username '{data['username']}' đã được sử dụng"
                )

        # Kiểm tra email đã tồn tại chưa (nếu có)
        if "email" in data and data["email"] != user.email:
            existing = await self.user_repo.get_by_email(data["email"])
            if existing:
                raise ConflictException(
                    detail=f"Email '{data['email']}' đã được sử dụng"
                )

        # Nếu cập nhật password
        if "password" in data:
            data["password_hash"] = hash_password(data["password"])
            del data["password"]

        # Cập nhật người dùng
        updated = await self.user_repo.update(user_id, data)

        # Cập nhật display_name trong social profile nếu có thay đổi
        if "display_name" in data:
            profile = await self.social_profile_repo.get_by_user_id(user_id)
            if profile:
                await self.social_profile_repo.update(
                    profile.id, {"display_name": data["display_name"]}
                )

        # Log user profile update activity
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="PROFILE_UPDATE",
                entity_type="USER",
                entity_id=user_id,
                description=f"User updated profile information",
                metadata=data,
            ),
        )

        # Lấy số lượng người theo dõi và đang theo dõi
        followers_count = await self.following_repo.count_followers(user_id)
        following_count = await self.following_repo.count_following(user_id)

        return {
            "id": updated.id,
            "username": updated.username,
            "email": updated.email,
            "display_name": updated.display_name,
            "full_name": updated.full_name,
            "avatar": updated.avatar_url,
            "is_active": updated.is_active,
            "is_verified": updated.is_verified,
            "is_premium": updated.is_premium,
            "premium_until": updated.premium_until,
            "gender": updated.gender,
            "birth_date": updated.birth_date,
            "country": updated.country,
            "bio": updated.bio,
            "last_login": updated.last_login,
            "last_active": updated.last_active,
            "followers_count": followers_count,
            "following_count": following_count,
        }

    async def delete_user(self, user_id: int) -> Dict[str, Any]:
        """
        Xóa người dùng.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Get user details before deletion for logging
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        await self.user_repo.delete(user_id)

        # Log user deletion activity
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="ACCOUNT_DELETION",
                entity_type="USER",
                entity_id=user_id,
                description=f"User account deleted: {user.username}",
                metadata={"email": user.email},
            ),
        )

        return {"message": "Đã xóa người dùng thành công"}

    async def list_users(
        self, skip: int = 0, limit: int = 20, search: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lấy danh sách người dùng.

        Args:
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            search: Từ khóa tìm kiếm (tùy chọn)

        Returns:
            Danh sách người dùng và thông tin phân trang
        """
        users = await self.user_repo.list_users(skip, limit, search)
        total = await self.user_repo.count_users(search)

        return {
            "items": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "display_name": user.display_name,
                    "full_name": user.full_name,
                    "avatar": user.avatar_url,
                    "is_active": user.is_active,
                    "is_verified": user.is_verified,
                    "is_premium": user.is_premium,
                    "last_login": user.last_login,
                    "last_active": user.last_active,
                }
                for user in users
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def authenticate_user(
        self, username_or_email: str, password: str
    ) -> Optional[Dict[str, Any]]:
        """
        Xác thực người dùng bằng username/email và mật khẩu.

        Args:
            username_or_email: Username hoặc email
            password: Mật khẩu

        Returns:
            Thông tin người dùng nếu xác thực thành công, None nếu thất bại
        """
        # Kiểm tra xem đầu vào là username hay email
        if "@" in username_or_email:
            user = await self.user_repo.get_by_email(username_or_email)
        else:
            user = await self.user_repo.get_by_username(username_or_email)

        if not user:
            return None

        # Kiểm tra người dùng có hoạt động không
        if not user.is_active:
            return None

        # Kiểm tra mật khẩu
        if not verify_password(password, user.password_hash):
            return None

        # Cập nhật thời gian đăng nhập
        await self.user_repo.update_last_login(user.id)

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_premium": user.is_premium,
            "avatar": user.avatar_url,
        }

    async def verify_email(self, token: str) -> Dict[str, Any]:
        """
        Xác thực email của người dùng.

        Args:
            token: Token xác thực

        Returns:
            Thông tin xác thực

        Raises:
            NotFoundException: Nếu không tìm thấy token
        """
        user = await self.user_repo.get_by_verification_token(token)
        if not user:
            raise NotFoundException(
                detail="Token xác thực không hợp lệ hoặc đã hết hạn"
            )

        # Xác thực email
        updated = await self.user_repo.verify_email(user.id)

        # Log email verification activity
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user.id,
                activity_type="EMAIL_VERIFICATION",
                entity_type="USER",
                entity_id=user.id,
                description=f"User verified email: {user.email}",
            ),
        )

        return {"user_id": updated.id, "is_verified": updated.is_verified}

    async def request_password_reset(self, email: str) -> Dict[str, Any]:
        """
        Yêu cầu đặt lại mật khẩu.

        Args:
            email: Email của người dùng

        Returns:
            Thông tin token đặt lại mật khẩu

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với email {email}"
            )

        # Tạo token đặt lại mật khẩu
        token = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(hours=24)

        # Lưu token
        await self.user_repo.set_password_reset_token(user.id, token, expires)

        return {
            "user_id": user.id,
            "email": user.email,
            "reset_token": token,
            "expires_at": expires,
        }

    async def reset_password(self, token: str, new_password: str) -> Dict[str, Any]:
        """
        Đặt lại mật khẩu.

        Args:
            token: Token đặt lại mật khẩu
            new_password: Mật khẩu mới

        Returns:
            Thông tin kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy token hoặc token đã hết hạn
        """
        user = await self.user_repo.get_by_reset_password_token(token)
        if not user:
            raise NotFoundException(
                detail="Token đặt lại mật khẩu không hợp lệ hoặc đã hết hạn"
            )

        # Băm mật khẩu mới
        password_hash = hash_password(new_password)

        # Cập nhật mật khẩu
        await self.user_repo.update_password(user.id, password_hash)

        return {"user_id": user.id, "message": "Đã đặt lại mật khẩu thành công"}

    async def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> Dict[str, Any]:
        """
        Thay đổi mật khẩu.

        Args:
            user_id: ID của người dùng
            current_password: Mật khẩu hiện tại
            new_password: Mật khẩu mới

        Returns:
            Thông tin kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu mật khẩu hiện tại không đúng
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra mật khẩu hiện tại
        if not verify_password(current_password, user.password_hash):
            raise BadRequestException(detail="Mật khẩu hiện tại không đúng")

        # Băm mật khẩu mới
        password_hash = hash_password(new_password)

        # Cập nhật mật khẩu
        await self.user_repo.update_password(user_id, password_hash)

        # Log password change activity
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="PASSWORD_CHANGE",
                entity_type="USER",
                entity_id=user_id,
                description=f"User changed password",
            ),
        )

        return {"user_id": user_id, "message": "Đã thay đổi mật khẩu thành công"}

    async def update_last_active(self, user_id: int) -> Dict[str, Any]:
        """
        Cập nhật thời gian hoạt động cuối.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông tin kết quả
        """
        updated = await self.user_repo.update_last_active(user_id)

        return {"user_id": updated.id, "last_active": updated.last_active}

    async def update_avatar(self, user_id: int, avatar_url: str) -> Dict[str, Any]:
        """
        Cập nhật avatar.

        Args:
            user_id: ID của người dùng
            avatar_url: Đường dẫn avatar mới

        Returns:
            Thông tin kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Cập nhật avatar
        updated = await self.user_repo.update(user_id, {"avatar_url": avatar_url})

        return {"user_id": updated.id, "avatar": updated.avatar_url}

    async def deactivate_account(self, user_id: int) -> Dict[str, Any]:
        """
        Vô hiệu hóa tài khoản.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông tin kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Vô hiệu hóa tài khoản
        updated = await self.user_repo.deactivate_user(user_id)

        return {
            "user_id": updated.id,
            "is_active": updated.is_active,
            "message": "Đã vô hiệu hóa tài khoản thành công",
        }

    async def reactivate_account(self, user_id: int) -> Dict[str, Any]:
        """
        Kích hoạt lại tài khoản.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông tin kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kích hoạt lại tài khoản
        updated = await self.user_repo.reactivate_user(user_id)

        return {
            "user_id": updated.id,
            "is_active": updated.is_active,
            "message": "Đã kích hoạt lại tài khoản thành công",
        }

    async def check_premium_status(self, user_id: int) -> Dict[str, Any]:
        """
        Kiểm tra trạng thái premium của người dùng.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông tin trạng thái premium

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        premium_days_left = 0
        if user.is_premium and user.premium_until:
            delta = user.premium_until - datetime.now()
            premium_days_left = max(0, delta.days)

        return {
            "user_id": user.id,
            "is_premium": user.is_premium,
            "premium_until": user.premium_until,
            "days_left": premium_days_left,
        }

    async def set_premium_status(
        self, user_id: int, is_premium: bool, premium_until: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Thiết lập trạng thái premium cho người dùng.

        Args:
            user_id: ID của người dùng
            is_premium: Trạng thái premium
            premium_until: Thời gian hết hạn premium

        Returns:
            Thông tin trạng thái premium đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        updated = await self.user_repo.set_premium_status(
            user_id, is_premium, premium_until
        )

        premium_days_left = 0
        if updated.is_premium and updated.premium_until:
            delta = updated.premium_until - datetime.now()
            premium_days_left = max(0, delta.days)

        return {
            "user_id": updated.id,
            "is_premium": updated.is_premium,
            "premium_until": updated.premium_until,
            "days_left": premium_days_left,
        }

    async def get_premium_users(self, skip: int = 0, limit: int = 20) -> Dict[str, Any]:
        """
        Lấy danh sách người dùng premium.

        Args:
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách người dùng premium và thông tin phân trang
        """
        users = await self.user_repo.list_premium_users(skip, limit)
        total = await self.user_repo.count_premium_users()

        return {
            "items": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "display_name": user.display_name,
                    "avatar": user.avatar_url,
                    "premium_until": user.premium_until,
                }
                for user in users
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def resend_verification_email(self, user_id: int) -> Dict[str, Any]:
        """
        Gửi lại email xác thực.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông tin token xác thực

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu người dùng đã xác thực
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra người dùng đã xác thực chưa
        if user.is_verified:
            raise BadRequestException(detail="Người dùng đã xác thực email")

        # Tạo token xác thực mới
        token = str(uuid.uuid4())

        # Lưu token
        updated = await self.user_repo.set_verification_token(user_id, token)

        return {
            "user_id": updated.id,
            "email": updated.email,
            "verification_token": updated.verification_token,
        }

    async def check_if_username_exists(self, username: str) -> bool:
        """
        Kiểm tra xem username đã tồn tại chưa.

        Args:
            username: Username cần kiểm tra

        Returns:
            True nếu username đã tồn tại, False nếu chưa
        """
        user = await self.user_repo.get_by_username(username)
        return user is not None

    async def check_if_email_exists(self, email: str) -> bool:
        """
        Kiểm tra xem email đã tồn tại chưa.

        Args:
            email: Email cần kiểm tra

        Returns:
            True nếu email đã tồn tại, False nếu chưa
        """
        user = await self.user_repo.get_by_email(email)
        return user is not None
