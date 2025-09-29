from sqlalchemy.orm import Session
from typing import Tuple, Optional, Dict, Any
import jwt
from datetime import datetime, timezone, timedelta
import bcrypt
from fastapi import HTTPException, status

from app.admin_site.models import Admin, AdminSession
from app.admin_site.repositories.admin_repo import AdminRepository
from app.admin_site.repositories.admin_session_repo import AdminSessionRepository
from app.core.config import get_settings
from app.core.exceptions import (
    UnauthorizedException,
    NotFoundException,
    ServerException,
    BadRequestException,
)
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

settings = get_settings()
logger = get_logger(__name__)


def authenticate_admin(db: Session, username: str, password: str) -> Optional[Admin]:
    """
    Xác thực admin với username và password.

    Args:
        db: Database session
        username: Tên đăng nhập
        password: Mật khẩu

    Returns:
        Admin object nếu xác thực thành công, None nếu thất bại

    Raises:
        UnauthorizedException: Nếu thông tin đăng nhập không hợp lệ
    """
    try:
        # Tìm admin theo username
        admin = AdminRepository.get_by_username(db, username)

        if not admin:
            logger.warning(f"Không tìm thấy admin với username: {username}")
            return None

        # Kiểm tra tài khoản có bị khóa không
        if not admin.is_active:
            logger.warning(f"Tài khoản admin đã bị khóa: {username}")

            # Log failed login attempt with inactive account
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin.id,
                        activity_type="AUTH",
                        entity_type="ADMIN",
                        entity_id=admin.id,
                        description=f"Failed login attempt with inactive account: {username}",
                        metadata={
                            "username": username,
                            "reason": "Account inactive",
                            "ip_address": None,  # IP address should be passed in production
                            "user_agent": None,  # User agent should be passed in production
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

            return None

        # Kiểm tra mật khẩu
        if not verify_password(password, admin.password_hash):
            logger.warning(f"Mật khẩu không chính xác cho admin: {username}")

            # Log failed login attempt with incorrect password
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin.id,
                        activity_type="AUTH",
                        entity_type="ADMIN",
                        entity_id=admin.id,
                        description=f"Failed login attempt with incorrect password: {username}",
                        metadata={
                            "username": username,
                            "reason": "Invalid password",
                            "ip_address": None,  # IP address should be passed in production
                            "user_agent": None,  # User agent should be passed in production
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

            return None

        # Cập nhật thời gian đăng nhập gần nhất
        try:
            AdminRepository.update_last_login(db, admin.id)

            # Log successful login
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin.id,
                        activity_type="AUTH",
                        entity_type="ADMIN",
                        entity_id=admin.id,
                        description=f"Successful login: {username}",
                        metadata={
                            "username": username,
                            "ip_address": None,  # IP address should be passed in production
                            "user_agent": None,  # User agent should be passed in production
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        except Exception as e:
            logger.error(f"Lỗi khi cập nhật thời gian đăng nhập: {str(e)}")

        return admin
    except Exception as e:
        logger.error(f"Lỗi khi xác thực admin: {str(e)}")
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Kiểm tra mật khẩu.

    Args:
        plain_password: Mật khẩu gốc
        hashed_password: Mật khẩu đã hash

    Returns:
        True nếu mật khẩu chính xác, False nếu không
    """
    try:
        # Chuyển đổi sang bytes nếu cần
        if isinstance(plain_password, str):
            plain_password = plain_password.encode("utf-8")

        if isinstance(hashed_password, str):
            hashed_password = hashed_password.encode("utf-8")

        # Kiểm tra mật khẩu
        return bcrypt.checkpw(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra mật khẩu: {str(e)}")
        return False


def get_password_hash(password: str) -> str:
    """
    Tạo hash cho mật khẩu.

    Args:
        password: Mật khẩu gốc

    Returns:
        Chuỗi hash của mật khẩu
    """
    try:
        # Chuyển đổi sang bytes nếu cần
        if isinstance(password, str):
            password = password.encode("utf-8")

        # Tạo salt và hash
        salt = bcrypt.gensalt()
        hashed_pw = bcrypt.hashpw(password, salt)

        # Trả về chuỗi hash
        return hashed_pw.decode("utf-8")
    except Exception as e:
        logger.error(f"Lỗi khi tạo hash mật khẩu: {str(e)}")
        raise ServerException(detail=f"Lỗi khi tạo hash mật khẩu: {str(e)}")


def create_admin_token(admin: Admin) -> Tuple[str, str]:
    """
    Tạo token cho admin.

    Args:
        admin: Admin object

    Returns:
        Tuple (access_token, refresh_token)

    Raises:
        ServerException: Nếu có lỗi khi tạo token
    """
    try:
        # Tạo access token
        access_token_expires = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

        access_token_data = {
            "sub": str(admin.id),
            "username": admin.username,
            "is_super_admin": admin.is_super_admin,
            "exp": access_token_expires,
        }

        access_token = jwt.encode(
            access_token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )

        # Tạo refresh token
        refresh_token_expires = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        refresh_token_data = {
            "sub": str(admin.id),
            "type": "refresh",
            "exp": refresh_token_expires,
        }

        refresh_token = jwt.encode(
            refresh_token_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )

        return access_token, refresh_token
    except Exception as e:
        logger.error(f"Lỗi khi tạo token: {str(e)}")
        raise ServerException(detail=f"Lỗi khi tạo token: {str(e)}")


def refresh_admin_token(db: Session, refresh_token: str) -> Tuple[Admin, str, str]:
    """
    Làm mới token admin.

    Args:
        db: Database session
        refresh_token: Refresh token

    Returns:
        Tuple (admin, access_token, refresh_token)

    Raises:
        UnauthorizedException: Nếu refresh token không hợp lệ
        ServerException: Nếu có lỗi khác xảy ra
    """
    try:
        # Giải mã refresh token
        try:
            payload = jwt.decode(
                refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )

            # Kiểm tra loại token
            if payload.get("type") != "refresh":
                raise UnauthorizedException(detail="Token không hợp lệ")

            admin_id = int(payload.get("sub"))
        except jwt.PyJWTError:
            raise UnauthorizedException(detail="Token không hợp lệ hoặc hết hạn")

        # Kiểm tra token có trong database không
        session = AdminSessionRepository.get_by_token(db, refresh_token)
        if not session:
            raise UnauthorizedException(
                detail="Token không tồn tại hoặc đã bị vô hiệu hóa"
            )

        # Kiểm tra phiên có bị vô hiệu hóa không
        if session.status != "active":
            raise UnauthorizedException(detail="Phiên đã bị vô hiệu hóa")

        # Lấy thông tin admin
        admin = AdminRepository.get_by_id(db, admin_id)
        if not admin:
            raise NotFoundException(detail="Admin không tồn tại")

        # Kiểm tra tài khoản có bị khóa không
        if not admin.is_active:
            # Log failed token refresh with inactive account
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin.id,
                        activity_type="AUTH",
                        entity_type="ADMIN",
                        entity_id=admin.id,
                        description=f"Failed token refresh with inactive account: {admin.username}",
                        metadata={
                            "username": admin.username,
                            "reason": "Account inactive",
                            "ip_address": None,  # IP address should be passed in production
                            "user_agent": None,  # User agent should be passed in production
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

            raise UnauthorizedException(detail="Tài khoản đã bị khóa")

        # Tạo token mới
        new_access_token, new_refresh_token = create_admin_token(admin)

        # Vô hiệu hóa refresh token cũ
        AdminSessionRepository.invalidate(db, refresh_token)

        # Log successful token refresh
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin.id,
                    activity_type="AUTH",
                    entity_type="ADMIN",
                    entity_id=admin.id,
                    description=f"Successful token refresh: {admin.username}",
                    metadata={
                        "username": admin.username,
                        "ip_address": None,  # IP address should be passed in production
                        "user_agent": None,  # User agent should be passed in production
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

        return admin, new_access_token, new_refresh_token
    except Exception as e:
        if isinstance(e, (UnauthorizedException, NotFoundException)):
            raise e

        logger.error(f"Lỗi khi làm mới token: {str(e)}")
        raise ServerException(detail=f"Lỗi khi làm mới token: {str(e)}")


def change_admin_password(
    db: Session, admin_id: int, current_password: str, new_password: str
) -> bool:
    """
    Thay đổi mật khẩu admin.

    Args:
        db: Database session
        admin_id: ID admin
        current_password: Mật khẩu hiện tại
        new_password: Mật khẩu mới

    Returns:
        True nếu thay đổi thành công

    Raises:
        NotFoundException: Nếu không tìm thấy admin
        BadRequestException: Nếu mật khẩu hiện tại không đúng
        ServerException: Nếu có lỗi khác xảy ra
    """
    try:
        # Lấy thông tin admin
        admin = AdminRepository.get_by_id(db, admin_id)
        if not admin:
            raise NotFoundException(detail="Admin không tồn tại")

        # Kiểm tra mật khẩu hiện tại
        if not verify_password(current_password, admin.password_hash):
            # Log failed password change attempt with incorrect password
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="ADMIN",
                        entity_id=admin_id,
                        description=f"Failed password change attempt with incorrect current password: {admin.username}",
                        metadata={
                            "username": admin.username,
                            "reason": "Invalid current password",
                            "ip_address": None,  # IP address should be passed in production
                            "user_agent": None,  # User agent should be passed in production
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

            raise BadRequestException(detail="Mật khẩu hiện tại không đúng")

        # Kiểm tra mật khẩu mới có giống mật khẩu cũ không
        if verify_password(new_password, admin.password_hash):
            # Log failed password change attempt with same password
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="ADMIN",
                        entity_id=admin_id,
                        description=f"Failed password change attempt with same password: {admin.username}",
                        metadata={
                            "username": admin.username,
                            "reason": "New password same as old password",
                            "ip_address": None,  # IP address should be passed in production
                            "user_agent": None,  # User agent should be passed in production
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

            raise BadRequestException(
                detail="Mật khẩu mới không được giống mật khẩu cũ"
            )

        # Hash mật khẩu mới
        hashed_password = get_password_hash(new_password)

        # Cập nhật mật khẩu
        updated_admin = AdminRepository.update_password(db, admin_id, hashed_password)
        if not updated_admin:
            raise ServerException(detail="Không thể cập nhật mật khẩu")

        # Vô hiệu hóa tất cả phiên của admin
        AdminSessionRepository.invalidate_all_by_admin(db, admin_id)

        # Log successful password change
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="UPDATE",
                    entity_type="ADMIN",
                    entity_id=admin_id,
                    description=f"Successful password change: {admin.username}",
                    metadata={
                        "username": admin.username,
                        "ip_address": None,  # IP address should be passed in production
                        "user_agent": None,  # User agent should be passed in production
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi thay đổi mật khẩu admin: {str(e)}")
        raise ServerException(detail=f"Lỗi khi thay đổi mật khẩu admin: {str(e)}")


def get_admin_by_username(db: Session, username: str) -> Optional[Admin]:
    """
    Lấy thông tin admin theo username.

    Args:
        db: Database session
        username: Tên đăng nhập cần tìm

    Returns:
        Admin object nếu tìm thấy, None nếu không tìm thấy
    """
    try:
        # Sử dụng repository để tìm admin
        admin = AdminRepository.get_by_username(db, username)
        return admin
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin admin theo username: {str(e)}")
        return None
