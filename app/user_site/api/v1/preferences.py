from typing import Dict, Any, Optional, List
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Request,
    Query,
    Path,
    Body,
)
from app.user_site.api.v1 import throttle_requests
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_active_user
from app.user_site.models.user import User
from app.user_site.schemas.preference import (
    UserPreferenceResponse,
    UserPreferenceUpdate,
    ReadingPreferenceResponse,
    ThemePreferenceResponse,
    NotificationPreferenceResponse,
    PrivacyPreferenceResponse,
    DeviceSyncRequest,
    DeviceSyncResponse,
)
from app.user_site.services.preference_service import PreferenceService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import NotFoundException, BadRequestException, ServerException

router = APIRouter()
logger = get_logger("preferences_api")
audit_logger = AuditLogger()


@router.get("/", response_model=UserPreferenceResponse)
@track_request_time(endpoint="get_user_preferences")
@cache_response(ttl=600, vary_by=["current_user.id"])
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy tùy chọn người dùng hiện tại.

    Trả về tất cả tùy chọn của người dùng bao gồm giao diện, ngôn ngữ,
    tùy chọn đọc sách và các cài đặt khác. Nếu người dùng chưa có tùy chọn,
    sẽ trả về tùy chọn mặc định.
    """
    preference_service = PreferenceService(db)

    try:
        preferences = await preference_service.get_user_preferences(current_user.id)

        if not preferences:
            # Trả về tùy chọn mặc định nếu chưa có
            default_preferences = await preference_service.get_default_preferences()
            default_preferences["user_id"] = current_user.id
            return default_preferences

        return preferences
    except Exception as e:
        logger.error(f"Lỗi khi lấy tùy chọn người dùng {current_user.id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy tùy chọn người dùng")


@router.put("/", response_model=UserPreferenceResponse)
@track_request_time(endpoint="update_user_preferences")
@invalidate_cache(namespace="preferences", tags=["user_preferences"])
async def update_preferences(
    data: UserPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật tùy chọn người dùng.

    Cho phép cập nhật tất cả hoặc một phần tùy chọn. Các tùy chọn không được chỉ định
    sẽ giữ nguyên giá trị hiện tại.
    """
    preference_service = PreferenceService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật tùy chọn người dùng - User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Giới hạn tốc độ cập nhật tùy chọn
        await throttle_requests(
            "update_preferences",
            limit=20,
            period=60,
            current_user=current_user,
            request=request,
            db=db,
        )

        updated_preferences = await preference_service.update_user_preferences(
            user_id=current_user.id, data=data.model_dump(exclude_unset=True)
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "preferences_update",
            f"Người dùng đã cập nhật tùy chọn",
            metadata={"user_id": current_user.id},
        )

        return updated_preferences
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật tùy chọn người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi cập nhật tùy chọn người dùng")


@router.get("/reading", response_model=ReadingPreferenceResponse)
@track_request_time(endpoint="get_reading_preferences")
@cache_response(ttl=600, vary_by=["current_user.id"])
async def get_reading_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy tùy chọn đọc sách của người dùng hiện tại.

    Bao gồm tùy chọn font chữ, cỡ chữ, khoảng cách dòng, theme đọc sách và các
    tùy chọn đồng bộ vị trí đọc.
    """
    preference_service = PreferenceService(db)

    try:
        preferences = await preference_service.get_user_preferences(current_user.id)

        # Trả về các cài đặt liên quan đến đọc sách
        if not preferences:
            # Trả về tùy chọn mặc định nếu chưa có
            default_reading = await preference_service.get_default_reading_preferences()
            return default_reading

        reading_preferences = {
            "reading_font": preferences.reading_font,
            "reading_font_size": preferences.reading_font_size,
            "reading_line_spacing": preferences.reading_line_spacing,
            "reading_theme": preferences.reading_theme,
            "text_alignment": preferences.get("text_alignment", "left"),
            "margins": preferences.get("margins", "normal"),
            "auto_scroll_speed": preferences.get("auto_scroll_speed", "medium"),
            "page_transition": preferences.get("page_transition", "slide"),
            "orientation_lock": preferences.get("orientation_lock", False),
            "keep_screen_on": preferences.get("keep_screen_on", True),
            "sync_reading_position": preferences.sync_reading_position,
        }

        return reading_preferences
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy tùy chọn đọc sách của người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy tùy chọn đọc sách")


@router.put("/reading", response_model=ReadingPreferenceResponse)
@track_request_time(endpoint="update_reading_preferences")
@invalidate_cache(namespace="preferences", tags=["reading_preferences"])
async def update_reading_preferences(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật tùy chọn đọc sách.

    Cho phép cập nhật các tùy chọn liên quan đến trải nghiệm đọc sách
    mà không làm thay đổi các tùy chọn khác.
    """
    preference_service = PreferenceService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật tùy chọn đọc sách - User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Xác thực các giá trị đầu vào
        reading_fields = [
            "reading_font",
            "reading_font_size",
            "reading_line_spacing",
            "reading_theme",
            "text_alignment",
            "margins",
            "auto_scroll_speed",
            "page_transition",
            "orientation_lock",
            "keep_screen_on",
            "sync_reading_position",
        ]

        # Chỉ lấy các trường liên quan đến đọc sách
        validated_data = {k: v for k, v in data.items() if k in reading_fields}

        if not validated_data:
            raise BadRequestException(
                detail="Không có dữ liệu tùy chọn đọc sách hợp lệ được cung cấp",
                code="invalid_reading_preferences",
            )

        updated_preferences = await preference_service.update_user_preferences(
            user_id=current_user.id, data=validated_data
        )

        # Trích xuất và trả về chỉ các tùy chọn đọc sách
        reading_response = {
            "reading_font": updated_preferences.reading_font,
            "reading_font_size": updated_preferences.reading_font_size,
            "reading_line_spacing": updated_preferences.reading_line_spacing,
            "reading_theme": updated_preferences.reading_theme,
            "text_alignment": updated_preferences.get("text_alignment", "left"),
            "margins": updated_preferences.get("margins", "normal"),
            "auto_scroll_speed": updated_preferences.get("auto_scroll_speed", "medium"),
            "page_transition": updated_preferences.get("page_transition", "slide"),
            "orientation_lock": updated_preferences.get("orientation_lock", False),
            "keep_screen_on": updated_preferences.get("keep_screen_on", True),
            "sync_reading_position": updated_preferences.sync_reading_position,
        }

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "reading_preferences_update",
            f"Người dùng đã cập nhật tùy chọn đọc sách",
            metadata={"user_id": current_user.id},
        )

        return reading_response
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật tùy chọn đọc sách cho người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi cập nhật tùy chọn đọc sách")


@router.get("/themes", response_model=List[ThemePreferenceResponse])
@track_request_time(endpoint="get_available_themes")
@cache_response(ttl=86400)  # Cache 24 giờ
async def get_available_themes(
    type: str = Query(
        "app", regex="^(app|reading)$", description="Loại theme (app hoặc reading)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các theme có sẵn trong hệ thống.

    - **type**: Loại theme (app hoặc reading)
      - app: Theme cho giao diện ứng dụng
      - reading: Theme cho chế độ đọc sách
    """
    preference_service = PreferenceService(db)

    try:
        themes = await preference_service.get_available_themes(type)
        return themes
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách theme có sẵn: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách theme có sẵn")


@router.get("/theme/{theme_id}", response_model=ThemePreferenceResponse)
@track_request_time(endpoint="get_theme_details")
@cache_response(ttl=86400)  # Cache 24 giờ
async def get_theme_details(
    theme_id: str = Path(..., description="ID của theme"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin chi tiết của một theme.

    Bao gồm thông tin về tên, mô tả, loại theme, bảng màu, và tùy chọn khác.
    """
    preference_service = PreferenceService(db)

    try:
        theme = await preference_service.get_theme_by_id(theme_id)

        if not theme:
            raise NotFoundException(
                detail=f"Không tìm thấy theme với ID: {theme_id}",
                code="theme_not_found",
            )

        return theme
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin theme {theme_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin theme")


@router.get("/notification", response_model=NotificationPreferenceResponse)
@track_request_time(endpoint="get_notification_preferences")
@cache_response(ttl=600, vary_by=["current_user.id"])
async def get_notification_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy tùy chọn thông báo của người dùng hiện tại.

    Bao gồm các tùy chọn về loại thông báo, phương thức nhận thông báo và tần suất.
    """
    preference_service = PreferenceService(db)

    try:
        preferences = await preference_service.get_user_preferences(current_user.id)

        if not preferences or not hasattr(preferences, "notification_settings"):
            # Trả về tùy chọn mặc định nếu chưa có
            default_notification = (
                await preference_service.get_default_notification_preferences()
            )
            return default_notification

        return preferences.notification_settings
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy tùy chọn thông báo của người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy tùy chọn thông báo")


@router.put("/notification", response_model=NotificationPreferenceResponse)
@track_request_time(endpoint="update_notification_preferences")
@invalidate_cache(namespace="preferences", tags=["notification_preferences"])
async def update_notification_preferences(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật tùy chọn thông báo.

    Cho phép cập nhật các tùy chọn về loại thông báo, phương thức nhận thông báo,
    và tần suất mà không làm thay đổi các tùy chọn khác.
    """
    preference_service = PreferenceService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật tùy chọn thông báo - User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Xác thực dữ liệu đầu vào
        if not data:
            raise BadRequestException(
                detail="Không có dữ liệu tùy chọn thông báo được cung cấp",
                code="invalid_notification_preferences",
            )

        # Cập nhật chỉ phần notification_settings
        notification_settings = {"notification_settings": data}

        updated_preferences = await preference_service.update_user_preferences(
            user_id=current_user.id, data=notification_settings
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "notification_preferences_update",
            f"Người dùng đã cập nhật tùy chọn thông báo",
            metadata={"user_id": current_user.id},
        )

        return updated_preferences.notification_settings
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật tùy chọn thông báo cho người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi cập nhật tùy chọn thông báo")


@router.get("/privacy", response_model=PrivacyPreferenceResponse)
@track_request_time(endpoint="get_privacy_preferences")
@cache_response(ttl=600, vary_by=["current_user.id"])
async def get_privacy_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy tùy chọn quyền riêng tư của người dùng hiện tại.

    Bao gồm các tùy chọn về hiển thị hoạt động, lịch sử đọc, và các dữ liệu cá nhân khác.
    """
    preference_service = PreferenceService(db)

    try:
        preferences = await preference_service.get_user_preferences(current_user.id)

        if not preferences or not hasattr(preferences, "privacy_settings"):
            # Trả về tùy chọn mặc định nếu chưa có
            default_privacy = await preference_service.get_default_privacy_preferences()
            return default_privacy

        return preferences.privacy_settings
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy tùy chọn quyền riêng tư của người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy tùy chọn quyền riêng tư")


@router.put("/privacy", response_model=PrivacyPreferenceResponse)
@track_request_time(endpoint="update_privacy_preferences")
@invalidate_cache(namespace="preferences", tags=["privacy_preferences"])
async def update_privacy_preferences(
    data: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật tùy chọn quyền riêng tư.

    Cho phép cập nhật các tùy chọn về hiển thị hoạt động, lịch sử đọc,
    và các dữ liệu cá nhân khác mà không làm thay đổi các tùy chọn khác.
    """
    preference_service = PreferenceService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật tùy chọn quyền riêng tư - User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Xác thực dữ liệu đầu vào
        if not data:
            raise BadRequestException(
                detail="Không có dữ liệu tùy chọn quyền riêng tư được cung cấp",
                code="invalid_privacy_preferences",
            )

        # Cập nhật chỉ phần privacy_settings
        privacy_settings = {"privacy_settings": data}

        updated_preferences = await preference_service.update_user_preferences(
            user_id=current_user.id, data=privacy_settings
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "privacy_preferences_update",
            f"Người dùng đã cập nhật tùy chọn quyền riêng tư",
            metadata={"user_id": current_user.id},
        )

        return updated_preferences.privacy_settings
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật tùy chọn quyền riêng tư cho người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi cập nhật tùy chọn quyền riêng tư")


@router.put("/reset", response_model=UserPreferenceResponse)
@track_request_time(endpoint="reset_user_preferences")
@invalidate_cache(namespace="preferences", tags=["user_preferences"])
async def reset_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Đặt lại tùy chọn người dùng về mặc định.

    Tất cả các tùy chọn sẽ được đặt lại về giá trị mặc định của hệ thống.
    """
    preference_service = PreferenceService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Đặt lại tùy chọn người dùng - User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Lấy dữ liệu tùy chọn mặc định
        default_preferences = await preference_service.get_default_preferences()

        reset_preferences = await preference_service.update_user_preferences(
            user_id=current_user.id, data=default_preferences
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "preferences_reset",
            f"Người dùng đã đặt lại tùy chọn về mặc định",
            metadata={"user_id": current_user.id},
        )

        return reset_preferences
    except Exception as e:
        logger.error(f"Lỗi khi đặt lại tùy chọn người dùng {current_user.id}: {str(e)}")
        raise ServerException(detail="Lỗi khi đặt lại tùy chọn người dùng")


@router.post("/sync", response_model=DeviceSyncResponse)
@track_request_time(endpoint="sync_preferences")
async def sync_preferences(
    data: DeviceSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Đồng bộ hóa tùy chọn giữa các thiết bị.

    Cho phép đồng bộ tùy chọn từ thiết bị hiện tại lên hệ thống hoặc lấy tùy chọn
    từ hệ thống về thiết bị hiện tại. Hỗ trợ giải quyết xung đột khi có nhiều thay đổi.
    """
    preference_service = PreferenceService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Đồng bộ tùy chọn - User: {current_user.id}, Device: {data.device_id}, IP: {client_ip}"
    )

    try:
        # Đồng bộ hóa tùy chọn
        sync_result = await preference_service.sync_preferences(
            user_id=current_user.id,
            device_id=data.device_id,
            last_sync_time=data.last_sync_time,
            client_preferences=data.preferences,
            sync_direction=data.sync_direction,
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "preferences_sync",
            f"Người dùng đã đồng bộ tùy chọn từ thiết bị {data.device_id}",
            metadata={"user_id": current_user.id, "device_id": data.device_id},
        )

        return sync_result
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi đồng bộ tùy chọn cho người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi đồng bộ tùy chọn")
