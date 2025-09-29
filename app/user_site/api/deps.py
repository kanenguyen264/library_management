from typing import AsyncGenerator, Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta

from fastapi import Depends, HTTPException, status, Request, Security
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
import time

from app.common.db.session import get_db
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.user_site.models.user import User
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.services.auth_service import AuthService
from app.monitoring.metrics import track_auth_request

# Thêm import throttle_requests từ module mới
from app.user_site.api.throttling import throttle_requests

# from app.security.encryption.token_encryption import verify_token_integrity
from app.logging.setup import get_logger
from app.monitoring.apm.apm_agent import APMAgent
from app.security.audit.audit_trails import log_access_attempt
from app.user_site.services.subscription_service import SubscriptionService


# Hàm giả tạm thời cho verify_token_integrity
def verify_token_integrity(token: str) -> bool:
    """
    Kiểm tra tính toàn vẹn của token.
    Hàm tạm thế cho module bị thiếu.
    """
    return True


settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login",
    scopes={
        "user": "Quyền truy cập người dùng thường",
        "premium": "Quyền truy cập người dùng premium",
        "offline_access": "Quyền tạo refresh token",
    },
)
logger = get_logger("auth_deps")
apm_agent = APMAgent()


async def get_current_user(
    security_scopes: SecurityScopes = SecurityScopes(),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> User:
    """
    Xác thực người dùng hiện tại từ JWT token.

    Args:
        security_scopes: Các quyền cần thiết cho endpoint
        token: JWT token từ Authorization header
        db: Database session
        request: FastAPI Request object

    Returns:
        User: Đối tượng User nếu xác thực thành công

    Raises:
        UnauthorizedException: Nếu token không hợp lệ
        ForbiddenException: Nếu người dùng không có quyền
    """
    start_time = time.time()

    # Tạo thông báo lỗi dựa trên scopes yêu cầu
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
        scopes_msg = f"Yêu cầu quyền: {security_scopes.scope_str}"
    else:
        authenticate_value = "Bearer"
        scopes_msg = ""

    credentials_exception = UnauthorizedException(
        detail=f"Không thể xác thực thông tin người dùng. {scopes_msg}",
        headers={"WWW-Authenticate": authenticate_value},
    )

    try:
        # Kiểm tra tính toàn vẹn của token
        if not verify_token_integrity(token):
            logger.warning(f"Token có dấu hiệu bị giả mạo: {token[:10]}...")
            raise credentials_exception

        # Kiểm tra token có trong blacklist không
        auth_service = AuthService(db)
        if await auth_service.is_token_blacklisted(token):
            logger.warning(f"Token đã bị vô hiệu hóa (blacklisted): {token[:10]}...")
            raise UnauthorizedException(
                detail="Token đã hết hạn hoặc bị vô hiệu hóa, vui lòng đăng nhập lại"
            )

        # Giải mã JWT token
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            user_id: str = payload.get("sub")
            token_exp: int = payload.get("exp", 0)
            token_scopes = payload.get("scopes", [])

            if user_id is None:
                logger.warning("Token không chứa thông tin user_id")
                raise credentials_exception

            # Kiểm tra xem token đã hết hạn chưa
            now = datetime.now(timezone.utc).timestamp()
            if token_exp < now:
                logger.warning(f"Token đã hết hạn: {token[:10]}...")
                raise UnauthorizedException(
                    detail="Token đã hết hạn, vui lòng đăng nhập lại",
                    headers={"WWW-Authenticate": authenticate_value},
                )

            # Kiểm tra quyền nếu có
            for scope in security_scopes.scopes:
                if scope not in token_scopes:
                    logger.warning(f"User {user_id} không có quyền {scope}")
                    raise ForbiddenException(
                        detail=f"Không đủ quyền truy cập. Yêu cầu quyền: {scope}",
                        headers={"WWW-Authenticate": authenticate_value},
                    )

        except JWTError as e:
            logger.error(f"Lỗi giải mã JWT: {str(e)}")
            # Ghi nhận lỗi vào APM nếu có
            apm_agent.capture_exception(e)
            raise credentials_exception

        # Lấy thông tin người dùng từ database
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(int(user_id))

        if user is None:
            logger.warning(f"Không tìm thấy người dùng với ID: {user_id}")
            raise credentials_exception

        if not user.is_active:
            logger.warning(f"Tài khoản người dùng {user_id} đã bị vô hiệu hóa")
            raise ForbiddenException(detail="Tài khoản đã bị vô hiệu hóa")

        # Cập nhật last_active nếu đã trôi qua ít nhất 5 phút từ lần cuối
        if (
            datetime.now(timezone.utc) - user.last_active
        ).total_seconds() > 300:  # 5 phút
            await user_repo.update_last_active(user.id)

        # Ghi log truy cập
        if settings.AUDIT_ENABLED and request:
            client_ip = request.client.host
            user_agent = request.headers.get("User-Agent", "")
            resource = request.url.path
            await log_access_attempt(
                resource_type="api_endpoint",
                resource_id=resource,
                user_id=str(user.id),
                user_type="user",
                action="access",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
            )

        # Ghi nhận thời gian xử lý xác thực
        duration = time.time() - start_time
        if request:
            track_auth_request(user.id, True, "token")
            if duration > 0.1:  # Nếu quá 100ms, ghi log cảnh báo
                logger.warning(
                    f"Xác thực token chậm: {duration:.4f}s cho user {user.id}"
                )

        return user

    except HTTPException:
        # Ghi nhận thất bại
        if request:
            track_auth_request(None, False, "token")
        raise
    except Exception as e:
        # Ghi nhận các lỗi khác
        logger.error(f"Lỗi không xác định trong xác thực: {str(e)}")
        apm_agent.capture_exception(e)
        if request:
            track_auth_request(None, False, "token")
        raise credentials_exception


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Xác thực người dùng hiện tại đang active.

    Args:
        current_user: User đã được xác thực từ JWT token

    Returns:
        User: Đối tượng User nếu active

    Raises:
        HTTPException: Nếu tài khoản bị vô hiệu hóa
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị vô hiệu hóa"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Xác thực người dùng hiện tại là admin.

    Args:
        current_user: User đã được xác thực từ JWT token

    Returns:
        User: Đối tượng User nếu là admin

    Raises:
        HTTPException: Nếu không phải admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Yêu cầu quyền admin để truy cập",
        )
    return current_user


async def get_current_premium_user(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Xác thực người dùng hiện tại có quyền premium.

    Args:
        current_user: User đã được xác thực từ JWT token
        db: Database session

    Returns:
        User: Đối tượng User nếu có premium

    Raises:
        HTTPException: Nếu không có premium
    """
    # Kiểm tra từ thuộc tính is_premium
    if hasattr(current_user, "is_premium") and current_user.is_premium:
        return current_user

    # Hoặc kiểm tra từ subscription service
    subscription_service = SubscriptionService(db)
    has_premium = await subscription_service.has_active_premium(current_user.id)

    if not has_premium:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tính năng này chỉ dành cho người dùng premium",
        )

    return current_user


async def get_optional_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Lấy người dùng hiện tại nếu có token hợp lệ, không báo lỗi nếu không có.

    Args:
        token: JWT token từ Authorization header
        db: Database session

    Returns:
        Optional[User]: Đối tượng User nếu có và token hợp lệ, None nếu không
    """
    try:
        return await get_current_user(SecurityScopes(), token, db)
    except HTTPException:
        return None


async def is_moderator(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """
    Kiểm tra xem người dùng có phải là moderator không.

    Args:
        current_user: User hiện tại
        db: Database session

    Returns:
        bool: True nếu là moderator, False nếu không
    """
    from app.user_site.models.user_role import UserRole
    from app.user_site.models.role import Role
    from sqlalchemy import select

    # Lấy vai trò của người dùng từ database
    query = (
        select(Role.name)
        .join(UserRole, Role.id == UserRole.role_id)
        .filter(UserRole.user_id == current_user.id)
    )
    result = await db.execute(query)
    user_roles = result.scalars().all()

    # Kiểm tra xem người dùng có vai trò moderator không
    is_mod = "moderator" in user_roles

    # Hoặc kiểm tra quyền của người dùng
    auth_service = AuthService(db)
    has_perm = await auth_service.check_permission(current_user.id, "moderate_content")

    return is_mod or has_perm or current_user.is_staff


async def is_admin(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """
    Kiểm tra người dùng hiện tại có phải là admin không.

    Args:
        current_user: Người dùng hiện tại
        db: Database session

    Returns:
        bool: True nếu là admin, ngược lại False
    """
    user_repo = UserRepository(db)
    admin_status = await user_repo.is_admin(current_user.id)
    return admin_status


async def verify_subscription(
    feature: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Kiểm tra người dùng có quyền truy cập tính năng dựa vào loại gói đăng ký.

    Args:
        feature: Tên tính năng cần kiểm tra
        current_user: Người dùng hiện tại
        db: Database session

    Returns:
        User: Người dùng nếu có quyền truy cập

    Raises:
        ForbiddenException: Nếu không có quyền truy cập tính năng này
    """
    # Luôn cho phép admin truy cập mọi tính năng
    if await is_admin(current_user, db):
        return current_user

    # Kiểm tra người dùng premium có quyền mặc định cho một số tính năng
    if await get_current_premium_user(current_user, db):
        # Danh sách tính năng premium có quyền truy cập
        premium_features = [
            "advanced_search",
            "reading_analytics",
            "personalized_recommendations",
            "annotations_export",
            "reading_goals",
            "book_collections",
            "api_access",
        ]

        if feature in premium_features:
            return current_user

    # Kiểm tra quyền truy cập cụ thể dựa trên gói đăng ký
    subscription_service = SubscriptionService(db)
    has_access = await subscription_service.check_feature_access(
        current_user.id, feature
    )

    if not has_access:
        raise ForbiddenException(
            detail=f"Tính năng '{feature}' yêu cầu gói đăng ký cao cấp hơn",
            code="subscription_required",
        )

    return current_user
