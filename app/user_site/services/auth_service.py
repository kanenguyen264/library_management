from typing import Optional, Dict, Any, Tuple, List
import secrets
import jwt
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext
import uuid
import re
import time
import traceback
from fastapi import status

from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.social_profile_repo import SocialProfileRepository
from app.user_site.services.notification_service import NotificationService
from app.user_site.schemas.user import UserCreate
from app.user_site.models.user import User
from app.core.exceptions import (
    AuthenticationException,
    BadRequestException,
    NotFoundException,
    UnauthorizedException,
    RateLimitException,
    ClientException,
    ServerException,
)
from app.core.config import get_settings
from app.logs_manager.services import AuthenticationLogService
from app.logs_manager.schemas.authentication_log import AuthenticationLogCreate
from app.cache import get_cache
from app.cache.keys import create_api_response_key, generate_cache_key
from app.monitoring.metrics import Metrics
from app.security.ddos.rate_limiter import AdvancedRateLimiter
from app.security.password import check_password_strength
from app.security.input_validation.validators import (
    validate_email,
    validate_username,
    ValidationResult,
    validate_password_strength,
)
from app.security.encryption.field_encryption import EncryptedType
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.alerting.alerts import AlertingSystem, AlertSeverity
from app.security.waf.rules import detect_sql_injection, detect_xss
from app.logging.setup import get_logger
from app.logs_manager.services.authentication_log_service import (
    AuthenticationLogService,
    create_authentication_log,  # Import hàm global
)

# Cấu hình mã hóa mật khẩu - tăng rounds cho bảo mật cao hơn
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# Lỗi:
# from app.core.config import settings

# Cách sửa:
settings = get_settings()

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.social_profile_repo = SocialProfileRepository(db)
        self.notification_service = NotificationService(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.alerting = AlertingSystem()
        self.profiler = CodeProfiler(enabled=True)
        self.auth_log_service = AuthenticationLogService()

        # Điền giới hạn đăng nhập thất bại
        self.MAX_LOGIN_ATTEMPTS = 5
        self.LOGIN_LOCKOUT_MINUTES = 15
        self.SECURE_TOKEN_BYTES = 32

    async def check_rate_limit(
        self,
        user_id: int,
        action: str,
        limit: int,
        period: int = 3600,
        ip: Optional[str] = None,
    ) -> Tuple[int, int]:
        """
        Kiểm tra giới hạn tốc độ cho một hành động cụ thể.

        Args:
            user_id: ID của người dùng
            action: Tên hành động cần kiểm tra
            limit: Số lượng request tối đa trong khoảng thời gian
            period: Khoảng thời gian tính bằng giây (mặc định 1 giờ)
            ip: Địa chỉ IP của người dùng (tùy chọn)

        Returns:
            Tuple[int, int]: (số lần request hiện tại, thời gian reset giới hạn)
        """
        now = int(time.time())
        window = now // period * period  # Tính toán cửa sổ hiện tại
        reset_time = window + period  # Thời gian reset là đầu cửa sổ tiếp theo

        # Tạo key dựa trên user_id, action và window
        key_parts = [str(user_id), action, str(window)]
        if ip:
            key_parts.append(ip)

        rate_key = f"rate_limit:{':'.join(key_parts)}"

        # Lấy và tăng số lần request
        count = await self.cache.get(rate_key) or 0

        # Tăng counter
        count += 1

        # Thiết lập TTL cho key (thời gian còn lại của cửa sổ hiện tại)
        ttl = reset_time - now
        await self.cache.set(rate_key, count, ttl=ttl)

        # Trả về số lần request hiện tại và thời gian reset
        return count, reset_time

    async def _check_login_attempts(
        self, username_or_email: str, ip_address: str
    ) -> None:
        """
        Kiểm tra số lần đăng nhập thất bại để phòng chống brute force.

        Args:
            username_or_email: Tên đăng nhập hoặc email
            ip_address: Địa chỉ IP của người dùng

        Raises:
            RateLimitException: Nếu vượt quá số lần đăng nhập thất bại cho phép
        """
        cache_key = f"login_attempts:{username_or_email}:{ip_address}"
        attempts = await self.cache.get(cache_key) or 0

        if attempts >= self.MAX_LOGIN_ATTEMPTS:
            # Track đăng nhập bị khóa
            self.metrics.track_security_event(
                "account_lockout",
                "medium",
                {"username_or_email": username_or_email, "ip_address": ip_address},
            )

            # Gửi cảnh báo nếu có dấu hiệu tấn công
            await self.alerting.send_alert(
                title="Phát hiện tấn công brute force",
                message=f"Phát hiện brute force từ IP {ip_address} vào tài khoản {username_or_email}",
                severity=AlertSeverity.WARNING,
                tags=["security", "brute_force"],
                rate_limit_key=f"auth_alert:{ip_address}",
            )

            # Phòng chống tấn công timing: Vẫn xác minh mật khẩu để tránh timing attack
            retry_after = self.LOGIN_LOCKOUT_MINUTES * 60
            raise RateLimitException(
                detail=f"Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau {self.LOGIN_LOCKOUT_MINUTES} phút.",
                retry_after=retry_after,
            )

    async def _record_failed_attempt(
        self, username_or_email: str, ip_address: str
    ) -> None:
        """
        Ghi nhận lần đăng nhập thất bại.

        Args:
            username_or_email: Tên đăng nhập hoặc email
            ip_address: Địa chỉ IP của người dùng
        """
        cache_key = f"login_attempts:{username_or_email}:{ip_address}"
        attempts = await self.cache.get(cache_key) or 0
        attempts += 1

        # Thiết lập thời gian lockout
        ttl = self.LOGIN_LOCKOUT_MINUTES * 60
        await self.cache.set(cache_key, attempts, ttl=ttl)

    async def _reset_login_attempts(
        self, username_or_email: str, ip_address: str
    ) -> None:
        """
        Đặt lại bộ đếm đăng nhập thất bại sau khi đăng nhập thành công.

        Args:
            username_or_email: Tên đăng nhập hoặc email
            ip_address: Địa chỉ IP của người dùng
        """
        cache_key = f"login_attempts:{username_or_email}:{ip_address}"
        await self.cache.delete(cache_key)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Xác thực mật khẩu với protection chống timing attacks.

        Args:
            plain_password: Mật khẩu dạng text
            hashed_password: Mật khẩu đã hash

        Returns:
            True nếu mật khẩu khớp, ngược lại False
        """
        # Sử dụng constant-time comparison để chống timing attacks
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """
        Tạo hash cho mật khẩu.

        Args:
            password: Mật khẩu dạng text

        Returns:
            Chuỗi hash của mật khẩu
        """
        # Tạo salt ngẫu nhiên và hash
        return pwd_context.hash(password)

    def create_access_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Tạo JWT token với dấu thời gian và ID ngẫu nhiên.

        Args:
            data: Dữ liệu sẽ mã hóa trong token
            expires_delta: Thời gian hết hạn (tùy chọn)

        Returns:
            JWT token
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )

        # Thêm các thông tin bảo mật
        to_encode.update(
            {
                "exp": expire,
                "iat": datetime.now(timezone.utc),  # Thời điểm phát hành
                "jti": str(uuid.uuid4()),  # Unique token ID để tránh replay attacks
            }
        )

        # Track token creation
        self.metrics.track_token_validation("created")

        encoded_jwt = jwt.encode(
            to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """
        Tạo refresh token với độ an toàn cao.

        Args:
            data: Dữ liệu sẽ mã hóa trong token

        Returns:
            JWT refresh token
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        # Thêm các thông tin bảo mật
        to_encode.update(
            {
                "exp": expire,
                "iat": datetime.now(timezone.utc),
                "jti": str(uuid.uuid4()),  # Unique token ID
                "token_type": "refresh",
            }
        )

        # Sử dụng cùng secret key cho cả access và refresh token
        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        return encoded_jwt

    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Giải mã JWT token với xử lý lỗi cụ thể.

        Args:
            token: JWT token cần giải mã

        Returns:
            Dữ liệu đã giải mã

        Raises:
            AuthenticationException: Nếu token không hợp lệ hoặc đã hết hạn
        """
        try:
            # Verify và decode token
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )

            # Track token validation
            self.metrics.track_token_validation("valid")

            return payload
        except jwt.ExpiredSignatureError:
            self.metrics.track_token_validation("expired")
            raise AuthenticationException(detail="Token đã hết hạn")
        except jwt.InvalidTokenError:
            self.metrics.track_token_validation("invalid")
            raise AuthenticationException(detail="Token không hợp lệ")

    def decode_refresh_token(self, token: str) -> Dict[str, Any]:
        """
        Giải mã refresh token với xử lý lỗi cụ thể.

        Args:
            token: Refresh token cần giải mã

        Returns:
            Dữ liệu đã giải mã

        Raises:
            AuthenticationException: Nếu token không hợp lệ hoặc đã hết hạn
        """
        try:
            # Verify và decode refresh token
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )

            # Kiểm tra loại token
            if payload.get("token_type") != "refresh":
                self.metrics.track_token_validation("invalid_type")
                raise AuthenticationException(
                    detail="Token không hợp lệ - sai loại token"
                )

            # Track token validation
            self.metrics.track_token_validation("valid_refresh")

            return payload
        except jwt.ExpiredSignatureError:
            self.metrics.track_token_validation("expired_refresh")
            raise AuthenticationException(detail="Refresh token đã hết hạn")
        except jwt.InvalidTokenError:
            self.metrics.track_token_validation("invalid_refresh")
            raise AuthenticationException(detail="Refresh token không hợp lệ")

    async def authenticate_user(
        self,
        username_or_email: str,
        password: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Tuple[Dict[str, Any], str, str]:
        """
        Xác thực người dùng và tạo token với hỗ trợ rate limit và monitoring.

        Args:
            username_or_email: Tên đăng nhập hoặc email
            password: Mật khẩu
            ip_address: Địa chỉ IP của người dùng
            user_agent: User agent của người dùng

        Returns:
            Thông tin người dùng và access token, refresh token

        Raises:
            AuthenticationException: Nếu xác thực thất bại
            RateLimitException: Nếu vượt quá số lần đăng nhập thất bại cho phép
        """
        # Rate limiter cho API đăng nhập - chung cho tất cả requests
        key = f"login_api:{ip_address}"
        count = await self.cache.get(key) or 0
        if count >= 20:  # Giới hạn 20 lần đăng nhập/phút
            retry_after = 60  # 1 phút
            raise RateLimitException(
                detail="Quá nhiều lần đăng nhập từ IP của bạn. Vui lòng thử lại sau.",
                retry_after=retry_after,
            )

        # Tăng counter và set TTL
        await self.cache.set(key, count + 1, ttl=60)

        # Kiểm tra số lần đăng nhập thất bại cho user + ip cụ thể
        await self._check_login_attempts(username_or_email, ip_address)

        # Tracking metrics và performance
        with self.metrics.time_request("POST", "/auth/login"):
            # Sử dụng profiler.profile_time như một decorator thay vì context manager
            start_time = time.time()
            try:
                # Kiểm tra đầu vào là email hay username
                is_email = "@" in username_or_email

                if is_email:
                    user = await self.user_repo.get_by_email(username_or_email)
                else:
                    user = await self.user_repo.get_by_username(username_or_email)

                if not user:
                    # Log authentication failure
                    try:
                        await create_authentication_log(
                            self.db,
                            AuthenticationLogCreate(
                                user_id=None,
                                event_type="authentication_failure",
                                status="failed",
                                ip_address=ip_address,
                                user_agent=user_agent,
                                details={
                                    "reason": "user_not_found",
                                    "username_or_email": username_or_email,
                                },
                            ),
                            raise_exception=False,  # Không ném ngoại lệ nếu lỗi
                        )
                    except Exception as e:
                        # Chỉ ghi log lỗi, không dừng quy trình xác thực
                        logger.error(f"Failed to create authentication log: {str(e)}")

                    # Ghi nhận lần đăng nhập thất bại
                    await self._record_failed_attempt(username_or_email, ip_address)

                    # Track failed login
                    self.metrics.track_login(success=False, reason="user_not_found")

                    # Phòng chống timing attack - thêm một độ trễ nhỏ ngẫu nhiên
                    await self._simulate_password_check_time()

                    raise AuthenticationException(
                        detail="Tên đăng nhập/email hoặc mật khẩu không chính xác"
                    )

                if not user.is_active:
                    # Log authentication failure - inactive account
                    try:
                        await create_authentication_log(
                            self.db,
                            AuthenticationLogCreate(
                                user_id=user.id,
                                event_type="authentication_failure",
                                status="failed",
                                ip_address=ip_address,
                                user_agent=user_agent,
                                details={
                                    "reason": "account_inactive",
                                    "username_or_email": username_or_email,
                                },
                            ),
                            raise_exception=False,  # Không ném ngoại lệ nếu lỗi
                        )
                    except Exception as e:
                        # Chỉ ghi log lỗi, không dừng quy trình xác thực
                        logger.error(f"Failed to create authentication log: {str(e)}")

                    # Ghi nhận lần đăng nhập thất bại
                    await self._record_failed_attempt(username_or_email, ip_address)

                    # Track failed login
                    self.metrics.track_login(success=False, reason="account_inactive")

                    raise AuthenticationException(detail="Tài khoản đã bị vô hiệu hóa")

                # Kiểm tra mật khẩu
                if not self.verify_password(password, user.password_hash):
                    # Log authentication failure - wrong password
                    try:
                        await create_authentication_log(
                            self.db,
                            AuthenticationLogCreate(
                                user_id=user.id,
                                event_type="authentication_failure",
                                status="failed",
                                ip_address=ip_address,
                                user_agent=user_agent,
                                details={
                                    "reason": "invalid_password",
                                    "username_or_email": username_or_email,
                                },
                            ),
                            raise_exception=False,  # Không ném ngoại lệ nếu lỗi
                        )
                    except Exception as e:
                        # Chỉ ghi log lỗi, không dừng quy trình xác thực
                        logger.error(f"Failed to create authentication log: {str(e)}")

                    # Ghi nhận lần đăng nhập thất bại
                    await self._record_failed_attempt(username_or_email, ip_address)

                    # Phát hiện mật khẩu yếu và gửi thông báo nếu cần
                    if (
                        hasattr(user, "password_strength")
                        and user.password_strength == "weak"
                    ):
                        await self.notification_service.create_notification(
                            user_id=user.id,
                            type="SECURITY",
                            title="Cảnh báo bảo mật",
                            message="Mật khẩu của bạn yếu và dễ bị tấn công. Vui lòng đổi mật khẩu mạnh hơn.",
                        )

                    # Track failed login
                    self.metrics.track_login(success=False, reason="invalid_password")

                    raise AuthenticationException(
                        detail="Tên đăng nhập/email hoặc mật khẩu không chính xác"
                    )

                # Đăng nhập thành công - reset bộ đếm đăng nhập thất bại
                await self._reset_login_attempts(username_or_email, ip_address)

                # Log successful authentication
                try:
                    await create_authentication_log(
                        self.db,
                        AuthenticationLogCreate(
                            user_id=user.id,
                            event_type="authentication_success",
                            status="success",
                            ip_address=ip_address,
                            user_agent=user_agent,
                            details={"username_or_email": username_or_email},
                        ),
                        raise_exception=False,  # Không ném ngoại lệ nếu lỗi
                    )
                except Exception as e:
                    # Chỉ ghi log lỗi, không dừng quy trình xác thực
                    logger.error(f"Failed to create authentication log: {str(e)}")

                # Track successful login
                self.metrics.track_login(success=True)

                # Cập nhật thời gian đăng nhập cuối
                await self.user_repo.update_last_login(user.id)

                # Tạo access token và refresh token
                access_token_data = {
                    "sub": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "is_admin": False,
                    "is_premium": user.is_premium,
                    "ip": ip_address,  # Thêm IP cho security tracking
                }

                refresh_token_data = {"sub": str(user.id), "token_type": "refresh"}

                access_token = self.create_access_token(access_token_data)
                refresh_token = self.create_refresh_token(refresh_token_data)

                # Lưu thông tin phiên người dùng vào cache để có thể vô hiệu hóa khi cần thiết
                session_data = {
                    "user_id": user.id,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                # Cấu trúc key cho tracking session
                session_key = f"user_session:{user.id}:{access_token[-10:]}"
                await self.cache.set(
                    session_key,
                    session_data,
                    ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                )

                return self._get_user_response(user), access_token, refresh_token
            finally:
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
                logger.info(f"authenticate_user completed in {duration_ms:.2f}ms")

    async def _simulate_password_check_time(self):
        """
        Mô phỏng thời gian kiểm tra mật khẩu để phòng chống timing attacks.
        """
        # Thêm độ trễ ngẫu nhiên tương đương thời gian verify hash
        import random

        time.sleep(0.1 + random.random() * 0.1)  # 100-200ms delay

    async def refresh_tokens(
        self,
        refresh_token: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Tuple[Dict[str, Any], str, str]:
        """
        Làm mới token từ refresh token với kiểm soát bảo mật.

        Args:
            refresh_token: Refresh token
            ip_address: Địa chỉ IP của người dùng
            user_agent: User agent của người dùng

        Returns:
            Thông tin người dùng và access token, refresh token mới

        Raises:
            AuthenticationException: Nếu refresh token không hợp lệ hoặc đã hết hạn
            RateLimitException: Nếu vượt quá tần suất làm mới token
        """
        # Rate limit cho refresh token để tránh abuse
        key = f"token_refresh:{ip_address}"
        count = await self.cache.get(key) or 0
        if count >= 30:  # Giới hạn 30 lần refresh/phút
            retry_after = 60  # 1 phút
            raise RateLimitException(
                detail="Quá nhiều lần làm mới token. Vui lòng thử lại sau.",
                retry_after=retry_after,
            )

        # Tăng counter và set TTL
        await self.cache.set(key, count + 1, ttl=60)

        with self.metrics.time_request("POST", "/auth/refresh"):
            # Giải mã refresh token
            try:
                payload = self.decode_refresh_token(refresh_token)
            except AuthenticationException as e:
                # Track refresh token failure
                self.metrics.track_token_validation("refresh_failed")

                # Log authentication failure
                await create_authentication_log(
                    self.db,
                    AuthenticationLogCreate(
                        user_id=None,
                        event_type="authentication_failure",
                        status="failed",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        details={
                            "reason": str(e),
                            "action": "refresh_token",  # Chuyển action vào details
                        },
                    ),
                )

                # Kiểm tra dấu hiệu tấn công
                token_key = f"failed_refresh:{ip_address}"
                failed_count = await self.cache.get(token_key) or 0
                await self.cache.set(token_key, failed_count + 1, ttl=3600)

                if failed_count > 5:
                    # Gửi cảnh báo có dấu hiệu tấn công
                    await self.alerting.send_alert(
                        title="Phát hiện tấn công refresh token",
                        message=f"Nhiều lần refresh token thất bại từ IP {ip_address}",
                        severity=AlertSeverity.WARNING,
                        tags=["security", "token_attack"],
                    )

                raise

            # Lấy thông tin người dùng
            user_id = int(payload.get("sub"))

            # Kiểm tra token trong danh sách blacklist
            blacklist_key = f"token_blacklist:{refresh_token[-10:]}"
            if await self.cache.exists(blacklist_key):
                self.metrics.track_token_validation("blacklisted")
                raise AuthenticationException(detail="Token đã bị vô hiệu hóa")

            user = await self.user_repo.get_by_id(user_id)

            if not user or not user.is_active:
                self.metrics.track_token_validation("user_invalid")
                raise AuthenticationException(
                    detail="Người dùng không tồn tại hoặc đã bị vô hiệu hóa"
                )

            # Tạo access token và refresh token mới
            access_token_data = {
                "sub": str(user.id),
                "username": user.username,
                "email": user.email,
                "is_admin": False,
                "is_premium": user.is_premium,
                "ip": ip_address,  # Thêm IP cho security tracking
            }

            refresh_token_data = {"sub": str(user.id), "token_type": "refresh"}

            access_token = self.create_access_token(access_token_data)
            new_refresh_token = self.create_refresh_token(refresh_token_data)

            # Thêm token cũ vào blacklist để tránh reuse
            await self.cache.set(
                blacklist_key, user_id, ttl=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
            )

            # Cập nhật last_active
            await self.user_repo.update_last_active(user.id)

            # Log successful token refresh
            await create_authentication_log(
                self.db,
                AuthenticationLogCreate(
                    user_id=user.id,
                    event_type="authentication_success",
                    status="success",
                    ip_address=ip_address,
                    user_agent=user_agent,
                ),
            )

            # Lưu phiên mới vào cache
            session_data = {
                "user_id": user.id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "refreshed": True,
            }

            session_key = f"user_session:{user.id}:{access_token[-10:]}"
            await self.cache.set(
                session_key, session_data, ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )

            # Track successful token refresh
            self.metrics.track_token_validation("refreshed")

            return self._get_user_response(user), access_token, new_refresh_token

    async def verify_2fa(
        self,
        temp_token: str,
        code: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Tuple[Dict[str, Any], str, str]:
        """
        Xác thực mã hai yếu tố (2FA) và tạo token đăng nhập.

        Args:
            temp_token: Token tạm được cung cấp sau khi đăng nhập
            code: Mã 2FA từ authenticator app
            ip_address: Địa chỉ IP của người dùng
            user_agent: User agent của người dùng

        Returns:
            Thông tin người dùng và access token, refresh token

        Raises:
            UnauthorizedException: Nếu token hoặc mã không hợp lệ
            RateLimitException: Nếu vượt quá số lần thử
        """
        # Rate limit để tránh brute force
        key = f"2fa_verify:{ip_address}"
        count = await self.cache.get(key) or 0
        if count >= 5:  # Giới hạn 5 lần thử/phút
            retry_after = 60  # 1 phút
            raise RateLimitException(
                detail="Quá nhiều lần thử mã xác thực. Vui lòng thử lại sau.",
                retry_after=retry_after,
            )

        # Tăng counter và set TTL
        await self.cache.set(key, count + 1, ttl=60)

        with self.metrics.time_request("POST", "/auth/2fa/verify"):
            # Lấy thông tin từ token tạm thời
            try:
                # Giải mã token tạm thời
                decoded = jwt.decode(
                    temp_token,
                    settings.SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                )

                # Kiểm tra xem token có phải là token 2FA không
                if decoded.get("type") != "2fa_temp":
                    raise UnauthorizedException(detail="Token không hợp lệ")

                user_id = decoded.get("sub")
                if not user_id:
                    raise UnauthorizedException(detail="Token không hợp lệ")

                user = await self.user_repo.get_by_id(int(user_id))
                if not user or not user.is_active:
                    self.metrics.track_token_validation("user_invalid")
                    raise UnauthorizedException(
                        detail="Người dùng không tồn tại hoặc đã bị vô hiệu hóa"
                    )

                # Kiểm tra xem user có bật 2FA không
                if not user.two_factor_enabled or not user.two_factor_secret:
                    raise UnauthorizedException(
                        detail="2FA không được bật cho tài khoản này"
                    )

                # Xác thực mã 2FA
                import pyotp

                totp = pyotp.TOTP(user.two_factor_secret)
                if not totp.verify(code):
                    # Ghi nhận lần xác thực thất bại
                    fail_key = f"2fa_fail:{user.id}"
                    fail_count = await self.cache.get(fail_key) or 0
                    await self.cache.set(fail_key, fail_count + 1, ttl=300)

                    if fail_count >= 3:
                        # Gửi cảnh báo nếu có nhiều lần thất bại
                        await self.alerting.send_alert(
                            title="Phát hiện tấn công 2FA",
                            message=f"Nhiều lần nhập sai mã 2FA cho user {user.id} từ IP {ip_address}",
                            severity=AlertSeverity.WARNING,
                            tags=["security", "2fa"],
                        )

                    # Track failed 2FA
                    self.metrics.track_token_validation("2fa_failed")

                    # Log authentication failure
                    await create_authentication_log(
                        self.db,
                        AuthenticationLogCreate(
                            user_id=user.id,
                            event_type="authentication_failure",
                            status="failed",
                            ip_address=ip_address,
                            user_agent=user_agent,
                            details={"reason": "invalid_code"},
                        ),
                    )

                    raise UnauthorizedException(detail="Mã xác thực không chính xác")

                # Xác thực thành công - reset bộ đếm thất bại
                await self.cache.delete(f"2fa_fail:{user.id}")

                # Tạo token thực sự
                access_token_data = {
                    "sub": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "is_admin": False,
                    "is_premium": user.is_premium,
                    "ip": ip_address,  # Thêm IP cho security tracking
                }

                refresh_token_data = {"sub": str(user.id), "token_type": "refresh"}

                access_token = self.create_access_token(access_token_data)
                refresh_token = self.create_refresh_token(refresh_token_data)

                # Log successful authentication
                await create_authentication_log(
                    self.db,
                    AuthenticationLogCreate(
                        user_id=user.id,
                        event_type="authentication_success",
                        status="success",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ),
                )

                # Track successful 2FA
                self.metrics.track_token_validation("2fa_success")

                return self._get_user_response(user), access_token, refresh_token

            except jwt.ExpiredSignatureError:
                self.metrics.track_token_validation("2fa_token_expired")
                raise UnauthorizedException(detail="Token đã hết hạn")
            except jwt.InvalidTokenError:
                self.metrics.track_token_validation("2fa_token_invalid")
                raise UnauthorizedException(detail="Token không hợp lệ")
            except Exception as e:
                if isinstance(e, UnauthorizedException):
                    raise
                logger.error(f"Lỗi xác thực 2FA: {str(e)}")
                raise ServerException(detail="Lỗi xác thực, vui lòng thử lại sau")

    async def register_user(self, user_data: UserCreate, client_ip: str = None) -> Any:
        """
        Async version of registering a new user.

        Args:
            user_data: User creation data object
            client_ip: IP address of the client

        Returns:
            Created user object

        Raises:
            ValidationError: If the registration data is invalid
            ClientException: If the password is weak or email/username already exists
            ServerException: If there's an error during processing
        """
        try:
            logger.info(f"Registering new user: {user_data.email}")

            # Verify password strength - already done in the auth controller

            # Check if username exists - trực tiếp truy vấn repository, không ném ngoại lệ
            existing_user = await self.user_repo.get_by_username(user_data.username)
            if existing_user:
                logger.warning(f"Username already exists: {user_data.username}")
                raise ClientException(
                    detail=f"Username {user_data.username} is already taken",
                    code="username_exists",
                    status_code=status.HTTP_409_CONFLICT,
                )

            # Check if email exists - trực tiếp truy vấn repository, không ném ngoại lệ
            existing_email = await self.user_repo.get_by_email(user_data.email)
            if existing_email:
                logger.warning(f"Email already exists: {user_data.email}")
                raise ClientException(
                    detail=f"Email {user_data.email} is already registered",
                    code="email_exists",
                    status_code=status.HTTP_409_CONFLICT,
                )

            # Kiểm tra độ mạnh của mật khẩu
            is_valid, reason = validate_password_strength(user_data.password)
            if not is_valid:
                logger.warning(f"Mật khẩu yếu khi đăng ký từ IP {client_ip}: {reason}")
                raise ClientException(
                    detail=reason,
                    code="weak_password",
                    message="Mật khẩu không đủ mạnh, vui lòng chọn mật khẩu khác",
                )

            # Hash the password
            hashed_password = self.get_password_hash(user_data.password)

            # Create the user with default values
            user_create_dict = user_data.dict()
            user_create_dict.pop("password", None)  # Remove plain password
            user_create_dict.pop(
                "password_confirm", None
            )  # Remove password confirmation

            # Ghi log chi tiết dữ liệu đăng ký (đã loại bỏ mật khẩu)
            logger.debug(f"User creation data: {user_create_dict}")

            logger.info(
                f"Creating user with username: {user_data.username}, email: {user_data.email}"
            )
            user = await self.user_repo.create(
                {
                    **user_create_dict,
                    "password_hash": hashed_password,
                    "is_active": True,
                    "is_email_verified": False,
                    "verification_token": secrets.token_urlsafe(32),
                    "verification_expires": datetime.now(timezone.utc)
                    + timedelta(days=3),
                }
            )

            # Create default user settings and preferences here if needed

            # Tạo log đăng ký
            try:
                await create_authentication_log(
                    self.db,
                    AuthenticationLogCreate(
                        user_id=user.id,
                        event_type="user_registration",
                        status="success",
                        is_success=True,
                        ip_address=client_ip,
                        details={"registration_method": "email_password"},
                    ),
                    raise_exception=False,  # Không ném ngoại lệ nếu lỗi
                )
            except Exception as log_error:
                # Ghi nhận lỗi nhưng không dừng quy trình đăng ký
                logger.error(
                    f"Error creating authentication log: {str(log_error)}",
                    exc_info=True,
                )
                # Continue with registration regardless of logging errors

            return user

        except Exception as e:
            if isinstance(e, ClientException):
                raise

            logger.error(f"Error registering user: {str(e)}\n{traceback.format_exc()}")
            raise ServerException(
                detail=f"Error registering account: {str(e)}", code="registration_error"
            )

    @staticmethod
    async def register(
        *, register_data: UserCreate, session: Session, client_ip: str = None
    ) -> User:
        """
        Đăng ký người dùng mới

        Args:
            register_data: Dữ liệu đăng ký người dùng
            session: Session database
            client_ip: Địa chỉ IP của client

        Raises:
            ValidationError: Nếu dữ liệu đăng ký không hợp lệ
            ClientException: Nếu mật khẩu yếu, email/username đã tồn tại
            ServerException: Nếu có lỗi trong quá trình xử lý

        Returns:
            User: Đối tượng User đã tạo
        """
        try:
            logger.info(f"Đăng ký người dùng mới: {register_data.email}")

            # Kiểm tra độ mạnh của mật khẩu
            is_valid, reason = validate_password_strength(register_data.password)
            if not is_valid:
                logger.warning(f"Mật khẩu yếu khi đăng ký từ IP {client_ip}: {reason}")
                raise ClientException(
                    detail=reason,
                    code="weak_password",
                    message="Mật khẩu không đủ mạnh, vui lòng chọn mật khẩu khác",
                )

            # Khởi tạo UserRepository với session
            user_repo = UserRepository(session)

            # Hash the password
            hashed_password = pwd_context.hash(register_data.password)

            # Create a user data dictionary from the registration data
            user_dict = register_data.dict()
            user_dict.pop("password", None)  # Remove plain password
            user_dict.pop("password_confirm", None)  # Remove password confirmation
            user_dict["password_hash"] = hashed_password
            user_dict["is_active"] = True
            user_dict["is_email_verified"] = False
            user_dict["verification_token"] = secrets.token_urlsafe(32)
            user_dict["verification_expires"] = datetime.now(timezone.utc) + timedelta(
                days=3
            )

            # Create the user with the repository
            user = await user_repo.create(user_dict)

            # Tạo log đăng ký
            try:
                await create_authentication_log(
                    session,
                    AuthenticationLogCreate(
                        user_id=user.id,
                        event_type="user_registration",
                        status="success",
                        is_success=True,
                        ip_address=client_ip,
                        details={"registration_method": "email_password"},
                    ),
                    raise_exception=False,  # Không ném ngoại lệ nếu lỗi
                )
            except Exception as log_error:
                # Ghi nhận lỗi nhưng không dừng quy trình đăng ký
                logger.error(
                    f"Error creating authentication log: {str(log_error)}",
                    exc_info=True,
                )
                # Continue with registration regardless of logging errors

            return user

        except IntegrityError as e:
            err_msg = str(e).lower()
            if "email" in err_msg:
                logger.warning(
                    f"Email đã tồn tại khi đăng ký: {register_data.email} từ IP {client_ip}"
                )
                raise ClientException(
                    detail=f"Email {register_data.email} đã được sử dụng",
                    code="email_exists",
                    message="Email đã được sử dụng, vui lòng chọn email khác",
                )
            elif "username" in err_msg:
                logger.warning(
                    f"Username đã tồn tại khi đăng ký: {register_data.username} từ IP {client_ip}"
                )
                raise ClientException(
                    detail=f"Username {register_data.username} đã được sử dụng",
                    code="username_exists",
                    message="Tên đăng nhập đã được sử dụng, vui lòng chọn tên khác",
                )
            else:
                logger.error(f"Lỗi IntegrityError khi đăng ký user: {err_msg}")
                raise ServerException(
                    detail="Lỗi khi đăng ký tài khoản",
                    code="registration_error",
                    message="Có lỗi xảy ra khi đăng ký tài khoản, vui lòng thử lại sau",
                )
        except Exception as e:
            logger.error(
                f"Lỗi không xác định khi đăng ký user: {str(e)}\n{traceback.format_exc()}"
            )
            raise ServerException(
                detail=f"Lỗi khi đăng ký tài khoản: {str(e)}",
                code="registration_error",
                message="Có lỗi xảy ra khi đăng ký tài khoản, vui lòng thử lại sau",
            )

    async def verify_email(self, token: str, ip_address: str = "unknown") -> bool:
        """
        Xác thực email người dùng.

        Args:
            token: Token xác thực
            ip_address: Địa chỉ IP của người dùng

        Returns:
            True nếu xác thực thành công, False nếu thất bại
        """
        # Rate limit để tránh brute force
        key = f"verify_email:{ip_address}"
        count = await self.cache.get(key) or 0
        if count >= 10:  # Giới hạn 10 lần xác thực/5 phút
            retry_after = 300  # 5 phút
            raise RateLimitException(
                detail="Quá nhiều lần xác thực email. Vui lòng thử lại sau.",
                retry_after=retry_after,
            )

        # Tăng counter và set TTL
        await self.cache.set(key, count + 1, ttl=300)

        with self.metrics.time_request("GET", "/auth/verify-email"):
            user = await self.user_repo.get_by_verification_token(token)
            if not user:
                # Track failed verification
                self.metrics.track_user_activity("email_verification_failed")
                raise NotFoundException(
                    detail="Token xác thực không hợp lệ hoặc đã hết hạn"
                )

            # Kiểm tra token đã hết hạn chưa
            if hasattr(user, "verification_expires") and user.verification_expires:
                if user.verification_expires < datetime.now(timezone.utc):
                    self.metrics.track_user_activity("email_verification_expired")
                    raise NotFoundException(detail="Token xác thực đã hết hạn")

            # Xác thực và xóa token
            await self.user_repo.verify_email(user.id)

            # Track successful verification
            self.metrics.track_user_activity("email_verification_success")

            # Thông báo
            await self.notification_service.create_notification(
                user_id=user.id,
                type="ACCOUNT",
                title="Email đã được xác thực",
                message="Cảm ơn bạn đã xác thực email. Bây giờ bạn có thể truy cập đầy đủ các tính năng của hệ thống.",
            )

            return True

    async def request_password_reset(
        self, email: str, ip_address: str = "unknown"
    ) -> bool:
        """
        Yêu cầu đặt lại mật khẩu với bảo vệ chống lạm dụng.

        Args:
            email: Email người dùng
            ip_address: Địa chỉ IP người dùng

        Returns:
            True nếu yêu cầu thành công

        Raises:
            NotFoundException: Nếu không tìm thấy email
            RateLimitException: Nếu vượt quá tần suất yêu cầu
        """
        # Rate limit cho yêu cầu reset mật khẩu
        key = f"password_reset_request:{ip_address}"
        count = await self.cache.get(key) or 0
        if count >= 3:  # Giới hạn 3 lần yêu cầu/giờ
            retry_after = 3600  # 1 giờ
            raise RateLimitException(
                detail="Quá nhiều lần yêu cầu đặt lại mật khẩu. Vui lòng thử lại sau.",
                retry_after=retry_after,
            )

        # Tăng counter và set TTL
        await self.cache.set(key, count + 1, ttl=3600)

        with self.metrics.time_request("POST", "/auth/reset-password-request"):
            # Kiểm tra độ mạnh reset password cho email này
            reset_count_key = f"reset_count:{email}:24h"
            reset_count = await self.cache.get(reset_count_key) or 0

            if reset_count >= 3:
                # Giới hạn 3 lần yêu cầu reset mỗi 24h cho một email
                self.metrics.track_security_event("password_reset_limited", "medium")

                # Để chống leak thông tin và timing attacks, không tiết lộ rằng đã vượt quá giới hạn
                return True

            user = await self.user_repo.get_by_email(email)
            if not user:
                # Để ngăn chặn enumeration attacks, vẫn trả về true ngay cả khi email không tồn tại
                return True

            # Tạo token an toàn và thời gian hết hạn
            reset_token = secrets.token_urlsafe(self.SECURE_TOKEN_BYTES)
            expires = datetime.now(timezone.utc) + timedelta(hours=24)

            # Lưu token với hạn ngắn
            await self.user_repo.set_password_reset_token(user.id, reset_token, expires)

            # Tăng bộ đếm reset password
            await self.cache.increment(reset_count_key, 1, ttl=86400)

            # Track password reset request
            self.metrics.track_user_activity("password_reset_requested")

            # TODO: Gửi email đặt lại mật khẩu

            return True

    async def reset_password(
        self, token: str, new_password: str, ip_address: str = "unknown"
    ) -> bool:
        """
        Đặt lại mật khẩu với kiểm tra độ mạnh mật khẩu.

        Args:
            token: Token đặt lại mật khẩu
            new_password: Mật khẩu mới
            ip_address: Địa chỉ IP người dùng

        Returns:
            True nếu đặt lại thành công

        Raises:
            NotFoundException: Nếu không tìm thấy token hoặc đã hết hạn
            BadRequestException: Nếu mật khẩu mới không đủ mạnh
        """
        # Rate limit cho reset password
        key = f"password_reset:{ip_address}"
        count = await self.cache.get(key) or 0
        if count >= 5:  # Giới hạn 5 lần đặt lại/5 phút
            retry_after = 300  # 5 phút
            raise RateLimitException(
                detail="Quá nhiều lần đặt lại mật khẩu. Vui lòng thử lại sau.",
                retry_after=retry_after,
            )

        # Tăng counter và set TTL
        await self.cache.set(key, count + 1, ttl=300)

        with self.metrics.time_request("POST", "/auth/reset-password"):
            # Kiểm tra độ mạnh mật khẩu mới
            is_strong, password_message = validate_password_strength(new_password)
            if not is_strong:
                self.metrics.track_user_activity("password_reset_weak_password")
                raise BadRequestException(
                    detail=f"Mật khẩu mới quá yếu: {password_message}"
                )

            user = await self.user_repo.get_by_reset_password_token(token)
            if not user:
                # Track failed password reset
                self.metrics.track_user_activity("password_reset_invalid_token")

                # Check for brute-force attempts
                invalid_reset_key = f"invalid_reset:{ip_address}"
                invalid_attempts = await self.cache.get(invalid_reset_key) or 0
                await self.cache.set(invalid_reset_key, invalid_attempts + 1, ttl=3600)

                if invalid_attempts > 5:
                    # Có dấu hiệu brute force token
                    await self.alerting.send_alert(
                        title="Phát hiện brute force reset token",
                        message=f"Phát hiện brute force reset token từ IP {ip_address}",
                        severity=AlertSeverity.WARNING,
                        tags=["security", "brute_force", "password_reset"],
                    )

                raise NotFoundException(detail="Token không hợp lệ hoặc đã hết hạn")

            # Kiểm tra token đã hết hạn chưa
            if (
                user.password_reset_expires
                and user.password_reset_expires < datetime.now(timezone.utc)
            ):
                self.metrics.track_user_activity("password_reset_expired_token")
                raise NotFoundException(detail="Token đặt lại mật khẩu đã hết hạn")

            # Hash mật khẩu mới
            password_hash = self.get_password_hash(new_password)

            # Cập nhật mật khẩu và xóa token
            await self.user_repo.update(
                user.id,
                {
                    "password_hash": password_hash,
                    "password_reset_token": None,
                    "password_reset_at": datetime.now(timezone.utc),
                    "password_reset_expires": None,
                    "password_strength": "strong" if is_strong else "medium",
                },
            )

            # Hủy tất cả các phiên đăng nhập hiện có (yêu cầu đăng nhập lại)
            session_pattern = f"user_session:{user.id}:*"
            await self.cache.clear(pattern=session_pattern)

            # Track successful password reset
            self.metrics.track_user_activity("password_reset_success")

            # Log authentication activity
            await create_authentication_log(
                self.db,
                AuthenticationLogCreate(
                    user_id=user.id,
                    event_type="authentication_success",
                    status="success",
                    ip_address=ip_address,
                    details={"method": "token"},
                ),
            )

            # Thông báo
            await self.notification_service.create_notification(
                user_id=user.id,
                type="SECURITY",
                title="Mật khẩu đã được đặt lại",
                message="Mật khẩu của bạn đã được đặt lại thành công. Nếu không phải bạn thực hiện, vui lòng liên hệ với chúng tôi ngay.",
            )

            return True

    async def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
        ip_address: str = "unknown",
    ) -> bool:
        """
        Đổi mật khẩu với kiểm tra bảo mật cao.

        Args:
            user_id: ID người dùng
            current_password: Mật khẩu hiện tại
            new_password: Mật khẩu mới
            ip_address: Địa chỉ IP người dùng

        Returns:
            True nếu đổi thành công

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            AuthenticationException: Nếu mật khẩu hiện tại không đúng
            BadRequestException: Nếu mật khẩu mới không đủ mạnh
        """
        # Rate limit cho đổi mật khẩu
        key = f"password_change:{ip_address}"
        count = await self.cache.get(key) or 0
        if count >= 3:  # Giới hạn 3 lần đổi/giờ
            retry_after = 3600  # 1 giờ
            raise RateLimitException(
                detail="Quá nhiều lần đổi mật khẩu. Vui lòng thử lại sau.",
                retry_after=retry_after,
            )

        # Tăng counter và set TTL
        await self.cache.set(key, count + 1, ttl=3600)

        with self.metrics.time_request("POST", "/auth/change-password"):
            # Kiểm tra độ mạnh mật khẩu mới
            is_strong, password_message = validate_password_strength(new_password)
            if not is_strong:
                self.metrics.track_user_activity("password_change_weak_password")
                raise BadRequestException(
                    detail=f"Mật khẩu mới quá yếu: {password_message}"
                )

            # Kiểm tra mật khẩu mới không giống mật khẩu cũ
            if current_password == new_password:
                raise BadRequestException(
                    detail="Mật khẩu mới không được giống mật khẩu cũ"
                )

            user = await self.user_repo.get_by_id(user_id)
            if not user:
                self.metrics.track_user_activity("password_change_user_not_found")
                raise NotFoundException(detail="Không tìm thấy người dùng")

            if not self.verify_password(current_password, user.password_hash):
                # Track failed password change
                self.metrics.track_user_activity("password_change_invalid_current")

                # Log authentication failure
                await create_authentication_log(
                    self.db,
                    AuthenticationLogCreate(
                        user_id=user_id,
                        event_type="authentication_failure",
                        status="failed",
                        ip_address=ip_address,
                        details={"reason": "invalid_current_password"},
                    ),
                )

                # Theo dõi số lần thất bại
                password_fail_key = f"password_change_fail:{user_id}"
                fail_count = await self.cache.get(password_fail_key) or 0
                await self.cache.set(password_fail_key, fail_count + 1, ttl=3600)

                if fail_count >= 3:
                    # Gửi thông báo cảnh báo
                    await self.notification_service.create_notification(
                        user_id=user_id,
                        type="SECURITY",
                        title="Cảnh báo bảo mật",
                        message="Có nhiều lần nhập sai mật khẩu hiện tại. Đây có phải là bạn không? Nếu không, tài khoản của bạn có thể đang bị tấn công.",
                    )

                raise AuthenticationException(detail="Mật khẩu hiện tại không đúng")

            # Hash mật khẩu mới
            password_hash = self.get_password_hash(new_password)

            # Cập nhật mật khẩu
            await self.user_repo.update_password(
                user_id,
                password_hash,
                password_strength="strong" if is_strong else "medium",
                changed_at=datetime.now(timezone.utc),
            )

            # Xóa tất cả các phiên khác (ngoại trừ phiên hiện tại)
            session_pattern = f"user_session:{user.id}:*"
            await self.cache.clear(pattern=session_pattern)

            # Xóa bộ đếm thất bại
            await self.cache.delete(f"password_change_fail:{user_id}")

            # Track successful password change
            self.metrics.track_user_activity("password_change_success")

            # Log authentication activity
            await create_authentication_log(
                self.db,
                AuthenticationLogCreate(
                    user_id=user_id,
                    event_type="authentication_success",
                    status="success",
                    ip_address=ip_address,
                ),
            )

            # Thông báo
            await self.notification_service.create_notification(
                user_id=user_id,
                type="SECURITY",
                title="Mật khẩu đã được thay đổi",
                message="Mật khẩu của bạn đã được thay đổi thành công. Nếu không phải bạn thực hiện, vui lòng liên hệ với chúng tôi ngay.",
            )

            return True

    async def social_auth(
        self,
        provider: str,
        token_data: Dict[str, Any],
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Tuple[Dict[str, Any], str, str]:
        """
        Xác thực qua mạng xã hội với bảo mật nâng cao.

        Args:
            provider: Nhà cung cấp (google, facebook, ...)
            token_data: Dữ liệu token và thông tin người dùng
            ip_address: Địa chỉ IP của người dùng
            user_agent: User agent của người dùng

        Returns:
            Thông tin người dùng và access token, refresh token

        Raises:
            BadRequestException: Nếu thiếu thông tin
            RateLimitException: Nếu vượt quá tần suất yêu cầu
        """
        # Rate limit cho social login
        key = f"social_auth:{ip_address}"
        count = await self.cache.get(key) or 0
        if count >= 10:  # Giới hạn 10 lần đăng nhập/phút
            retry_after = 60  # 1 phút
            raise RateLimitException(
                detail="Quá nhiều lần đăng nhập qua mạng xã hội. Vui lòng thử lại sau.",
                retry_after=retry_after,
            )

        # Tăng counter và set TTL
        await self.cache.set(key, count + 1, ttl=60)

        with self.metrics.time_request("POST", f"/auth/{provider}"):
            # Kiểm tra các trường bắt buộc
            required_fields = ["provider_id", "email"]
            for field in required_fields:
                if field not in token_data:
                    raise BadRequestException(detail=f"Thiếu trường {field}")

            # Đảm bảo email là chuỗi
            email = str(token_data["email"])
            provider_id = str(token_data["provider_id"])

            # Validate email format
            email_validation = validate_email(email)
            if not email_validation:
                raise BadRequestException(detail="Email từ nhà cung cấp không hợp lệ")

            # Kiểm tra xem đã có hồ sơ mạng xã hội chưa
            social_profile = await self.social_profile_repo.get_by_provider_id(
                provider, provider_id
            )

            if social_profile:
                # Đã có hồ sơ, lấy thông tin người dùng
                user = await self.user_repo.get_by_id(social_profile.user_id)
                if not user or not user.is_active:
                    # Track failed social auth
                    self.metrics.track_login(success=False, reason="account_inactive")

                    raise AuthenticationException(
                        detail="Tài khoản đã bị vô hiệu hóa hoặc không tồn tại"
                    )

                # Cập nhật thông tin hồ sơ mạng xã hội nếu cần
                update_data = {
                    "access_token": token_data.get("access_token"),
                    "expires_at": token_data.get("expires_at"),
                    "refresh_token": token_data.get("refresh_token"),
                    "last_used_at": datetime.now(timezone.utc),
                    "last_ip": ip_address,
                }

                await self.social_profile_repo.update(social_profile.id, update_data)

                # Kiểm tra xem có cần cập nhật avatar người dùng
                if token_data.get("photo_url") and not user.avatar_url:
                    await self.user_repo.update(
                        user.id, {"avatar_url": token_data.get("photo_url")}
                    )
            else:
                # Chưa có hồ sơ, kiểm tra xem có người dùng với email này chưa
                user = await self.user_repo.get_by_email(email)

                if user:
                    # Đã có người dùng, liên kết với hồ sơ mạng xã hội
                    social_data = {
                        "user_id": user.id,
                        "provider": provider,
                        "provider_id": provider_id,
                        "access_token": token_data.get("access_token"),
                        "refresh_token": token_data.get("refresh_token"),
                        "expires_at": token_data.get("expires_at"),
                        "provider_data": token_data.get("provider_data", {}),
                        "last_used_at": datetime.now(timezone.utc),
                        "last_ip": ip_address,
                    }

                    await self.social_profile_repo.create(social_data)

                    # Cập nhật avatar người dùng nếu cần
                    if token_data.get("photo_url") and not user.avatar_url:
                        await self.user_repo.update(
                            user.id, {"avatar_url": token_data.get("photo_url")}
                        )
                else:
                    # Chưa có người dùng, tạo mới
                    # Generate username từ email hoặc tên
                    display_name = (
                        token_data.get("display_name")
                        or token_data.get("name")
                        or email.split("@")[0]
                    )
                    username = token_data.get("username") or email.split("@")[0]

                    # Đảm bảo username là duy nhất
                    base_username = username
                    suffix = 1
                    while await self.user_repo.get_by_username(username):
                        username = f"{base_username}{suffix}"
                        suffix += 1

                    # Tạo mật khẩu ngẫu nhiên
                    random_password = secrets.token_urlsafe(16)
                    password_hash = self.get_password_hash(random_password)

                    # Chuẩn bị dữ liệu người dùng
                    user_data = {
                        "username": username,
                        "email": email,
                        "password_hash": password_hash,
                        "display_name": display_name,
                        "avatar_url": token_data.get("photo_url"),
                        "is_email_verified": True,  # Email từ social provider được xem là đã xác thực
                        "last_ip": ip_address,
                    }

    async def search_users(
        self,
        search_term: str,
        page: int = 1,
        limit: int = 10,
        exclude_ids: List[int] = None,
    ) -> Dict[str, Any]:
        """
        Tìm kiếm người dùng theo từ khóa.

        Args:
            search_term: Từ khóa tìm kiếm (username, email, tên)
            page: Trang hiện tại
            limit: Số lượng kết quả mỗi trang
            exclude_ids: Danh sách ID người dùng bị loại trừ

        Returns:
            Dict với users và total_count
        """
        # Sanitize search term để tránh tấn công injection
        if search_term:
            # Kiểm tra an toàn trước khi tìm kiếm
            if detect_sql_injection(search_term) or detect_xss(search_term):
                raise BadRequestException(
                    detail="Từ khóa tìm kiếm chứa ký tự không hợp lệ"
                )

            # Đảm bảo search_term là chuỗi an toàn
            search_term = str(search_term).strip()

        # Tìm kiếm
        result = await self.user_repo.search(
            search_term=search_term,
            page=page,
            limit=limit,
            exclude_ids=exclude_ids or [],
        )

        return result

    def _get_user_response(self, user) -> Dict[str, Any]:
        """
        Chuyển đổi đối tượng User thành dictionary để trả về API.

        Args:
            user: Đối tượng User từ database

        Returns:
            Dict chứa thông tin người dùng
        """
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "avatar": user.avatar_url if hasattr(user, "avatar_url") else None,
            "is_active": user.is_active,
            "is_verified": (
                user.is_verified
                if hasattr(user, "is_verified")
                else user.is_email_verified
            ),
            "is_premium": user.is_premium,
            "premium_until": user.premium_until,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": (
                user.updated_at.isoformat()
                if hasattr(user, "updated_at") and user.updated_at
                else user.created_at.isoformat() if user.created_at else None
            ),
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
