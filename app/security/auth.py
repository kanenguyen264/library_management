from typing import Dict, List, Optional, Union, Any, Tuple
import time
import uuid
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, EmailStr, SecretStr, validator

from app.core.db import get_session, async_session
from app.security.password import (
    verify_password,
    get_password_hash,
    check_password_strength,
)
from app.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.security.oauth2 import oauth2_manager, OAuthUserInfo
from app.core.config import get_settings
from app.logging.setup import get_logger
from app.security.audit.audit_trails import log_auth_success, log_auth_failure
from app.monitoring.metrics import track_auth_request

settings = get_settings()
logger = get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class LoginInput(BaseModel):
    """Dữ liệu đầu vào đăng nhập."""

    username: str
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    """Phản hồi token sau khi đăng nhập."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class RegisterInput(BaseModel):
    """Dữ liệu đầu vào đăng ký."""

    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @validator("password")
    def password_strength(cls, v):
        """Kiểm tra độ mạnh mật khẩu."""
        is_strong, reason = check_password_strength(v)
        if not is_strong:
            raise ValueError(reason)
        return v


class AuthManager:
    """
    Quản lý xác thực cho hệ thống.
    Hỗ trợ đăng nhập/đăng ký cơ bản và OAuth2.
    """

    def __init__(self):
        """Khởi tạo AuthManager."""
        # Thử lấy rate limiter nếu có sẵn
        try:
            from app.security.ddos.rate_limiter import AdvancedRateLimiter

            self.rate_limiter = True
        except ImportError:
            self.rate_limiter = False

        # Khởi tạo bộ đếm login attempts
        self.failed_attempts = {}
        self.lockout_until = {}
        self.max_attempts = settings.MAX_LOGIN_ATTEMPTS
        self.lockout_duration = settings.LOGIN_LOCKOUT_DURATION

    async def authenticate_user(
        self,
        db: Session,
        username: str,
        password: str,
        ip_address: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Xác thực người dùng bằng username/password.

        Args:
            db: Database session
            username: Tên đăng nhập hoặc email
            password: Mật khẩu
            ip_address: Địa chỉ IP của người dùng
            user_agent: User agent của người dùng

        Returns:
            Tuple (success, user_or_none, error_message)
        """
        # Kiểm tra lockout
        if self._is_locked_out(username, ip_address):
            wait_time = int((self.lockout_until.get(username, 0) - time.time()) / 60)
            error_message = f"Tài khoản bị tạm khóa do đăng nhập sai nhiều lần. Vui lòng thử lại sau {wait_time} phút."
            log_auth_failure(username, ip_address, "account_locked", user_agent)
            return False, None, error_message

        # Tìm user theo username/email
        from app.user_site.models.user import User

        if "@" in username:
            user = db.query(User).filter(User.email == username.lower()).first()
        else:
            user = db.query(User).filter(User.username == username).first()

        # Nếu không tìm thấy user
        if not user:
            self._record_failed_attempt(username, ip_address)
            log_auth_failure(username, ip_address, "user_not_found", user_agent)
            return False, None, "Tên đăng nhập hoặc mật khẩu không đúng."

        # Kiểm tra trạng thái tài khoản
        if not user.is_active:
            log_auth_failure(username, ip_address, "account_inactive", user_agent)
            return False, None, "Tài khoản đã bị vô hiệu hóa."

        # Xác minh mật khẩu
        if not verify_password(password, user.password_hash):
            self._record_failed_attempt(username, ip_address)
            log_auth_failure(
                username,
                ip_address,
                "invalid_password",
                user_agent,
                details={"user_id": str(user.id)},
            )
            return False, None, "Tên đăng nhập hoặc mật khẩu không đúng."

        # Đăng nhập thành công, reset failed attempts
        self._reset_failed_attempts(username, ip_address)

        # Ghi log thành công
        log_auth_success(
            user_id=str(user.id),
            user_type="user",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Theo dõi metric
        track_auth_request(user.id, True)

        return True, user, None

    def _record_failed_attempt(self, username: str, ip_address: str) -> None:
        """
        Ghi nhận đăng nhập thất bại và khóa tài khoản nếu cần.

        Args:
            username: Tên đăng nhập
            ip_address: Địa chỉ IP
        """
        # Tạo key kết hợp username+IP để phòng tấn công
        key = f"{username}:{ip_address}"

        # Tăng số lần thất bại
        if key in self.failed_attempts:
            self.failed_attempts[key] += 1
        else:
            self.failed_attempts[key] = 1

        # Kiểm tra có cần khóa không
        attempts = self.failed_attempts[key]
        if attempts >= self.max_attempts:
            # Khóa tài khoản
            lockout_time = time.time() + (self.lockout_duration * 60)
            self.lockout_until[username] = lockout_time
            logger.warning(
                f"Tài khoản {username} bị khóa tạm thời do đăng nhập sai {attempts} lần từ IP {ip_address}"
            )

    def _is_locked_out(self, username: str, ip_address: str) -> bool:
        """
        Kiểm tra tài khoản có bị khóa không.

        Args:
            username: Tên đăng nhập
            ip_address: Địa chỉ IP

        Returns:
            True nếu bị khóa
        """
        # Kiểm tra thời gian khóa
        lockout_until = self.lockout_until.get(username, 0)
        if lockout_until > time.time():
            return True

        # Nếu đã hết thời gian khóa, reset
        if username in self.lockout_until:
            del self.lockout_until[username]

        return False

    def _reset_failed_attempts(self, username: str, ip_address: str) -> None:
        """
        Reset số lần đăng nhập thất bại.

        Args:
            username: Tên đăng nhập
            ip_address: Địa chỉ IP
        """
        key = f"{username}:{ip_address}"
        if key in self.failed_attempts:
            del self.failed_attempts[key]

    async def create_tokens(
        self,
        user_id: Union[str, int],
        scopes: List[str] = None,
        remember_me: bool = False,
    ) -> TokenResponse:
        """
        Tạo access token và refresh token.

        Args:
            user_id: ID người dùng
            scopes: Danh sách scopes
            remember_me: Tạo token dài hạn

        Returns:
            TokenResponse với tokens
        """
        # Xác định thời hạn token
        if remember_me:
            access_expire = settings.EXTENDED_ACCESS_TOKEN_EXPIRE_MINUTES
            refresh_expire = settings.EXTENDED_REFRESH_TOKEN_EXPIRE_MINUTES
        else:
            access_expire = settings.ACCESS_TOKEN_EXPIRE_MINUTES
            refresh_expire = settings.REFRESH_TOKEN_EXPIRE_MINUTES

        # Tạo access token
        access_token = create_access_token(
            subject=user_id,
            expires_delta=timedelta(minutes=access_expire),
            scopes=scopes or ["user"],
        )

        # Tạo refresh token
        refresh_token = create_refresh_token(
            subject=user_id, expires_delta=timedelta(minutes=refresh_expire)
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=access_expire * 60,  # Đổi phút thành giây
        )

    async def register_user(
        self,
        db: Session,
        user_data: RegisterInput,
        ip_address: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Đăng ký người dùng mới.

        Args:
            db: Database session
            user_data: Dữ liệu đăng ký
            ip_address: Địa chỉ IP
            user_agent: User agent

        Returns:
            Tuple (success, user_or_none, error_message)
        """
        try:
            # Kiểm tra username đã tồn tại chưa
            from app.user_site.models.user import User

            existing_user = (
                db.query(User)
                .filter(
                    (User.username == user_data.username)
                    | (User.email == user_data.email.lower())
                )
                .first()
            )

            if existing_user:
                if existing_user.username == user_data.username:
                    return False, None, "Tên đăng nhập đã được sử dụng."
                else:
                    return False, None, "Email đã được sử dụng."

            # Tạo user mới
            user = User(
                username=user_data.username,
                email=user_data.email.lower(),
                password_hash=get_password_hash(user_data.password),
                full_name=user_data.full_name,
                is_active=True,
                created_at=datetime.utcnow(),
                registration_ip=ip_address,
            )

            db.add(user)
            db.commit()
            db.refresh(user)

            # Ghi log
            log_auth_success(
                user_id=str(user.id),
                user_type="user",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"action": "register"},
            )

            # Theo dõi metric
            track_auth_request(user.id, True)

            return True, user, None

        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi đăng ký người dùng: {str(e)}")
            return False, None, f"Lỗi khi đăng ký: {str(e)}"

    async def register_oauth_user(
        self,
        db: Session,
        oauth_info: OAuthUserInfo,
        ip_address: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Đăng ký hoặc liên kết người dùng OAuth.

        Args:
            db: Database session
            oauth_info: Thông tin từ OAuth provider
            ip_address: Địa chỉ IP
            user_agent: User agent

        Returns:
            Tuple (success, user_or_none, error_message)
        """
        from app.user_site.models.user import User
        from app.user_site.models.oauth_link import OAuthLink

        try:
            # Kiểm tra OAuth link đã tồn tại chưa
            oauth_link = (
                db.query(OAuthLink)
                .filter(
                    OAuthLink.provider == oauth_info.provider,
                    OAuthLink.provider_user_id == oauth_info.provider_user_id,
                )
                .first()
            )

            if oauth_link:
                # Đã liên kết, lấy user
                user = db.query(User).filter(User.id == oauth_link.user_id).first()

                if not user:
                    return False, None, "Tài khoản liên kết không tồn tại."

                if not user.is_active:
                    return False, None, "Tài khoản đã bị vô hiệu hóa."

                # Cập nhật thông tin nếu cần
                oauth_link.last_login_at = datetime.utcnow()
                oauth_link.last_login_ip = ip_address
                db.commit()

                # Ghi log
                log_auth_success(
                    user_id=str(user.id),
                    user_type="user",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"provider": oauth_info.provider},
                )

                # Theo dõi metric
                track_auth_request(user.id, True, oauth_info.provider)

                return True, user, None

            # Tìm user bằng email nếu có
            user = None
            if oauth_info.email:
                user = (
                    db.query(User)
                    .filter(User.email == oauth_info.email.lower())
                    .first()
                )

            if user:
                # Liên kết với tài khoản hiện có
                oauth_link = OAuthLink(
                    user_id=user.id,
                    provider=oauth_info.provider,
                    provider_user_id=oauth_info.provider_user_id,
                    email=oauth_info.email,
                    name=oauth_info.name,
                    picture=oauth_info.picture,
                    created_at=datetime.utcnow(),
                    last_login_at=datetime.utcnow(),
                    last_login_ip=ip_address,
                )

                db.add(oauth_link)
                db.commit()

                # Ghi log
                log_auth_success(
                    user_id=str(user.id),
                    user_type="user",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"provider": oauth_info.provider, "action": "link"},
                )

                return True, user, None

            # Tạo user mới
            username = self._generate_username_from_oauth(oauth_info)
            random_password = str(uuid.uuid4())

            user = User(
                username=username,
                email=oauth_info.email.lower() if oauth_info.email else None,
                password_hash=get_password_hash(random_password),
                full_name=oauth_info.name,
                avatar_url=oauth_info.picture,
                is_active=True,
                created_at=datetime.utcnow(),
                registration_ip=ip_address,
                is_oauth_user=True,
            )

            db.add(user)
            db.flush()  # Lấy ID nhưng chưa commit

            # Tạo OAuth link
            oauth_link = OAuthLink(
                user_id=user.id,
                provider=oauth_info.provider,
                provider_user_id=oauth_info.provider_user_id,
                email=oauth_info.email,
                name=oauth_info.name,
                picture=oauth_info.picture,
                created_at=datetime.utcnow(),
                last_login_at=datetime.utcnow(),
                last_login_ip=ip_address,
            )

            db.add(oauth_link)
            db.commit()
            db.refresh(user)

            # Ghi log
            log_auth_success(
                user_id=str(user.id),
                user_type="user",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"provider": oauth_info.provider, "action": "register"},
            )

            # Theo dõi metric
            track_auth_request(user.id, True, oauth_info.provider)

            return True, user, None

        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi đăng ký/liên kết OAuth: {str(e)}")
            return False, None, f"Lỗi khi xử lý đăng nhập OAuth: {str(e)}"

    def _generate_username_from_oauth(self, oauth_info: OAuthUserInfo) -> str:
        """
        Tạo username từ thông tin OAuth.

        Args:
            oauth_info: Thông tin OAuth

        Returns:
            Username duy nhất
        """
        import re

        # Tạo base username từ email hoặc name
        if oauth_info.email:
            base_name = oauth_info.email.split("@")[0]
        elif oauth_info.name:
            # Chuyển tên thành slug
            base_name = re.sub(r"[^\w]", "", oauth_info.name.lower())
        else:
            # Fallback nếu không có cả hai
            base_name = f"{oauth_info.provider}_user"

        # Thêm một số ngẫu nhiên để tránh trùng lặp
        import random

        random_suffix = "".join(str(random.randint(0, 9)) for _ in range(6))

        return f"{base_name}_{random_suffix}"


# Tạo singleton instance
auth_manager = AuthManager()


# Các hàm dependency cho FastAPI
async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_session)
):
    """
    Lấy current user từ token.

    Args:
        token: JWT token
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: Nếu token không hợp lệ hoặc user không tồn tại
    """
    try:
        from app.core.exceptions import TokenExpired, InvalidToken

        try:
            payload = decode_token(token)
        except TokenExpired:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token đã hết hạn",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except InvalidToken:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không hợp lệ",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không chứa thông tin người dùng",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Kiểm tra scopes
        scopes = payload.get("scopes", [])

        # Nếu có scope admin, lấy admin user
        if "admin" in scopes:
            from app.admin_site.models.admin import Admin

            user = db.query(Admin).filter(Admin.id == user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Admin không tồn tại",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        else:
            # Lấy user thường
            from app.user_site.models.user import User

            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Người dùng không tồn tại",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        return user

    except Exception as e:
        logger.error(f"Lỗi khi xác thực token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không thể xác thực",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(current_user=Depends(get_current_user)):
    """
    Kiểm tra user có active không.

    Args:
        current_user: User từ get_current_user

    Returns:
        User nếu active

    Raises:
        HTTPException: Nếu user không active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị vô hiệu hóa"
        )
    return current_user


# Các hàm tiện ích
def get_auth_manager() -> AuthManager:
    """
    Dependency để lấy AuthManager.

    Returns:
        AuthManager instance
    """
    return auth_manager


def get_client_ip(request: Request) -> str:
    """
    Lấy địa chỉ IP của client.

    Args:
        request: FastAPI Request

    Returns:
        Địa chỉ IP
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host or "127.0.0.1"
