from typing import Dict, Any, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    HTTPException,
    status,
    Request,
    Body,
)
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import EmailStr

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_active_user, get_current_user
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.social_profile import (
    SocialProfileCreate,
    SocialProfileUpdate,
    SocialProfileResponse,
    SocialProfileListResponse,
    FollowRequest,
    FollowersResponse,
    FollowingResponse,
    SocialStatsResponse,
    SocialActivityResponse,
    RecommendedUsersResponse,
    SocialSearchParams,
)
from app.user_site.services.social_profile_service import SocialProfileService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time, increment_counter
from app.cache.decorators import cache_response, invalidate_cache
from app.core.security import verify_password
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.security.audit.audit_trails import AuditLogger

router = APIRouter()
logger = get_logger("social_profiles_api")
audit_logger = AuditLogger()


@router.post(
    "/", response_model=SocialProfileResponse, status_code=status.HTTP_201_CREATED
)
@track_request_time(endpoint="create_social_profile")
async def create_social_profile(
    data: SocialProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một trang mạng xã hội mới cho người dùng hiện tại.
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo trang mạng xã hội - User: {current_user.id}, Platform: {data.platform}, IP: {client_ip}"
    )

    try:
        # Kiểm tra người dùng đã có hồ sơ trên nền tảng này chưa
        existing_profile = await social_profile_service.get_social_profile_by_platform(
            user_id=current_user.id, platform=data.platform
        )

        if existing_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bạn đã có trang mạng xã hội trên nền tảng {data.platform}",
            )

        profile = await social_profile_service.create_social_profile(
            current_user.id, data.model_dump()
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "social_profile_create",
            f"Người dùng đã tạo trang mạng xã hội trên nền tảng {data.platform}",
            metadata={"user_id": current_user.id, "platform": data.platform},
        )

        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo trang mạng xã hội: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo trang mạng xã hội",
        )


@router.get("/", response_model=SocialProfileListResponse)
@track_request_time(endpoint="list_social_profiles")
@cache_response(ttl=600, vary_by=["current_user.id"])
async def list_social_profiles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách trang mạng xã hội của người dùng hiện tại.
    """
    social_profile_service = SocialProfileService(db)

    try:
        profiles = await social_profile_service.list_social_profiles(current_user.id)
        return {"items": profiles, "total": len(profiles)}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách trang mạng xã hội cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách trang mạng xã hội",
        )


@router.get("/user/{user_id}", response_model=SocialProfileListResponse)
@track_request_time(endpoint="get_user_social_profiles")
@cache_response(ttl=3600, vary_by=["user_id"])
async def get_user_social_profiles(
    user_id: int = Path(..., gt=0, description="ID của người dùng"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách trang mạng xã hội công khai của một người dùng.
    """
    social_profile_service = SocialProfileService(db)

    try:
        # Kiểm tra người dùng có tồn tại không
        user_exists = await social_profile_service.is_user_exists(user_id)

        if not user_exists:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID: {user_id}"
            )

        profiles = await social_profile_service.list_public_social_profiles(user_id)
        return {"items": profiles, "total": len(profiles)}
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách trang mạng xã hội công khai cho người dùng {user_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách trang mạng xã hội công khai",
        )


@router.get("/{profile_id}", response_model=SocialProfileResponse)
@track_request_time(endpoint="get_social_profile")
@cache_response(ttl=600, vary_by=["profile_id", "current_user.id"])
async def get_social_profile(
    profile_id: int = Path(..., gt=0, description="ID của trang mạng xã hội"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một trang mạng xã hội.
    """
    social_profile_service = SocialProfileService(db)

    try:
        profile = await social_profile_service.get_social_profile_by_id(profile_id)

        if not profile:
            raise NotFoundException(
                detail=f"Không tìm thấy trang mạng xã hội với ID: {profile_id}"
            )

        # Kiểm tra quyền xem
        if profile.user_id != current_user.id and not profile.is_public:
            raise ForbiddenException(
                detail="Bạn không có quyền xem trang mạng xã hội này"
            )

        return profile
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin trang mạng xã hội {profile_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin trang mạng xã hội",
        )


@router.put("/{profile_id}", response_model=SocialProfileResponse)
@track_request_time(endpoint="update_social_profile")
async def update_social_profile(
    data: SocialProfileUpdate,
    profile_id: int = Path(..., gt=0, description="ID của trang mạng xã hội"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin trang mạng xã hội.
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật trang mạng xã hội - ID: {profile_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra trang mạng xã hội có tồn tại không
        profile = await social_profile_service.get_social_profile_by_id(profile_id)

        if not profile:
            raise NotFoundException(
                detail=f"Không tìm thấy trang mạng xã hội với ID: {profile_id}"
            )

        # Kiểm tra quyền chỉnh sửa
        if profile.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền chỉnh sửa trang mạng xã hội này"
            )

        updated_profile = await social_profile_service.update_social_profile(
            profile_id=profile_id, data=data.model_dump(exclude_unset=True)
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "social_profile_update",
            f"Người dùng đã cập nhật trang mạng xã hội {profile_id}",
            metadata={"user_id": current_user.id, "profile_id": profile_id},
        )

        return updated_profile
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật trang mạng xã hội {profile_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật trang mạng xã hội",
        )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_social_profile")
async def delete_social_profile(
    profile_id: int = Path(..., gt=0, description="ID của trang mạng xã hội"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa trang mạng xã hội.
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa trang mạng xã hội - ID: {profile_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra trang mạng xã hội có tồn tại không
        profile = await social_profile_service.get_social_profile_by_id(profile_id)

        if not profile:
            raise NotFoundException(
                detail=f"Không tìm thấy trang mạng xã hội với ID: {profile_id}"
            )

        # Kiểm tra quyền xóa
        if profile.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xóa trang mạng xã hội này"
            )

        await social_profile_service.delete_social_profile(profile_id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "social_profile_delete",
            f"Người dùng đã xóa trang mạng xã hội {profile_id}",
            metadata={"user_id": current_user.id, "profile_id": profile_id},
        )

        return None
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa trang mạng xã hội {profile_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa trang mạng xã hội",
        )


@router.get("/me", response_model=SocialProfileResponse)
@track_request_time(endpoint="get_my_social_profile")
async def get_my_social_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin hồ sơ xã hội của người dùng hiện tại.
    """
    social_profile_service = SocialProfileService(db)

    try:
        profile = await social_profile_service.get_social_profile_by_user_id(
            current_user.id
        )

        if not profile:
            # Tạo hồ sơ nếu chưa tồn tại
            profile = await social_profile_service.create_social_profile(
                current_user.id
            )

        return profile
    except Exception as e:
        logger.error(f"Lỗi khi lấy hồ sơ xã hội cá nhân: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy hồ sơ xã hội cá nhân",
        )


@router.put("/me", response_model=SocialProfileResponse)
@track_request_time(endpoint="update_my_social_profile")
@throttle_requests(max_requests=5, per_seconds=60)
async def update_my_social_profile(
    data: SocialProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Cập nhật thông tin hồ sơ xã hội của người dùng hiện tại.

    - Rate limiting: Giới hạn 5 request/phút để bảo vệ hệ thống
    - Input validation: Xác thực dữ liệu đầu vào
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(f"Cập nhật hồ sơ xã hội - User: {current_user.id}, IP: {client_ip}")

    try:
        profile = await social_profile_service.get_social_profile_by_user_id(
            current_user.id
        )

        if not profile:
            # Tạo hồ sơ nếu chưa tồn tại
            profile = await social_profile_service.create_social_profile(
                current_user.id
            )

        updated_profile = await social_profile_service.update_social_profile(
            user_id=current_user.id, data=data.model_dump(exclude_unset=True)
        )

        # Vô hiệu hóa cache liên quan
        await invalidate_cache(f"social:profile:{current_user.id}")

        return updated_profile
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật hồ sơ xã hội: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật hồ sơ xã hội",
        )


@router.get("/users/{user_id}", response_model=SocialProfileResponse)
@track_request_time(endpoint="get_user_social_profile")
@cache_response(ttl=3600, vary_by=["user_id"])
async def get_user_social_profile(
    user_id: int = Path(..., gt=0, description="ID của người dùng"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin hồ sơ xã hội của một người dùng.

    - Public API: Có thể truy cập mà không cần đăng nhập
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    social_profile_service = SocialProfileService(db)

    try:
        profile = await social_profile_service.get_social_profile_by_user_id(user_id)

        if not profile:
            raise NotFoundException(
                detail=f"Không tìm thấy hồ sơ xã hội cho người dùng có ID: {user_id}"
            )

        # Kiểm tra nếu hồ sơ riêng tư và người xem không phải là chủ sở hữu hoặc người theo dõi
        if profile.is_private and (not current_user or current_user.id != user_id):
            # Kiểm tra nếu người xem có theo dõi người dùng này không
            if not current_user or not await social_profile_service.is_following(
                current_user.id, user_id
            ):
                # Trả về phiên bản giới hạn của hồ sơ
                return {
                    "id": profile.id,
                    "user_id": profile.user_id,
                    "display_name": profile.display_name,
                    "avatar_url": profile.avatar_url,
                    "is_private": profile.is_private,
                    "follower_count": profile.follower_count,
                    "following_count": profile.following_count,
                }

        return profile
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy hồ sơ xã hội của người dùng {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy hồ sơ xã hội",
        )


@router.post("/follow", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="follow_user")
@throttle_requests(max_requests=20, per_seconds=60)
async def follow_user(
    data: FollowRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Theo dõi một người dùng.

    - Anti-abuse: Giới hạn tốc độ để ngăn chặn lạm dụng
    - Validation: Kiểm tra logic nghiệp vụ (không thể tự theo dõi bản thân)
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Theo dõi người dùng - User: {current_user.id}, Target: {data.user_id}, IP: {client_ip}"
    )

    if current_user.id == data.user_id:
        raise BadRequestException(detail="Không thể theo dõi chính mình")

    try:
        # Kiểm tra người dùng đích có tồn tại không
        target_profile = await social_profile_service.get_social_profile_by_user_id(
            data.user_id
        )

        if not target_profile:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng có ID: {data.user_id}"
            )

        # Kiểm tra đã theo dõi chưa
        if await social_profile_service.is_following(current_user.id, data.user_id):
            raise BadRequestException(detail=f"Bạn đã theo dõi người dùng này")

        # Thực hiện theo dõi
        await social_profile_service.follow_user(current_user.id, data.user_id)

        # Vô hiệu hóa cache liên quan
        await invalidate_cache(f"social:profile:{current_user.id}")
        await invalidate_cache(f"social:profile:{data.user_id}")
        await invalidate_cache(f"social:followers:{data.user_id}")
        await invalidate_cache(f"social:following:{current_user.id}")

        return {"message": "Theo dõi thành công"}
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi theo dõi người dùng {data.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi theo dõi người dùng",
        )


@router.post("/unfollow", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="unfollow_user")
@throttle_requests(max_requests=20, per_seconds=60)
async def unfollow_user(
    data: FollowRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Bỏ theo dõi một người dùng.

    - Anti-abuse: Giới hạn tốc độ để ngăn chặn lạm dụng
    - Validation: Kiểm tra logic nghiệp vụ
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Bỏ theo dõi người dùng - User: {current_user.id}, Target: {data.user_id}, IP: {client_ip}"
    )

    if current_user.id == data.user_id:
        raise BadRequestException(detail="Không thể bỏ theo dõi chính mình")

    try:
        # Kiểm tra người dùng đích có tồn tại không
        target_profile = await social_profile_service.get_social_profile_by_user_id(
            data.user_id
        )

        if not target_profile:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng có ID: {data.user_id}"
            )

        # Kiểm tra có đang theo dõi không
        if not await social_profile_service.is_following(current_user.id, data.user_id):
            raise BadRequestException(detail=f"Bạn chưa theo dõi người dùng này")

        # Thực hiện bỏ theo dõi
        await social_profile_service.unfollow_user(current_user.id, data.user_id)

        # Vô hiệu hóa cache liên quan
        await invalidate_cache(f"social:profile:{current_user.id}")
        await invalidate_cache(f"social:profile:{data.user_id}")
        await invalidate_cache(f"social:followers:{data.user_id}")
        await invalidate_cache(f"social:following:{current_user.id}")

        return {"message": "Bỏ theo dõi thành công"}
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi bỏ theo dõi người dùng {data.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi bỏ theo dõi người dùng",
        )


@router.get("/followers/{user_id}", response_model=FollowersResponse)
@track_request_time(endpoint="get_followers")
@cache_response(ttl=1800, vary_by=["user_id", "skip", "limit"])
async def get_followers(
    user_id: int = Path(..., gt=0, description="ID của người dùng"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách người theo dõi của một người dùng.

    - Pagination: Phân trang với skip/limit
    - Caching: Cache kết quả để tối ưu hiệu suất
    - Privacy: Kiểm tra quyền riêng tư trước khi trả về kết quả
    """
    social_profile_service = SocialProfileService(db)

    try:
        # Kiểm tra người dùng có tồn tại không
        profile = await social_profile_service.get_social_profile_by_user_id(user_id)

        if not profile:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng có ID: {user_id}"
            )

        # Kiểm tra quyền riêng tư nếu không phải bản thân
        if profile.is_private and (not current_user or current_user.id != user_id):
            # Kiểm tra nếu người xem có theo dõi người dùng này không
            if not current_user or not await social_profile_service.is_following(
                current_user.id, user_id
            ):
                raise ForbiddenException(
                    detail="Không có quyền xem danh sách người theo dõi của hồ sơ riêng tư này"
                )

        followers, total = await social_profile_service.get_followers(
            user_id=user_id, skip=skip, limit=limit
        )

        return {"items": followers, "total": total}
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách người theo dõi của người dùng {user_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách người theo dõi",
        )


@router.get("/following/{user_id}", response_model=FollowingResponse)
@track_request_time(endpoint="get_following")
@cache_response(ttl=1800, vary_by=["user_id", "skip", "limit"])
async def get_following(
    user_id: int = Path(..., gt=0, description="ID của người dùng"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách người mà người dùng đang theo dõi.

    - Pagination: Phân trang với skip/limit
    - Caching: Cache kết quả để tối ưu hiệu suất
    - Privacy: Kiểm tra quyền riêng tư trước khi trả về kết quả
    """
    social_profile_service = SocialProfileService(db)

    try:
        # Kiểm tra người dùng có tồn tại không
        profile = await social_profile_service.get_social_profile_by_user_id(user_id)

        if not profile:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng có ID: {user_id}"
            )

        # Kiểm tra quyền riêng tư nếu không phải bản thân
        if profile.is_private and (not current_user or current_user.id != user_id):
            # Kiểm tra nếu người xem có theo dõi người dùng này không
            if not current_user or not await social_profile_service.is_following(
                current_user.id, user_id
            ):
                raise ForbiddenException(
                    detail="Không có quyền xem danh sách đang theo dõi của hồ sơ riêng tư này"
                )

        following, total = await social_profile_service.get_following(
            user_id=user_id, skip=skip, limit=limit
        )

        return {"items": following, "total": total}
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách đang theo dõi của người dùng {user_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách đang theo dõi",
        )


@router.post("/search", response_model=RecommendedUsersResponse)
@track_request_time(endpoint="search_users")
@throttle_requests(max_requests=15, per_seconds=60)
async def search_users(
    params: SocialSearchParams = Body(...),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Tìm kiếm người dùng với các tiêu chí nâng cao.

    - Advanced search: Tìm kiếm theo nhiều tiêu chí (tên, thẻ, sở thích)
    - Pagination: Phân trang với skip/limit
    - Rate limiting: Giới hạn 15 request/phút
    """
    social_profile_service = SocialProfileService(db)

    try:
        users, total = await social_profile_service.search_users(
            params=params,
            skip=skip,
            limit=limit,
            current_user_id=current_user.id if current_user else None,
        )

        return {"items": users, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm người dùng: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tìm kiếm người dùng",
        )


@router.get("/recommended", response_model=RecommendedUsersResponse)
@track_request_time(endpoint="get_recommended_users")
@cache_response(ttl=3600, vary_by=["limit", "user_id"])
async def get_recommended_users(
    limit: int = Query(10, ge=1, le=50, description="Số lượng người dùng gợi ý"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách người dùng được gợi ý để theo dõi.

    - Personalized: Gợi ý dựa trên sở thích đọc và hành vi của người dùng
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    social_profile_service = SocialProfileService(db)

    try:
        users, total = await social_profile_service.get_recommended_users(
            user_id=current_user.id, limit=limit
        )

        return {"items": users, "total": total}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách người dùng gợi ý cho {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách người dùng gợi ý",
        )


@router.get("/popular", response_model=RecommendedUsersResponse)
@track_request_time(endpoint="get_popular_users")
@cache_response(ttl=3600, vary_by=["limit", "category_id"])
async def get_popular_users(
    limit: int = Query(10, ge=1, le=50, description="Số lượng người dùng nổi bật"),
    category_id: Optional[int] = Query(
        None, gt=0, description="Lọc theo danh mục sách"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách người dùng nổi bật trên nền tảng.

    - Popularity: Dựa trên lượt theo dõi và hoạt động
    - Filtering: Tùy chọn lọc theo danh mục sách yêu thích
    - Caching: Cache kết quả để tối ưu hiệu suất
    """
    social_profile_service = SocialProfileService(db)
    increment_counter("popular_users_requested")

    try:
        users, total = await social_profile_service.get_popular_users(
            limit=limit, category_id=category_id
        )

        return {"items": users, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách người dùng nổi bật: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách người dùng nổi bật",
        )


@router.get("/stats/me", response_model=SocialStatsResponse)
@track_request_time(endpoint="get_my_social_stats")
async def get_my_social_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thống kê xã hội của người dùng hiện tại.

    - Stats: Thống kê lượt theo dõi, tương tác, xu hướng
    """
    social_profile_service = SocialProfileService(db)

    try:
        stats = await social_profile_service.get_user_social_stats(current_user.id)
        return stats
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thống kê xã hội của người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thống kê xã hội",
        )


@router.get("/activity", response_model=SocialActivityResponse)
@track_request_time(endpoint="get_social_activity")
@cache_response(ttl=300, vary_by=["user_id", "limit"])
async def get_social_activity(
    limit: int = Query(20, ge=1, le=100, description="Số lượng hoạt động lấy"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy luồng hoạt động xã hội từ người dùng đang theo dõi.

    - News feed: Hiển thị hoạt động đọc, đánh giá, bình luận từ mạng xã hội
    - Caching: Cache kết quả để tối ưu hiệu suất (TTL ngắn vì dữ liệu thay đổi nhanh)
    """
    social_profile_service = SocialProfileService(db)

    try:
        activities = await social_profile_service.get_social_activity(
            user_id=current_user.id, limit=limit
        )

        return {"items": activities, "total": len(activities)}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy hoạt động xã hội cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy hoạt động xã hội",
        )


@router.post("/privacy", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="update_privacy_settings")
@throttle_requests(max_requests=5, per_seconds=60)
async def update_privacy_settings(
    is_private: bool = Body(..., embed=True),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Cập nhật cài đặt riêng tư hồ sơ.

    - Privacy: Cho phép người dùng điều chỉnh mức độ riêng tư của hồ sơ
    - Rate limiting: Giới hạn 5 request/phút
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật cài đặt riêng tư - User: {current_user.id}, Private: {is_private}, IP: {client_ip}"
    )

    try:
        profile = await social_profile_service.get_social_profile_by_user_id(
            current_user.id
        )

        if not profile:
            profile = await social_profile_service.create_social_profile(
                current_user.id
            )

        await social_profile_service.update_privacy_settings(
            user_id=current_user.id, is_private=is_private
        )

        # Vô hiệu hóa cache liên quan
        await invalidate_cache(f"social:profile:{current_user.id}")

        return {"message": "Cập nhật cài đặt riêng tư thành công"}
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật cài đặt riêng tư cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật cài đặt riêng tư",
        )


@router.post("/block/{user_id}", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="block_user")
@throttle_requests(max_requests=10, per_seconds=60)
async def block_user(
    user_id: int = Path(..., gt=0, description="ID của người dùng cần chặn"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Chặn một người dùng.

    - Security: Cho phép người dùng chặn tương tác từ người khác
    - Anti-abuse: Giới hạn tốc độ để ngăn chặn lạm dụng
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Chặn người dùng - User: {current_user.id}, Target: {user_id}, IP: {client_ip}"
    )

    if current_user.id == user_id:
        raise BadRequestException(detail="Không thể chặn chính mình")

    try:
        # Kiểm tra người dùng đích có tồn tại không
        target_profile = await social_profile_service.get_social_profile_by_user_id(
            user_id
        )

        if not target_profile:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng có ID: {user_id}"
            )

        # Kiểm tra đã chặn chưa
        if await social_profile_service.is_blocked(current_user.id, user_id):
            raise BadRequestException(detail=f"Bạn đã chặn người dùng này")

        # Thực hiện chặn
        await social_profile_service.block_user(current_user.id, user_id)

        # Tự động bỏ theo dõi nếu đang theo dõi
        if await social_profile_service.is_following(current_user.id, user_id):
            await social_profile_service.unfollow_user(current_user.id, user_id)

        # Tự động xóa theo dõi từ người bị chặn (nếu có)
        if await social_profile_service.is_following(user_id, current_user.id):
            await social_profile_service.unfollow_user(user_id, current_user.id)

        # Vô hiệu hóa cache liên quan
        await invalidate_cache(f"social:profile:{current_user.id}")
        await invalidate_cache(f"social:profile:{user_id}")
        await invalidate_cache(f"social:followers:{current_user.id}")
        await invalidate_cache(f"social:followers:{user_id}")
        await invalidate_cache(f"social:following:{current_user.id}")
        await invalidate_cache(f"social:following:{user_id}")

        return {"message": "Chặn người dùng thành công"}
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi chặn người dùng {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi chặn người dùng",
        )


@router.post("/unblock/{user_id}", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="unblock_user")
@throttle_requests(max_requests=10, per_seconds=60)
async def unblock_user(
    user_id: int = Path(..., gt=0, description="ID của người dùng cần bỏ chặn"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Bỏ chặn một người dùng.

    - Security: Cho phép người dùng bỏ chặn người khác
    - Anti-abuse: Giới hạn tốc độ để ngăn chặn lạm dụng
    """
    social_profile_service = SocialProfileService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Bỏ chặn người dùng - User: {current_user.id}, Target: {user_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra người dùng đích có tồn tại không
        target_profile = await social_profile_service.get_social_profile_by_user_id(
            user_id
        )

        if not target_profile:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng có ID: {user_id}"
            )

        # Kiểm tra có đang chặn không
        if not await social_profile_service.is_blocked(current_user.id, user_id):
            raise BadRequestException(detail=f"Bạn chưa chặn người dùng này")

        # Thực hiện bỏ chặn
        await social_profile_service.unblock_user(current_user.id, user_id)

        # Vô hiệu hóa cache liên quan
        await invalidate_cache(f"social:profile:{current_user.id}")

        return {"message": "Bỏ chặn người dùng thành công"}
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi bỏ chặn người dùng {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi bỏ chặn người dùng",
        )


@router.get("/blocked", response_model=RecommendedUsersResponse)
@track_request_time(endpoint="get_blocked_users")
async def get_blocked_users(
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách người dùng đã chặn.

    - Pagination: Phân trang với skip/limit
    - Security: Giúp người dùng quản lý danh sách chặn
    """
    social_profile_service = SocialProfileService(db)

    try:
        blocked_users, total = await social_profile_service.get_blocked_users(
            user_id=current_user.id, skip=skip, limit=limit
        )

        return {"items": blocked_users, "total": total}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách người dùng đã chặn của {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách người dùng đã chặn",
        )
