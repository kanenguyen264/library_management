from datetime import timedelta
from typing import Any, Dict, List, Optional, Union
import time
import asyncio
import traceback

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    status,
    Request,
    BackgroundTasks,
    Query,
    Response,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.common.db.session import get_db
from app.core.config import get_settings
from app.user_site.services.user_service import UserService
from app.user_site.services.auth_service import AuthService
from app.user_site.models.user import User
from app.user_site.schemas.user import UserCreate, UserResponse, Token, TokenData
from app.user_site.schemas.auth import (
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
    EmailVerificationRequest,
    TwoFactorVerifyRequest,
    TwoFactorSetupResponse,
    TwoFactorEnableRequest,
    TwoFactorDisableRequest,
)
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ServerException,
    UnauthorizedException,
    ForbiddenException,
    RateLimitException,
    NotFoundException,
    ClientException,
)
from app.security.ddos.rate_limiter import rate_limit
from app.monitoring.metrics.metrics import Metrics
from app.monitoring.metrics.metrics import (
    track_request_time as metrics_track_request_time,
)
from app.monitoring.metrics import track_auth_request
from app.security.audit.audit_trails import AuditLogger
from app.security.input_validation.validators import validate_password_strength
from app.security.encryption.field_encryption import encrypt_sensitive_data
from app.logging.setup import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    get_current_user,
    get_current_active_user,
)
from app.security.captcha.verifier import verify_captcha


# Tạo function stub thay thế cho module thiếu
async def send_verification_email(email: str, username: str, user_id: str) -> None:
    """
    Stub function để thay thế app.email.email_service.send_verification_email

    Args:
        email: Email người dùng
        username: Tên người dùng
        user_id: ID người dùng để tạo token xác thực
    """
    logger = get_logger("email_service")
    logger.info(
        f"Gửi email xác thực đến {email} cho {username} với user_id {user_id[:8]}..."
    )
    # Trong môi trường thực tế, function này sẽ gửi email


settings = get_settings()
router = APIRouter()
metrics = Metrics()
audit_logger = AuditLogger()
logger = get_logger("auth_api")


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
@rate_limit(limit=10, period=60 * 60)  # 10 registration attempts per hour
async def register(
    request: Request,
    background_tasks: BackgroundTasks,
    user_data: RegisterRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with the provided details.

    Returns:
        A response with the user's ID and a success message.

    Raises:
        ValidationError: If the provided data fails validation.
        ClientException: If there's a client-related issue (e.g., user already exists).
        ServerException: If there's a server-related issue.
    """
    client_ip = request.client.host
    user_agent = request.headers.get("User-Agent", "Unknown")

    try:
        # Log the registration attempt
        logger.info(
            f"Registration attempt from IP: {client_ip}, User-Agent: {user_agent}, Email: {user_data.email}"
        )

        # Validate password strength
        is_valid, reason = validate_password_strength(user_data.password)
        if not is_valid:
            logger.warning(f"Password validation failed: {reason}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "error": {
                        "code": "weak_password",
                        "message": reason,
                        "details": {
                            "field": "password",
                            "validation_error": reason,
                            "requirements": {
                                "min_length": settings.PASSWORD_MIN_LENGTH,
                                "require_uppercase": settings.PASSWORD_REQUIRE_UPPERCASE,
                                "require_digits": settings.PASSWORD_REQUIRE_DIGITS,
                                "require_special": settings.PASSWORD_REQUIRE_SPECIAL,
                            },
                        },
                    },
                },
            )

        # Initialize services
        auth_service = AuthService(db)
        user_service = UserService(db)

        # Check if username or email already exists
        if await user_service.check_if_username_exists(user_data.username):
            logger.warning(f"Username already exists: {user_data.username}")
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "success": False,
                    "error": {
                        "code": "username_exists",
                        "message": f"Username '{user_data.username}' is already taken",
                        "details": {"field": "username", "value": user_data.username},
                    },
                },
            )

        if await user_service.check_if_email_exists(user_data.email):
            logger.warning(f"Email already exists: {user_data.email}")
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "success": False,
                    "error": {
                        "code": "email_exists",
                        "message": f"Email '{user_data.email}' is already registered",
                        "details": {"field": "email", "value": user_data.email},
                    },
                },
            )

        # Create user in database
        try:
            # Sử dụng context manager time_request
            with metrics.time_request("POST", "register_user"):
                # Sử dụng model_dump (với Pydantic v2) hoặc dict() (với Pydantic v1)
                try:
                    user_dict = user_data.model_dump()  # Pydantic v2
                except AttributeError:
                    user_dict = user_data.dict()  # Pydantic v1

                # Ghi log thông tin chuyển đổi để debug
                logger.debug(f"User registration data: {user_dict}")

                user = await auth_service.register_user(
                    UserCreate(**user_dict), client_ip=client_ip
                )

        except Exception as conversion_error:
            # Ghi log lỗi chuyển đổi dữ liệu cụ thể
            error_trace = traceback.format_exc()
            logger.error(
                f"Error converting registration data: {str(conversion_error)}\n{error_trace}",
                exc_info=True,
                extra={
                    "traceback": error_trace,
                    "user_data": str(user_data),
                },
            )
            # Re-raise để xử lý ở khối except bên ngoài
            raise

        # Log audit event
        audit_logger.log_user_activity(
            user_id=str(user.id),
            action="user_registration",
            details={
                "ip_address": client_ip,
                "user_agent": user_agent,
                "username": user.username,
                "email_domain": user.email.split("@")[-1],
            },
            severity="info",
        )

        # Send verification email in the background
        background_tasks.add_task(
            send_verification_email,
            email=user.email,
            username=user.username,
            user_id=str(user.id),
        )

        logger.info(f"User registered successfully: {user.username} (ID: {user.id})")

        # Return success response
        return {
            "success": True,
            "message": "User registered successfully. Please check your email to verify your account.",
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
            },
        }

    except ValidationError as e:
        # Handle validation errors
        error_details = []
        for error in e.errors():
            error_details.append(
                {
                    "field": error["loc"][-1] if error.get("loc") else "unknown",
                    "message": error["msg"],
                    "type": error["type"],
                }
            )

        logger.error(f"Validation error during registration: {error_details}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid input data",
                    "details": error_details,
                },
            },
        )

    except ClientException as e:
        logger.error(f"Client error during registration: {str(e)}")
        return JSONResponse(
            status_code=e.status_code,
            content={
                "success": False,
                "error": {
                    "code": e.error_code,
                    "message": str(e),
                    "details": e.details if hasattr(e, "details") else None,
                },
            },
        )

    except Exception as e:
        error_id = f"{time.time_ns()}"
        error_trace = traceback.format_exc()
        logger.critical(
            f"Unexpected error during registration: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={
                "traceback": error_trace,
                "error_id": error_id,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "exception": str(e),
            },
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": {
                    "code": "server_error",
                    "message": "An unexpected error occurred during registration",
                    "reference": f"Error ID: {error_id}",
                },
            },
        )


@router.post("/login", response_model=LoginResponse)
@rate_limit(limit=10, period=300)  # Giới hạn 10 lần đăng nhập/5 phút từ một IP
@metrics_track_request_time(endpoint="auth_login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Đăng nhập và lấy access token.
    """
    auth_service = AuthService(db)
    client_ip = request.client.host
    user_agent = request.headers.get("User-Agent", "")

    try:
        # Kiểm tra thông tin đăng nhập
        try:
            user, access_token, refresh_token = await auth_service.authenticate_user(
                username_or_email=form_data.username,
                password=form_data.password,
                ip_address=client_ip,
                user_agent=user_agent,
            )

            # Ghi log
            logger.info(f"Đăng nhập thành công: {user['id']} từ IP {client_ip}")

            # Track sự kiện
            track_auth_request(user["id"], True, "password")

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": user,
            }

        except UnauthorizedException as e:
            # Đăng nhập thất bại
            logger.warning(
                f"Đăng nhập thất bại cho {form_data.username} từ IP {client_ip}"
            )
            track_auth_request(None, False, "password")
            raise e

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(
            f"Lỗi đăng nhập: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={
                "username": form_data.username,
                "client_ip": client_ip,
                "traceback": error_trace,
            },
        )
        track_auth_request(None, False, "password")
        raise ServerException(detail="Lỗi đăng nhập, vui lòng thử lại sau")


@router.post("/verify-email", status_code=status.HTTP_200_OK)
@rate_limit(limit=10, period=300)  # Giới hạn 10 lần xác thực/5 phút từ một IP
@metrics_track_request_time(endpoint="auth_verify_email")
async def verify_email(
    request: Request, data: EmailVerificationRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Xác thực email người dùng.

    - Bảo mật: Giới hạn tốc độ yêu cầu xác thực
    - Audit: Ghi lại hành động xác thực
    """
    client_ip = request.client.host

    try:
        auth_service = AuthService(db)
        success = await auth_service.verify_email(data.token, ip_address=client_ip)

        if not success:
            # Ghi log thất bại
            await audit_logger.log_security_event(
                event_type="email_verification",
                ip_address=client_ip,
                user_agent=request.headers.get("User-Agent", ""),
                status="failure",
                details={"reason": "invalid_token"},
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token xác thực không hợp lệ hoặc đã hết hạn",
            )

        # Ghi log thành công
        await audit_logger.log_security_event(
            event_type="email_verification",
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
            status="success",
        )

        return {"message": "Xác thực email thành công"}
    except Exception as e:
        if not isinstance(e, HTTPException):
            # Ghi log lỗi hệ thống
            error_trace = traceback.format_exc()
            logger.error(
                f"Lỗi xác thực email: {str(e)}\n{error_trace}",
                exc_info=True,
                extra={
                    "client_ip": client_ip,
                    "token": "***",
                    "traceback": error_trace,
                },
            )

        # Re-raise exception
        raise


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@rate_limit(limit=5, period=3600)  # Giới hạn 5 yêu cầu/giờ từ một IP
@metrics_track_request_time(endpoint="auth_forgot_password")
async def forgot_password(
    request: Request, data: PasswordResetRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Yêu cầu đặt lại mật khẩu.

    - Bảo mật: Giới hạn tốc độ yêu cầu đặt lại mật khẩu
    - Bảo mật: Không tiết lộ thông tin tài khoản tồn tại hay không
    """
    client_ip = request.client.host

    try:
        auth_service = AuthService(db)
        success = await auth_service.request_password_reset(
            data.email, ip_address=client_ip
        )

        # Ghi log cho mục đích kiểm tra
        if success:
            await audit_logger.log_security_event(
                event_type="password_reset_request",
                ip_address=client_ip,
                user_agent=request.headers.get("User-Agent", ""),
                status="success",
                details={"email": encrypt_sensitive_data(data.email)},
            )
        else:
            await audit_logger.log_security_event(
                event_type="password_reset_request",
                ip_address=client_ip,
                user_agent=request.headers.get("User-Agent", ""),
                status="not_found",
                details={"email": encrypt_sensitive_data(data.email)},
            )

        # Luôn trả về thành công kể cả khi email không tồn tại để tránh rò rỉ thông tin
        return {
            "message": "Nếu email này đã đăng ký, chúng tôi đã gửi hướng dẫn đặt lại mật khẩu"
        }
    except Exception as e:
        # Ghi log lỗi hệ thống
        error_trace = traceback.format_exc()
        logger.error(
            f"Lỗi yêu cầu đặt lại mật khẩu: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={
                "client_ip": client_ip,
                "email": encrypt_sensitive_data(data.email),
                "traceback": error_trace,
            },
        )

        # Vẫn trả về thông báo thành công để tránh rò rỉ thông tin
        return {
            "message": "Nếu email này đã đăng ký, chúng tôi đã gửi hướng dẫn đặt lại mật khẩu"
        }


@router.post("/reset-password", status_code=status.HTTP_200_OK)
@rate_limit(limit=5, period=300)  # Giới hạn 5 yêu cầu/5 phút từ một IP
@metrics_track_request_time(endpoint="auth_reset_password")
async def reset_password(
    request: Request,
    data: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Đặt lại mật khẩu với token.

    - Bảo mật: Giới hạn tốc độ đặt lại mật khẩu
    - Validation: Kiểm tra độ mạnh của mật khẩu mới
    """
    client_ip = request.client.host

    # Kiểm tra độ mạnh của mật khẩu
    password_valid, reason = validate_password_strength(data.new_password)
    if not password_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=reason
            or "Mật khẩu không đủ mạnh. Cần ít nhất 8 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt.",
        )

    try:
        auth_service = AuthService(db)
        success = await auth_service.reset_password(
            data.token, data.new_password, ip_address=client_ip
        )

        if not success:
            # Ghi log thất bại
            await audit_logger.log_security_event(
                event_type="password_reset",
                ip_address=client_ip,
                user_agent=request.headers.get("User-Agent", ""),
                status="failure",
                details={"reason": "invalid_token"},
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token đặt lại mật khẩu không hợp lệ hoặc đã hết hạn",
            )

        # Ghi log thành công
        await audit_logger.log_security_event(
            event_type="password_reset",
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
            status="success",
        )

        return {"message": "Đặt lại mật khẩu thành công"}
    except Exception as e:
        if not isinstance(e, HTTPException):
            # Ghi log lỗi hệ thống
            error_trace = traceback.format_exc()
            logger.error(
                f"Lỗi đặt lại mật khẩu: {str(e)}\n{error_trace}",
                exc_info=True,
                extra={
                    "client_ip": client_ip,
                    "token": "***",
                    "traceback": error_trace,
                },
            )

        # Re-raise exception
        raise


@router.post("/refresh-token", response_model=LoginResponse)
@rate_limit(limit=20, period=300)  # Giới hạn 20 lần refresh/5 phút từ một IP
@metrics_track_request_time(endpoint="auth_refresh_token")
async def refresh_token(
    request: Request,
    data: Dict[str, str] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Làm mới token JWT khi token hiện tại hết hạn.

    - Bảo mật: Giới hạn tốc độ refresh token
    - Audit: Ghi lại hoạt động refresh token
    """
    client_ip = request.client.host
    user_agent = request.headers.get("User-Agent", "")

    if "refresh_token" not in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token là bắt buộc"
        )

    try:
        auth_service = AuthService(db)
        user, access_token, refresh_token = await auth_service.refresh_tokens(
            data["refresh_token"], ip_address=client_ip, user_agent=user_agent
        )

        # Ghi log thành công
        await audit_logger.log_security_event(
            event_type="token_refresh",
            user_id=user["id"],
            username=user["username"],
            ip_address=client_ip,
            user_agent=user_agent,
            status="success",
        )

        # Đo lường token refresh
        metrics.track_token_refresh(success=True)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "refresh_token": refresh_token,
            "user": user,
        }
    except Exception as e:
        # Ghi log lỗi hệ thống
        error_trace = traceback.format_exc()
        logger.error(
            f"Lỗi refresh token: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={"client_ip": client_ip, "traceback": error_trace},
        )

        # Ghi log audit
        await audit_logger.log_security_event(
            event_type="token_refresh",
            ip_address=client_ip,
            user_agent=user_agent,
            status="failure",
            details={"error": str(e), "traceback": error_trace},
        )

        # Đo lường token refresh thất bại
        metrics.track_token_refresh(success=False, reason=str(e))

        # Re-raise exception
        raise


@router.post("/2fa/verify", response_model=LoginResponse)
@rate_limit(limit=5, period=60)  # Giới hạn 5 lần thử/phút
@metrics_track_request_time(endpoint="auth_2fa_verify")
async def verify_2fa(
    request: Request,
    data: TwoFactorVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Xác thực mã hai yếu tố (2FA) và hoàn tất đăng nhập.
    """
    auth_service = AuthService(db)
    client_ip = request.client.host
    user_agent = request.headers.get("User-Agent", "")

    try:
        # Xác thực mã 2FA
        user, access_token, refresh_token = await auth_service.verify_2fa(
            temp_token=data.temp_token,
            code=data.code,
            ip_address=client_ip,
            user_agent=user_agent,
        )

        # Ghi log
        logger.info(f"Xác thực 2FA thành công: {user['id']} từ IP {client_ip}")
        track_auth_request(user["id"], True, "2fa")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": user,
        }

    except UnauthorizedException as e:
        logger.warning(f"Xác thực 2FA thất bại từ IP {client_ip}")
        track_auth_request(None, False, "2fa")
        raise e
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(
            f"Lỗi xác thực 2FA: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={"client_ip": client_ip, "traceback": error_trace},
        )
        track_auth_request(None, False, "2fa")
        raise ServerException(detail="Lỗi xác thực, vui lòng thử lại sau")


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
@metrics_track_request_time(endpoint="auth_2fa_setup")
async def setup_2fa(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Thiết lập xác thực hai yếu tố (2FA) cho tài khoản.
    """
    user_service = UserService(db)

    try:
        # Tạo secret key và QR code URL
        secret, qr_code_url = await user_service.generate_2fa_setup(current_user.id)

        # Ghi log
        logger.info(f"User {current_user.id} đang thiết lập 2FA")

        return {
            "secret": secret,
            "qr_code_url": qr_code_url,
            "message": "Quét mã QR bằng ứng dụng xác thực như Google Authenticator",
        }

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(
            f"Lỗi thiết lập 2FA: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={"user_id": current_user.id, "traceback": error_trace},
        )
        raise ServerException(
            detail="Lỗi thiết lập xác thực hai yếu tố, vui lòng thử lại sau"
        )


@router.post("/2fa/enable", status_code=status.HTTP_200_OK)
@metrics_track_request_time(endpoint="auth_2fa_enable")
async def enable_2fa(
    request: Request,
    data: TwoFactorEnableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Xác nhận và bật xác thực hai yếu tố (2FA) cho tài khoản.
    """
    user_service = UserService(db)

    try:
        # Xác thực mã và bật 2FA
        success = await user_service.enable_2fa(user_id=current_user.id, code=data.code)

        if not success:
            raise BadRequestException(
                detail="Mã xác thực không đúng", code="invalid_code"
            )

        # Ghi log
        logger.info(f"User {current_user.id} đã bật 2FA thành công")

        # Tạo mã backup để khôi phục khi mất thiết bị
        backup_codes = await user_service.generate_2fa_backup_codes(current_user.id)

        return {
            "message": "Đã bật xác thực hai yếu tố thành công",
            "backup_codes": backup_codes,
        }

    except HTTPException:
        raise
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(
            f"Lỗi bật 2FA: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={"user_id": current_user.id, "traceback": error_trace},
        )
        raise ServerException(
            detail="Lỗi bật xác thực hai yếu tố, vui lòng thử lại sau"
        )


@router.post("/2fa/disable", status_code=status.HTTP_200_OK)
@metrics_track_request_time(endpoint="auth_2fa_disable")
async def disable_2fa(
    request: Request,
    data: TwoFactorDisableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Tắt xác thực hai yếu tố (2FA) cho tài khoản.
    """
    user_service = UserService(db)

    try:
        # Yêu cầu xác thực mật khẩu để tắt 2FA
        if not verify_password(data.password, current_user.hashed_password):
            raise UnauthorizedException(detail="Mật khẩu không đúng")

        # Tắt 2FA
        await user_service.disable_2fa(current_user.id)

        # Ghi log
        logger.info(f"User {current_user.id} đã tắt 2FA")

        return {"message": "Đã tắt xác thực hai yếu tố thành công"}

    except HTTPException:
        raise
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(
            f"Lỗi tắt 2FA: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={"user_id": current_user.id, "traceback": error_trace},
        )
        raise ServerException(
            detail="Lỗi tắt xác thực hai yếu tố, vui lòng thử lại sau"
        )


@router.post("/logout", status_code=status.HTTP_200_OK)
@metrics_track_request_time(endpoint="auth_logout")
async def logout(
    request: Request,
    data: Dict[str, str] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Đăng xuất người dùng và vô hiệu hóa token.
    """
    user_service = UserService(db)
    client_ip = request.client.host

    try:
        token = data.get("token", "")
        if not token and request.headers.get("Authorization"):
            auth_header = request.headers.get("Authorization")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if token:
            # Thêm token vào blacklist
            await user_service.blacklist_token(token)

        # Ghi log
        logger.info(f"User {current_user.id} đăng xuất từ IP {client_ip}")

        return {"message": "Đăng xuất thành công"}

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(
            f"Lỗi đăng xuất: {str(e)}\n{error_trace}",
            exc_info=True,
            extra={
                "user_id": current_user.id,
                "client_ip": client_ip,
                "traceback": error_trace,
            },
        )
        raise ServerException(detail="Lỗi đăng xuất, vui lòng thử lại sau")
