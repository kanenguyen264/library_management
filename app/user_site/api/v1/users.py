from typing import Any, List, Optional, Dict
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Path,
    Query,
    Request,
    Body,
    UploadFile,
    File,
    Form,
)
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
import time

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_premium_user,
)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserPublicResponse,
    UserPasswordUpdate,
    UserProfileResponse,
    UserStatsResponse,
    UserPreferencesUpdate,
    UserActivityResponse,
    UserSecuritySettings,
)
from app.user_site.services.user_service import UserService
from app.user_site.services.preference_service import PreferenceService
from app.user_site.services.auth_service import AuthService
from app.security.password import check_password_strength, verify_password
from app.security.jwt import decode_token
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import (
    log_auth_success,
    log_auth_failure,
    log_data_operation,
)
from app.core.exceptions import (
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    ServerException,
)
from app.security.access_control.rbac import check_permission

router = APIRouter()
logger = get_logger("user_api")


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_user")
async def create_user(
    user_data: UserCreate, request: Request, db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Tạo người dùng mới (Đăng ký).

    * Yêu cầu mật khẩu mạnh
    * Email phải là duy nhất
    * Username phải là duy nhất
    """
    # Kiểm tra mật khẩu mạnh
    password_valid, reason = check_password_strength(user_data.password)
    if not password_valid:
        raise BadRequestException(detail=reason, field="password", code="weak_password")

    # Kiểm tra mật khẩu xác nhận
    if user_data.password != user_data.password_confirm:
        raise BadRequestException(
            detail="Mật khẩu xác nhận không khớp",
            field="password_confirm",
            code="password_mismatch",
        )

    # Rate limiting để ngăn chặn đăng ký hàng loạt
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "")

    user_service = UserService(db)
    auth_service = AuthService(db)

    try:
        # Kiểm tra email và username đã tồn tại chưa
        if await user_service.get_by_email(user_data.email):
            raise ConflictException(
                detail="Email đã được sử dụng", field="email", code="email_exists"
            )

        if await user_service.get_by_username(user_data.username):
            raise ConflictException(
                detail="Tên đăng nhập đã được sử dụng",
                field="username",
                code="username_exists",
            )

        # Tạo người dùng mới
        user = await user_service.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name,
        )

        # Tạo verification token
        verification_token = await auth_service.create_email_verification_token(user.id)

        # Gửi email xác thực (phần này sẽ được xử lý trong service)
        await auth_service.send_verification_email(user.email, verification_token)

        # Ghi log
        logger.info(
            f"Tạo người dùng mới thành công: {user.id}, {user.email}, IP: {client_ip}"
        )

        # Ghi log audit
        await log_data_operation(
            operation="create",
            resource_type="user",
            resource_id=str(user.id),
            user_id=str(user.id),
            user_type="user",
            status="success",
            ip_address=client_ip,
            user_agent=user_agent,
        )

        return user
    except ConflictException:
        raise
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo người dùng mới: {str(e)}")
        raise ServerException(detail="Lỗi khi đăng ký tài khoản, vui lòng thử lại sau")


@router.get("/me", response_model=UserResponse)
@track_request_time(endpoint="get_current_user")
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Lấy thông tin người dùng hiện tại.

    * Trả về thông tin chi tiết của tài khoản đang đăng nhập
    * Endpoint này cần JWT token hợp lệ
    """
    return current_user


@router.put("/me", response_model=UserResponse)
@track_request_time(endpoint="update_current_user")
@invalidate_cache(namespace="users", tags=["user_profile"])
async def update_current_user(
    data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Cập nhật thông tin người dùng hiện tại.

    * Chỉ cho phép cập nhật các thông tin cơ bản
    * Không cho phép cập nhật email và username
    """
    user_service = UserService(db)

    # Thông tin client
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "")

    # Validate dữ liệu đầu vào
    if data.email and data.email != current_user.email:
        raise BadRequestException(
            detail="Không thể thay đổi email qua API này, vui lòng sử dụng tính năng thay đổi email",
            field="email",
            code="email_change_not_allowed",
        )

    try:
        # Chỉ lấy các trường đã được thiết lập
        update_data = data.model_dump(exclude_unset=True, exclude={"email", "username"})

        # Nếu không có dữ liệu để cập nhật
        if not update_data:
            return current_user

        # Cập nhật thông tin
        updated_user = await user_service.update_user(
            user_id=current_user.id, update_data=update_data
        )

        # Ghi log audit
        await log_data_operation(
            operation="update",
            resource_type="user",
            resource_id=str(current_user.id),
            user_id=str(current_user.id),
            user_type="user",
            status="success",
            ip_address=client_ip,
            user_agent=user_agent,
            changes=update_data,
        )

        return updated_user
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật người dùng: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật thông tin tài khoản")


@router.put("/me/password", response_model=Dict[str, Any])
@track_request_time(endpoint="update_current_user_password")
async def update_current_user_password(
    data: UserPasswordUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Cập nhật mật khẩu người dùng hiện tại.

    * Yêu cầu mật khẩu hiện tại chính xác
    * Mật khẩu mới phải đủ mạnh (kết hợp chữ hoa, chữ thường, số, ký tự đặc biệt)
    * Mật khẩu mới không được trùng với mật khẩu hiện tại
    """
    # Giới hạn số lần đổi mật khẩu
    await throttle_requests(
        "change_password",
        limit=5,
        period=3600,
        request=request,
        current_user=current_user,
        db=db,
    )

    # Kiểm tra mật khẩu mới có đủ mạnh không
    password_valid, reason = check_password_strength(data.new_password)
    if not password_valid:
        raise BadRequestException(
            detail=reason, field="new_password", code="weak_password"
        )

    # Kiểm tra mật khẩu xác nhận
    if data.new_password != data.new_password_confirm:
        raise BadRequestException(
            detail="Mật khẩu xác nhận không khớp",
            field="new_password_confirm",
            code="password_mismatch",
        )

    user_service = UserService(db)
    auth_service = AuthService(db)

    # Thông tin client
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "")

    try:
        # Kiểm tra mật khẩu hiện tại
        if not verify_password(data.current_password, current_user.hashed_password):
            # Ghi log thất bại
            await log_auth_failure(
                username=current_user.username,
                ip_address=client_ip,
                reason="incorrect_password",
                user_agent=user_agent,
                details={"action": "change_password"},
            )

            raise UnauthorizedException(
                detail="Mật khẩu hiện tại không đúng", code="incorrect_password"
            )

        # Kiểm tra mật khẩu mới có giống mật khẩu cũ không
        if verify_password(data.new_password, current_user.hashed_password):
            raise BadRequestException(
                detail="Mật khẩu mới không được trùng với mật khẩu hiện tại",
                field="new_password",
                code="same_password",
            )

        # Thay đổi mật khẩu
        success = await user_service.change_password(
            user_id=current_user.id, new_password=data.new_password
        )

        if not success:
            raise ServerException(detail="Lỗi khi cập nhật mật khẩu")

        # Vô hiệu hóa tất cả token hiện tại (ngoại trừ token hiện tại)
        if data.logout_all_devices:
            current_token = request.headers.get("Authorization", "").replace(
                "Bearer ", ""
            )
            await auth_service.invalidate_all_tokens(
                current_user.id, exclude_token=current_token
            )

        # Ghi log audit
        await log_data_operation(
            operation="change_password",
            resource_type="user",
            resource_id=str(current_user.id),
            user_id=str(current_user.id),
            user_type="user",
            status="success",
            ip_address=client_ip,
            user_agent=user_agent,
        )

        # Ghi log thành công
        await log_auth_success(
            user_id=str(current_user.id),
            user_type="user",
            ip_address=client_ip,
            user_agent=user_agent,
            details={"action": "change_password"},
        )

        return {"success": True, "message": "Mật khẩu đã được cập nhật thành công"}
    except UnauthorizedException:
        raise
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật mật khẩu: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật mật khẩu")


@router.post("/me/email-change", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="request_email_change")
async def request_email_change(
    data: Dict[str, str] = Body(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Yêu cầu thay đổi địa chỉ email.

    * Gửi email xác nhận đến địa chỉ email mới
    * Cần nhập mật khẩu để xác thực
    """
    # Giới hạn số lần yêu cầu đổi email
    await throttle_requests(
        "request_email_change",
        limit=3,
        period=3600,
        request=request,
        current_user=current_user,
        db=db,
    )

    # Validate đầu vào
    new_email = data.get("new_email")
    password = data.get("password")

    if not new_email:
        raise BadRequestException(
            detail="Vui lòng cung cấp email mới", field="new_email"
        )

    if not password:
        raise BadRequestException(detail="Vui lòng cung cấp mật khẩu", field="password")

    # Thông tin client
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "")

    user_service = UserService(db)
    auth_service = AuthService(db)

    try:
        # Kiểm tra email mới có hợp lệ không
        if new_email == current_user.email:
            raise BadRequestException(
                detail="Email mới không được trùng với email hiện tại",
                field="new_email",
            )

        # Kiểm tra email đã tồn tại chưa
        if await user_service.get_by_email(new_email):
            raise ConflictException(
                detail="Email đã được sử dụng bởi tài khoản khác", field="new_email"
            )

        # Kiểm tra mật khẩu
        if not verify_password(password, current_user.hashed_password):
            raise UnauthorizedException(detail="Mật khẩu không đúng")

        # Tạo token thay đổi email
        token = await auth_service.create_email_change_token(
            user_id=current_user.id, new_email=new_email
        )

        # Gửi email xác nhận
        await auth_service.send_email_change_verification(
            current_email=current_user.email, new_email=new_email, token=token
        )

        # Ghi log
        logger.info(
            f"Yêu cầu thay đổi email: {current_user.id}, {current_user.email} -> {new_email}"
        )

        return {
            "success": True,
            "message": "Đã gửi email xác nhận đến địa chỉ email mới. Vui lòng kiểm tra hộp thư để hoàn tất thay đổi email.",
        }
    except BadRequestException:
        raise
    except ConflictException:
        raise
    except UnauthorizedException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi yêu cầu thay đổi email: {str(e)}")
        raise ServerException(detail="Lỗi khi yêu cầu thay đổi email")


@router.post("/me/avatar", response_model=Dict[str, Any])
@track_request_time(endpoint="upload_avatar")
@invalidate_cache(namespace="users", tags=["user_profile"])
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Tải lên hình đại diện mới cho người dùng.

    * Hỗ trợ file hình ảnh (JPEG, PNG, GIF)
    * Kích thước file tối đa 2MB
    """
    # Giới hạn số lần tải lên avatar
    await throttle_requests(
        "upload_avatar",
        limit=10,
        period=3600,
        request=request,
        current_user=current_user,
        db=db,
    )

    # Thông tin client
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "")

    user_service = UserService(db)

    try:
        # Kiểm tra loại file
        content_type = file.content_type
        if not content_type or not content_type.startswith("image/"):
            raise BadRequestException(
                detail="Chỉ chấp nhận file hình ảnh (JPEG, PNG, GIF)", field="file"
            )

        # Kiểm tra kích thước file (2MB)
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        # Reset file pointer về đầu
        await file.seek(0)

        # Đọc từng chunk và đếm kích thước
        chunk = await file.read(chunk_size)
        file_size += len(chunk)

        if file_size > 2 * 1024 * 1024:  # 2MB
            raise BadRequestException(
                detail="Kích thước file tối đa là 2MB", field="file"
            )

        # Reset file pointer về đầu
        await file.seek(0)

        # Tải lên hình đại diện
        avatar_url = await user_service.upload_avatar(
            user_id=current_user.id, file=file, content_type=content_type
        )

        # Ghi log
        logger.info(f"Tải lên avatar mới: {current_user.id}")

        # Ghi log audit
        await log_data_operation(
            operation="upload_avatar",
            resource_type="user",
            resource_id=str(current_user.id),
            user_id=str(current_user.id),
            user_type="user",
            status="success",
            ip_address=client_ip,
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "Tải lên hình đại diện thành công",
            "avatar_url": avatar_url,
        }
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tải lên avatar: {str(e)}")
        raise ServerException(detail="Lỗi khi tải lên hình đại diện")


@router.get("/me/preferences", response_model=Dict[str, Any])
@track_request_time(endpoint="get_user_preferences")
@cache_response(ttl=300, vary_by=["current_user.id"])
async def get_user_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Lấy thông tin tùy chọn của người dùng.

    * Trả về các tùy chọn người dùng như giao diện, thông báo, v.v.
    """
    preference_service = PreferenceService(db)

    try:
        preferences = await preference_service.get_user_preferences(current_user.id)
        return preferences
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin tùy chọn: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin tùy chọn")


@router.put("/me/preferences", response_model=Dict[str, Any])
@track_request_time(endpoint="update_user_preferences")
@invalidate_cache(namespace="users", tags=["user_preferences"])
async def update_user_preferences(
    data: UserPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Cập nhật tùy chọn của người dùng.

    * Cập nhật các tùy chọn như giao diện, thông báo, v.v.
    """
    preference_service = PreferenceService(db)

    # Thông tin client
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "")

    try:
        # Chỉ lấy các trường đã được thiết lập
        update_data = data.model_dump(exclude_unset=True)

        # Nếu không có dữ liệu để cập nhật
        if not update_data:
            preferences = await preference_service.get_user_preferences(current_user.id)
            return preferences

        # Cập nhật tùy chọn
        updated_preferences = await preference_service.update_user_preferences(
            user_id=current_user.id, preferences=update_data
        )

        # Ghi log audit
        await log_data_operation(
            operation="update_preferences",
            resource_type="user_preferences",
            resource_id=str(current_user.id),
            user_id=str(current_user.id),
            user_type="user",
            status="success",
            ip_address=client_ip,
            user_agent=user_agent,
            changes=update_data,
        )

        return updated_preferences
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật tùy chọn: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật tùy chọn")


@router.get("/me/stats", response_model=UserStatsResponse)
@track_request_time(endpoint="get_user_stats")
@cache_response(ttl=300, vary_by=["current_user.id"])
async def get_user_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UserStatsResponse:
    """
    Lấy thống kê người dùng.

    * Số sách đã đọc
    * Số trang đã đọc
    * Số phút đã đọc
    * Số bình luận, đánh giá
    * v.v.
    """
    user_service = UserService(db)

    try:
        stats = await user_service.get_user_stats(current_user.id)
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê người dùng: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thống kê người dùng")


@router.get("/me/activity", response_model=List[UserActivityResponse])
@track_request_time(endpoint="get_user_activity")
@cache_response(ttl=300, vary_by=["current_user.id", "limit", "offset"])
async def get_user_activity(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[UserActivityResponse]:
    """
    Lấy lịch sử hoạt động của người dùng.

    * Sách đã đọc gần đây
    * Đánh giá, bình luận gần đây
    * v.v.
    """
    user_service = UserService(db)

    try:
        activities = await user_service.get_user_activity(
            user_id=current_user.id, limit=limit, offset=offset
        )
        return activities
    except Exception as e:
        logger.error(f"Lỗi khi lấy lịch sử hoạt động: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy lịch sử hoạt động")


@router.get("/me/security", response_model=UserSecuritySettings)
@track_request_time(endpoint="get_security_settings")
async def get_security_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UserSecuritySettings:
    """
    Lấy cài đặt bảo mật của người dùng.

    * Trạng thái 2FA
    * Phiên đăng nhập hiện tại
    * v.v.
    """
    auth_service = AuthService(db)

    try:
        # Lấy danh sách các phiên đăng nhập
        sessions = await auth_service.get_active_sessions(current_user.id)

        return {
            "two_factor_enabled": current_user.is_2fa_enabled,
            "active_sessions": len(sessions),
            "sessions": sessions,
            "last_password_change": current_user.password_changed_at,
            "account_created_at": current_user.created_at,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy cài đặt bảo mật: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy cài đặt bảo mật")


@router.post("/me/sessions/revoke", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="revoke_sessions")
async def revoke_sessions(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Hủy các phiên đăng nhập.

    * Có thể hủy tất cả phiên ngoại trừ phiên hiện tại
    * Hoặc hủy một phiên cụ thể
    """
    auth_service = AuthService(db)

    # Thông tin client
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "")

    # Lấy token hiện tại từ header
    current_token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        current_token = auth_header[7:]

    try:
        session_id = data.get("session_id")
        revoke_all = data.get("revoke_all", False)

        if revoke_all:
            # Hủy tất cả phiên trừ phiên hiện tại
            count = await auth_service.invalidate_all_tokens(
                user_id=current_user.id, exclude_token=current_token
            )

            # Ghi log audit
            await log_data_operation(
                operation="revoke_all_sessions",
                resource_type="user_sessions",
                resource_id=str(current_user.id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
            )

            return {
                "success": True,
                "message": f"Đã hủy {count} phiên đăng nhập",
                "revoked_count": count,
            }
        elif session_id:
            # Hủy một phiên cụ thể
            success = await auth_service.invalidate_session(
                user_id=current_user.id, session_id=session_id
            )

            if not success:
                raise BadRequestException(detail="Không thể hủy phiên đăng nhập này")

            # Ghi log audit
            await log_data_operation(
                operation="revoke_session",
                resource_type="user_session",
                resource_id=session_id,
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
            )

            return {
                "success": True,
                "message": "Đã hủy phiên đăng nhập thành công",
                "session_id": session_id,
            }
        else:
            raise BadRequestException(
                detail="Vui lòng cung cấp session_id hoặc đặt revoke_all = true"
            )

    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi hủy phiên đăng nhập: {str(e)}")
        raise ServerException(detail="Lỗi khi hủy phiên đăng nhập")


@router.get("/{user_id}", response_model=UserPublicResponse)
@track_request_time(endpoint="get_user")
@cache_response(ttl=300, vary_by=["user_id"])
async def get_user(
    user_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Lấy thông tin công khai của người dùng theo ID.

    * Chỉ trả về thông tin công khai của người dùng
    * Không yêu cầu đăng nhập
    """
    user_service = UserService(db)

    try:
        user = await user_service.get_user(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID: {user_id}",
                code="user_not_found",
            )
        return user
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin người dùng: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin người dùng")


@router.get("/{user_id}/profile", response_model=UserProfileResponse)
@track_request_time(endpoint="get_user_profile")
@cache_response(ttl=300, vary_by=["user_id"])
async def get_user_profile(
    user_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)
) -> UserProfileResponse:
    """
    Lấy thông tin hồ sơ công khai của người dùng.

    * Bao gồm thông tin cơ bản và các thông tin bổ sung
    * Không yêu cầu đăng nhập
    """
    user_service = UserService(db)

    try:
        profile = await user_service.get_user_profile(user_id)
        if not profile:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID: {user_id}",
                code="user_not_found",
            )
        return profile
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy hồ sơ người dùng: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy hồ sơ người dùng")


@router.get("/", response_model=List[UserPublicResponse])
@track_request_time(endpoint="list_users")
@cache_response(ttl=300, vary_by=["skip", "limit", "search"])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=2),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Lấy danh sách người dùng (chỉ thông tin công khai).

    * Phân trang với skip và limit
    * Tìm kiếm theo username hoặc full_name
    """
    user_service = UserService(db)

    try:
        users = await user_service.list_users(skip=skip, limit=limit, search=search)
        return users
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách người dùng: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách người dùng")
