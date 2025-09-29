from fastapi import APIRouter, Depends, HTTPException, status, Body, Header, Request
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Any, Dict
from datetime import datetime
import traceback
import json
import uuid

from app.common.db.session import get_db
from app.admin_site.models import Admin
from app.admin_site.schemas.auth import (
    AdminLoginResponse,
    AdminRefreshTokenRequest,
    AdminChangePasswordRequest,
    TokenRefresh,
)
from app.admin_site.services.auth_service import (
    authenticate_admin,
    create_admin_token,
    refresh_admin_token,
    change_admin_password,
    get_admin_by_username,
)
from app.admin_site.services.admin_session_service import (
    create_admin_session,
    invalidate_session,
    validate_refresh_token,
    invalidate_session_by_refresh_token,
)
from app.admin_site.api.deps import get_current_admin
from app.security.audit.log_admin_action import (
    log_admin_login,
    log_admin_logout,
    log_admin_action,
)
from app.security.audit.log_admin_action import log_admin_access
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint
from app.cache.decorators import cached
from app.core.db import get_session
from app.security.jwt import create_access_token, create_refresh_token
from app.core.exceptions import AuthenticationException
from app.security.audit.audit_trails import log_data_operation

logger = get_logger(__name__)
router = APIRouter(tags=["Admin Auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/admin/auth/login")


# Endpoint dummy để hỗ trợ người dùng khi truy cập sai đường dẫn
@router.post("/login", include_in_schema=False)
async def incorrect_login_endpoint():
    """
    Endpoint dummy để thông báo về đường dẫn đúng khi người dùng truy cập sai URL
    """
    raise HTTPException(
        status_code=status.HTTP_308_PERMANENT_REDIRECT,
        detail="Endpoint đã di chuyển. Vui lòng sử dụng /api/v1/admin/auth/login thay vì /api/v1/admin/login",
        headers={"Location": "/api/v1/admin/auth/login"},
    )


@router.post("/auth/login", response_model=AdminLoginResponse)
@profile_endpoint(name="admin:login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_session),
):
    """
    Đăng nhập với username và password
    """
    # Tạo request_id để theo dõi xuyên suốt quá trình
    request_id = str(uuid.uuid4())

    # Ghi log thông tin request
    client_ip = "unknown"
    user_agent = "unknown"

    if request:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ["authorization", "cookie"]
        }

        logger.info(
            f"Admin login attempt - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "username": form_data.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "headers": json.dumps(headers),
                "timestamp": datetime.now().isoformat(),
            },
        )

    try:
        # Xử lý đặc biệt cho AsyncSession
        from sqlalchemy import text

        # Tìm admin theo username
        stmt = text("SELECT * FROM admin.admins WHERE username = :username")
        result = await db.execute(stmt, {"username": form_data.username})
        admin_row = result.first()

        if not admin_row:
            # Ghi log thất bại
            logger.warning(
                f"Admin login failed - User not found - Request ID: {request_id}",
                extra={
                    "request_id": request_id,
                    "username": form_data.username,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "error": "User not found",
                    "timestamp": datetime.now().isoformat(),
                },
            )

            # Audit log
            log_data_operation(
                operation="login",
                resource_type="authentication",
                resource_id=None,
                user_id=form_data.username,
                user_type="admin",
                status="error",
                ip_address=client_ip,
                user_agent=user_agent,
                changes={
                    "error": "User not found",
                    "request_id": request_id,
                },
                db=db,
            )

            raise AuthenticationException(
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Map kết quả query thành admin model
        from app.admin_site.models.admin import Admin

        admin = Admin(
            id=admin_row[0],
            username=admin_row[1],
            email=admin_row[2],
            password_hash=admin_row[3],
            full_name=admin_row[4],
            avatar_url=admin_row[5],
            is_active=admin_row[6],
            is_superadmin=admin_row[7],
            role_id=admin_row[8],
            phone=admin_row[9],
            note=admin_row[10],
            last_login=admin_row[11],
            login_count=admin_row[12],
            failed_login_attempts=admin_row[13],
            last_failed_login=admin_row[14],
            created_at=admin_row[15],
            updated_at=admin_row[16],
        )

        # Kiểm tra tài khoản có bị khóa không
        if not admin.is_active:
            logger.warning(
                f"Admin login failed - Inactive account - Request ID: {request_id}",
                extra={
                    "request_id": request_id,
                    "username": form_data.username,
                    "admin_id": admin.id,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "error": "Inactive account",
                    "timestamp": datetime.now().isoformat(),
                },
            )

            # Audit log
            log_data_operation(
                operation="login",
                resource_type="authentication",
                resource_id=None,
                user_id=form_data.username,
                user_type="admin",
                status="error",
                ip_address=client_ip,
                user_agent=user_agent,
                changes={
                    "error": "Inactive account",
                    "request_id": request_id,
                },
                db=db,
            )

            raise AuthenticationException(
                detail="Account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Kiểm tra mật khẩu
        from app.security.password import verify_password

        if not verify_password(form_data.password, admin.password_hash):
            logger.warning(
                f"Admin login failed - Incorrect password - Request ID: {request_id}",
                extra={
                    "request_id": request_id,
                    "username": form_data.username,
                    "admin_id": admin.id,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "error": "Incorrect password",
                    "timestamp": datetime.now().isoformat(),
                },
            )

            # Audit log
            log_data_operation(
                operation="login",
                resource_type="authentication",
                resource_id=None,
                user_id=form_data.username,
                user_type="admin",
                status="error",
                ip_address=client_ip,
                user_agent=user_agent,
                changes={
                    "error": "Incorrect password",
                    "request_id": request_id,
                },
                db=db,
            )

            raise AuthenticationException(
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Cập nhật thời gian đăng nhập gần nhất và số lần đăng nhập
        try:
            from datetime import timezone

            update_stmt = text(
                """
                UPDATE admin.admins 
                SET last_login = CURRENT_TIMESTAMP, 
                    login_count = login_count + 1,
                    failed_login_attempts = 0
                WHERE id = :admin_id
                """
            )
            await db.execute(update_stmt, {"admin_id": admin.id})
            await db.commit()
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật thông tin đăng nhập: {str(e)}")
            # Không cần rollback vì chúng ta vẫn muốn đăng nhập thành công

        access_token = create_access_token(
            data={"sub": str(admin.id), "scopes": ["admin"]},
        )

        refresh_token = create_refresh_token(
            data={"sub": str(admin.id), "scopes": ["admin"]},
        )

        # Lưu session
        ip_address = getattr(request, "client", None)
        ip = getattr(ip_address, "host", "unknown") if ip_address else "unknown"
        user_agent = (
            request.headers.get("User-Agent", "unknown") if request else "unknown"
        )

        # Tạo session trực tiếp thay vì qua service
        from datetime import datetime, timezone

        insert_stmt = text(
            """
            INSERT INTO admin.admin_sessions 
            (admin_id, ip_address, user_agent, refresh_token, created_at, last_activity, is_active)
            VALUES (:admin_id, :ip_address, :user_agent, :refresh_token, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, TRUE)
            RETURNING id
            """
        )
        session_result = await db.execute(
            insert_stmt,
            {
                "admin_id": admin.id,
                "ip_address": ip,
                "user_agent": user_agent,
                "refresh_token": refresh_token,
            },
        )
        session_id = session_result.scalar_one()
        await db.commit()

        # Ghi log thành công
        logger.info(
            f"Admin login successful - Admin ID: {admin.id} - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "admin_id": admin.id,
                "username": admin.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Audit log
        log_data_operation(
            operation="login",
            resource_type="authentication",
            resource_id=None,
            user_id=str(admin.id),
            user_type="admin",
            status="success",
            ip_address=client_ip,
            user_agent=user_agent,
            changes={
                "username": admin.username,
                "session_id": session_id,
                "request_id": request_id,
            },
            db=db,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "admin": admin,
        }
    except AuthenticationException:
        # Đã xử lý ở trên
        raise
    except Exception as e:
        # Ghi log chi tiết về lỗi
        error_detail = traceback.format_exc()
        logger.error(
            f"Admin login error - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "username": form_data.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "error": str(e),
                "error_type": e.__class__.__name__,
                "traceback": error_detail,
                "timestamp": datetime.now().isoformat(),
            },
        )

        # Audit log
        log_data_operation(
            operation="login",
            resource_type="authentication",
            resource_id=None,
            user_id=form_data.username,
            user_type="admin",
            status="error",
            ip_address=client_ip,
            user_agent=user_agent,
            changes={
                "error": str(e),
                "error_type": e.__class__.__name__,
                "request_id": request_id,
            },
            db=db,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi xác thực: {str(e)}",
        )


@router.post("/auth/refresh", response_model=AdminLoginResponse)
@profile_endpoint(name="admin:refresh_token")
async def refresh_token(
    token_data: TokenRefresh = Body(...),
    db: Session = Depends(get_session),
    request: Request = None,
):
    """
    Refresh access token using refresh token
    """
    # Tạo request_id để theo dõi
    request_id = str(uuid.uuid4())

    # Ghi log thông tin request
    client_ip = "unknown"
    user_agent = "unknown"

    if request:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")

        logger.info(
            f"Admin token refresh attempt - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "timestamp": datetime.now().isoformat(),
            },
        )

    try:
        # Validate refresh token
        refresh_data = validate_refresh_token(db, token_data.refresh_token)
        if not refresh_data:
            logger.warning(
                f"Admin token refresh failed - Invalid token - Request ID: {request_id}",
                extra={
                    "request_id": request_id,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "error": "Invalid refresh token",
                    "token_fragment": (
                        token_data.refresh_token[:10] + "..."
                        if token_data.refresh_token
                        else "None"
                    ),
                    "timestamp": datetime.now().isoformat(),
                },
            )

            raise AuthenticationException(
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        admin_id = refresh_data.get("sub")
        admin = get_admin_by_username(db, admin_id)
        if not admin:
            logger.warning(
                f"Admin token refresh failed - Admin not found - Request ID: {request_id}",
                extra={
                    "request_id": request_id,
                    "admin_id": admin_id,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "error": "Admin not found",
                    "timestamp": datetime.now().isoformat(),
                },
            )

            raise AuthenticationException(
                detail="Admin not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Create new tokens
        access_token = create_access_token(
            data={"sub": str(admin.id), "scopes": ["admin"]},
        )

        new_refresh_token = create_refresh_token(
            data={"sub": str(admin.id), "scopes": ["admin"]},
        )

        # Invalidate old refresh token
        invalidate_session_by_refresh_token(db, token_data.refresh_token)

        # Create new session with new refresh token
        ip_address = getattr(request, "client", None)
        ip = getattr(ip_address, "host", "unknown") if ip_address else "unknown"
        user_agent = (
            request.headers.get("User-Agent", "unknown") if request else "unknown"
        )
        session = create_admin_session(db, admin.id, ip, user_agent, new_refresh_token)

        # Ghi log thành công
        logger.info(
            f"Admin token refresh successful - Admin ID: {admin.id} - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "admin_id": admin.id,
                "username": admin.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "session_id": getattr(session, "id", "unknown"),
                "timestamp": datetime.now().isoformat(),
            },
        )

        # Audit log
        log_admin_action(
            action="refresh_token",
            resource_type="authentication",
            resource_id=admin.id,
            description=f"Admin {admin.username} refreshed access token",
            changes={"session_id": getattr(session, "id", "unknown")},
        )(lambda: None)()

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "admin": admin,
        }
    except AuthenticationException:
        # Đã xử lý ở trên
        raise
    except Exception as e:
        # Ghi log chi tiết về lỗi
        error_detail = traceback.format_exc()
        logger.error(
            f"Admin token refresh error - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "error": str(e),
                "error_type": e.__class__.__name__,
                "traceback": error_detail,
                "timestamp": datetime.now().isoformat(),
            },
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi làm mới token: {str(e)}",
        )


@router.post("/auth/logout")
@profile_endpoint(name="admin:logout")
@log_admin_action(action="logout", resource_type="session")
async def logout(
    token_data: TokenRefresh = Body(...),
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
    request: Request = None,
):
    """
    Đăng xuất và vô hiệu hóa refresh token
    """
    # Tạo request_id để theo dõi
    request_id = str(uuid.uuid4())

    # Ghi log thông tin request
    client_ip = "unknown"
    user_agent = "unknown"

    if request:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")

        logger.info(
            f"Admin logout attempt - Admin ID: {current_admin.id} - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "admin_id": current_admin.id,
                "username": current_admin.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "timestamp": datetime.now().isoformat(),
            },
        )

    try:
        success = invalidate_session_by_refresh_token(db, token_data.refresh_token)
        if not success:
            logger.warning(
                f"Admin logout failed - Invalid token - Admin ID: {current_admin.id} - Request ID: {request_id}",
                extra={
                    "request_id": request_id,
                    "admin_id": current_admin.id,
                    "username": current_admin.username,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "error": "Invalid refresh token",
                    "token_fragment": (
                        token_data.refresh_token[:10] + "..."
                        if token_data.refresh_token
                        else "None"
                    ),
                    "timestamp": datetime.now().isoformat(),
                },
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid refresh token"
            )

        # Ghi log đăng xuất thành công
        logger.info(
            f"Admin logout successful - Admin ID: {current_admin.id} - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "admin_id": current_admin.id,
                "username": current_admin.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "timestamp": datetime.now().isoformat(),
            },
        )

        # Audit log
        log_admin_logout(db)(lambda: None)()

        return {"message": "Successfully logged out"}
    except HTTPException:
        # Đã xử lý ở trên
        raise
    except Exception as e:
        # Ghi log chi tiết về lỗi
        error_detail = traceback.format_exc()
        logger.error(
            f"Admin logout error - Admin ID: {current_admin.id} - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "admin_id": current_admin.id,
                "username": current_admin.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "error": str(e),
                "error_type": e.__class__.__name__,
                "traceback": error_detail,
                "timestamp": datetime.now().isoformat(),
            },
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi đăng xuất: {str(e)}",
        )


@router.post("/change-password")
@profile_endpoint(name="admin:change_password")
@log_admin_action(
    action="update", resource_type="password", description="Admin changed password"
)
async def change_password(
    request_data: AdminChangePasswordRequest = Body(...),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Đổi mật khẩu quản trị viên.

    **Cách sử dụng**:
    - Gửi mật khẩu cũ và mật khẩu mới

    **Kết quả**:
    - Thành công nếu mật khẩu cũ chính xác
    - Lỗi 400 nếu mật khẩu cũ không chính xác
    """
    # Tạo request_id để theo dõi
    request_id = str(uuid.uuid4())

    # Ghi log thông tin request
    client_ip = "unknown"
    user_agent = "unknown"

    if request:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")

        logger.info(
            f"Admin password change attempt - Admin ID: {current_admin.id} - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "admin_id": current_admin.id,
                "username": current_admin.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "timestamp": datetime.now().isoformat(),
            },
        )

    try:
        # Đổi mật khẩu
        success = change_admin_password(
            db,
            current_admin.id,
            request_data.current_password,
            request_data.new_password,
        )

        if not success:
            logger.warning(
                f"Admin password change failed - Incorrect current password - Admin ID: {current_admin.id} - Request ID: {request_id}",
                extra={
                    "request_id": request_id,
                    "admin_id": current_admin.id,
                    "username": current_admin.username,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "error": "Incorrect current password",
                    "timestamp": datetime.now().isoformat(),
                },
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mật khẩu hiện tại không chính xác",
            )

        # Ghi log thành công
        logger.info(
            f"Admin password change successful - Admin ID: {current_admin.id} - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "admin_id": current_admin.id,
                "username": current_admin.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "timestamp": datetime.now().isoformat(),
            },
        )

        # Audit log được xử lý bởi decorator log_admin_action

        return {"message": "Đổi mật khẩu thành công"}
    except HTTPException as e:
        raise e
    except Exception as e:
        # Ghi log chi tiết về lỗi
        error_detail = traceback.format_exc()
        logger.error(
            f"Admin password change error - Admin ID: {current_admin.id} - Request ID: {request_id}",
            extra={
                "request_id": request_id,
                "admin_id": current_admin.id,
                "username": current_admin.username,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "error": str(e),
                "error_type": e.__class__.__name__,
                "traceback": error_detail,
                "timestamp": datetime.now().isoformat(),
            },
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi đổi mật khẩu: {str(e)}",
        )
