from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional, Union, Dict, Any, Callable
from sqlalchemy.orm import Session
from app.core.db import get_session
from app.security.jwt import decode_token
from app.core.exceptions import TokenExpired, InvalidToken
from functools import wraps

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_session)
):
    """
    Lấy thông tin user hiện tại từ JWT token.

    Args:
        token: JWT token
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: Khi token không hợp lệ hoặc user không tồn tại
    """
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except TokenExpired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidToken:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Kiểm tra user type (admin hoặc user thường)
    if "admin" in payload.get("scopes", []):
        from app.admin_site.models.admin import Admin

        user = db.query(Admin).filter(Admin.id == user_id).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        from app.user_site.models.user import User

        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return user


def get_current_active_user(current_user=Depends(get_current_user)):
    """
    Kiểm tra user hiện tại có active không.

    Args:
        current_user: User object từ get_current_user

    Returns:
        User object nếu active

    Raises:
        HTTPException: Nếu user không active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )
    return current_user


def get_current_admin(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_session)
):
    """
    Lấy thông tin admin hiện tại từ JWT token.

    Args:
        token: JWT token
        db: Database session

    Returns:
        Admin object

    Raises:
        HTTPException: Khi token không hợp lệ hoặc admin không tồn tại
    """
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Kiểm tra xem có phải admin không
        scopes = payload.get("scopes", [])
        if "admin" not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not an admin account",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except TokenExpired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidToken:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.admin_site.models.admin import Admin

    admin = db.query(Admin).filter(Admin.id == user_id).first()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive admin account"
        )

    return admin


def get_current_super_admin(current_admin=Depends(get_current_admin)):
    """
    Kiểm tra admin hiện tại có phải super admin không.

    Args:
        current_admin: Admin object từ get_current_admin

    Returns:
        Admin object nếu là super admin

    Raises:
        HTTPException: Nếu không phải super admin
    """
    if not current_admin.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required",
        )
    return current_admin


def check_permissions(required_permissions: List[str]):
    """
    Decorator kiểm tra quyền của user.

    Args:
        required_permissions: Danh sách tên quyền cần kiểm tra

    Returns:
        Callable that depends on current_user and db
    """

    def permissions_decorator(
        current_admin=Depends(get_current_admin), db: Session = Depends(get_session)
    ):
        # Super admin có tất cả quyền
        if current_admin.is_super_admin:
            return current_admin

        # Lấy quyền của admin từ database
        from app.admin_site.models.permission import Permission
        from app.admin_site.models.role import Role
        from app.admin_site.models.role_permission import RolePermission
        from app.admin_site.models.admin_role import AdminRole

        admin_permissions = (
            db.query(Permission.name)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(AdminRole, Role.id == AdminRole.role_id)
            .filter(AdminRole.admin_id == current_admin.id)
            .all()
        )

        admin_permissions = [p[0] for p in admin_permissions]

        # Kiểm tra quyền
        for permission in required_permissions:
            if permission not in admin_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission {permission} required",
                )

        return current_admin

    return permissions_decorator


def check_permission(permission_name: str):
    """
    Decorator kiểm tra một quyền cụ thể của admin.
    Phiên bản đơn giản hóa của check_permissions.

    Args:
        permission_name: Tên quyền cần kiểm tra

    Returns:
        Callable that depends on current_admin and db
    """
    return check_permissions([permission_name])


def requires_role(role_name: str):
    """
    Decorator kiểm tra người dùng có vai trò cụ thể không.

    Args:
        role_name: Tên vai trò cần kiểm tra

    Returns:
        Callable that depends on current_user and db
    """

    def role_decorator(
        current_user=Depends(get_current_user), db: Session = Depends(get_session)
    ):
        # Lấy vai trò của người dùng từ database
        from app.user_site.models.user_role import UserRole
        from app.user_site.models.role import Role

        user_roles = (
            db.query(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .filter(UserRole.user_id == current_user.id)
            .all()
        )

        user_roles = [r[0] for r in user_roles]

        # Kiểm tra vai trò
        if role_name not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {role_name} required",
            )

        return current_user

    return role_decorator


def user_owns_resource(resource_model, resource_id_name: str = "id"):
    """
    Kiểm tra xem người dùng có sở hữu resource hay không.

    Args:
        resource_model: SQLAlchemy model của resource
        resource_id_name: Tên tham số chứa resource ID

    Returns:
        Decorator function
    """

    def ownership_decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get resource ID from kwargs
            resource_id = kwargs.get(resource_id_name)
            if not resource_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Resource ID {resource_id_name} not provided",
                )

            # Get current user (assumes kwargs has current_user)
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
                )

            # Get database session (assumes kwargs has db)
            db = kwargs.get("db")
            if not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database session not available",
                )

            # Check ownership
            resource = (
                db.query(resource_model)
                .filter(
                    getattr(resource_model, "id") == resource_id,
                    getattr(resource_model, "user_id") == current_user.id,
                )
                .first()
            )

            if not resource:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to access this resource",
                )

            return await func(*args, **kwargs)

        return wrapper

    return ownership_decorator
