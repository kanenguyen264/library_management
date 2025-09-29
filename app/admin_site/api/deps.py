from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jwt import PyJWTError, decode
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime, timezone
import functools

from app.common.db.session import get_db
from app.admin_site.models import Admin, Permission
from app.admin_site.repositories.admin_session_repo import AdminSessionRepository
from app.core.config import get_settings
from app.logging.setup import get_logger
from app.cache.manager import CacheManager
from app.core.exceptions import AuthenticationException

settings = get_settings()
logger = get_logger(__name__)
cache = CacheManager()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/admin/login")


# Cache quyền của admin để cải thiện hiệu suất
def cache_admin_permissions(admin_id: int, permissions: List[str]) -> None:
    """Cache quyền của admin."""
    cache_key = f"admin:{admin_id}:permissions"
    cache.set(cache_key, permissions, ttl=300)  # Cache trong 5 phút


def get_cached_admin_permissions(admin_id: int) -> Optional[List[str]]:
    """Lấy quyền của admin từ cache."""
    cache_key = f"admin:{admin_id}:permissions"
    return cache.get(cache_key)


def invalidate_admin_permissions_cache(admin_id: int) -> None:
    """Xóa cache quyền của admin."""
    cache_key = f"admin:{admin_id}:permissions"
    cache.delete(cache_key)


async def get_current_admin(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Admin:
    """
    Lấy thông tin admin từ token.

    Args:
        token: JWT token
        db: Database session

    Returns:
        Admin object

    Raises:
        AuthenticationException: Nếu token không hợp lệ hoặc admin không tồn tại
    """
    credentials_exception = AuthenticationException(
        detail="Không thể xác thực thông tin admin",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Giải mã token
        payload = decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        admin_id = payload.get("sub")
        if admin_id is None:
            logger.warning("Token không chứa admin ID")
            raise credentials_exception

        # Kiểm tra thời gian hết hạn
        exp = payload.get("exp")
        if exp is None or datetime.now(timezone.utc).timestamp() > exp:
            logger.warning("Token đã hết hạn")
            raise AuthenticationException(
                detail="Token đã hết hạn, vui lòng đăng nhập lại",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Kiểm tra session token
        session_id = payload.get("sid")
        if session_id:
            # Kiểm tra xem session có còn active không (đề phòng token bị dùng sau khi logout)
            is_active = AdminSessionRepository.is_session_active(db, session_id)
            if not is_active:
                logger.warning(f"Session {session_id} đã hết hạn hoặc bị đăng xuất")
                raise AuthenticationException(
                    detail="Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    except PyJWTError as e:
        logger.warning(f"Lỗi giải mã token: {str(e)}")
        raise credentials_exception

    # Tìm admin trong database
    admin = (
        db.query(Admin).filter(Admin.id == admin_id, Admin.is_active == True).first()
    )

    if admin is None:
        logger.warning(f"Admin ID {admin_id} không tồn tại hoặc bị khóa")
        raise credentials_exception

    return admin


async def get_super_admin(current_admin: Admin = Depends(get_current_admin)) -> Admin:
    """
    Kiểm tra admin có quyền super admin không.

    Args:
        current_admin: Admin object hiện tại

    Returns:
        Admin object nếu là super admin

    Raises:
        HTTPException: Nếu không phải super admin
    """
    if not current_admin.is_super_admin:
        logger.warning(f"Admin {current_admin.username} không có quyền super admin")

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền thực hiện hành động này",
        )

    return current_admin


def check_admin_permissions(required_permissions: List[str]):
    """
    Decorator để kiểm tra admin có đủ quyền để thực hiện hành động.

    Args:
        required_permissions: Danh sách quyền cần kiểm tra

    Returns:
        Hàm dependency để FastAPI sử dụng
    """

    async def _check_permissions(
        current_admin: Admin = Depends(get_current_admin),
        db: Session = Depends(get_db),
        request: Request = None,
    ) -> Admin:
        # Super admin luôn có tất cả quyền
        if current_admin.is_super_admin:
            return current_admin

        # Lấy quyền từ cache (nếu có)
        admin_permissions = get_cached_admin_permissions(current_admin.id)

        # Nếu không có trong cache, truy vấn database
        if admin_permissions is None:
            admin_permissions = []

            for role in current_admin.roles:
                for permission in role.permissions:
                    admin_permissions.append(permission.name)

            # Lưu vào cache
            cache_admin_permissions(current_admin.id, admin_permissions)

        # Kiểm tra các quyền cần thiết
        has_permissions = all(
            perm in admin_permissions for perm in required_permissions
        )

        if not has_permissions:
            logger.warning(
                f"Admin {current_admin.username} không có đủ quyền: {required_permissions}, path: {request.url.path if request else 'N/A'}"
            )

            missing_permissions = [
                perm for perm in required_permissions if perm not in admin_permissions
            ]

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Không có quyền thực hiện hành động này. Thiếu quyền: {', '.join(missing_permissions)}",
            )

        return current_admin

    return _check_permissions


# Kiểm tra IP nguồn có trong danh sách IP được chấp nhận
def check_admin_ip(allowed_ips: List[str] = None):
    """
    Kiểm tra IP nguồn có được phép truy cập không.

    Args:
        allowed_ips: Danh sách IP được phép

    Returns:
        Hàm dependency để FastAPI sử dụng
    """

    async def _check_ip(request: Request) -> None:
        # Nếu không chỉ định IP, cho phép tất cả
        if not allowed_ips:
            return

        client_ip = request.client.host
        if client_ip not in allowed_ips:
            logger.warning(f"Truy cập bị từ chối từ IP: {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Địa chỉ IP không được phép truy cập",
            )

    return _check_ip


# Dependency kết hợp để kiểm tra cả quyền và IP nguồn
def secure_admin_access(required_permissions: List[str], allowed_ips: List[str] = None):
    """
    Kết hợp kiểm tra quyền và IP nguồn.

    Args:
        required_permissions: Danh sách quyền cần kiểm tra
        allowed_ips: Danh sách IP được phép

    Returns:
        Hàm dependency để FastAPI sử dụng
    """
    permission_check = check_admin_permissions(required_permissions)
    ip_check = check_admin_ip(allowed_ips)

    async def _secure_access(
        admin: Admin = Depends(permission_check), _: None = Depends(ip_check)
    ) -> Admin:
        return admin

    return _secure_access
