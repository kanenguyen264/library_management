from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.models.social_profile import SocialProfile, SocialProvider
from app.user_site.repositories.social_profile_repo import SocialProfileRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException, ConflictException
from app.common.utils.cache import cached, remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho social profile service
logger = logging.getLogger(__name__)


async def get_all_social_profiles(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    provider: Optional[SocialProvider] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[SocialProfile]:
    """
    Lấy danh sách hồ sơ mạng xã hội với bộ lọc.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        provider: Lọc theo nhà cung cấp
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách hồ sơ mạng xã hội
    """
    try:
        repo = SocialProfileRepository(db)
        profiles = await repo.list_social_profiles(
            skip=skip,
            limit=limit,
            user_id=user_id,
            provider=provider,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SOCIAL_PROFILES",
                        entity_id=0,
                        description="Viewed social profile list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "provider": provider.value if provider else None,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(profiles),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return profiles
    except Exception as e:
        logger.error(f"Error retrieving social profiles: {str(e)}")
        raise


async def count_social_profiles(
    db: Session,
    user_id: Optional[int] = None,
    provider: Optional[SocialProvider] = None,
) -> int:
    """
    Đếm số lượng hồ sơ mạng xã hội.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        provider: Lọc theo nhà cung cấp

    Returns:
        Số lượng hồ sơ mạng xã hội
    """
    try:
        repo = SocialProfileRepository(db)
        return await repo.count_social_profiles(user_id=user_id, provider=provider)
    except Exception as e:
        logger.error(f"Error counting social profiles: {str(e)}")
        raise


@cached(key_prefix="admin_social_profile", ttl=300)
async def get_social_profile_by_id(
    db: Session, profile_id: int, admin_id: Optional[int] = None
) -> SocialProfile:
    """
    Lấy thông tin hồ sơ mạng xã hội theo ID.

    Args:
        db: Database session
        profile_id: ID của hồ sơ mạng xã hội
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin hồ sơ mạng xã hội

    Raises:
        NotFoundException: Nếu không tìm thấy hồ sơ
    """
    try:
        repo = SocialProfileRepository(db)
        profile = await repo.get_by_id(profile_id)

        if not profile:
            logger.warning(f"Social profile with ID {profile_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy hồ sơ mạng xã hội với ID {profile_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SOCIAL_PROFILE",
                        entity_id=profile_id,
                        description=f"Viewed social profile details for user {profile.user_id}",
                        metadata={
                            "user_id": profile.user_id,
                            "provider": profile.provider.value,
                            "profile_url": (
                                profile.profile_url
                                if hasattr(profile, "profile_url")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return profile
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving social profile: {str(e)}")
        raise


async def get_user_profiles(db: Session, user_id: int) -> List[SocialProfile]:
    """
    Lấy danh sách hồ sơ mạng xã hội của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Danh sách hồ sơ mạng xã hội
    """
    try:
        repo = SocialProfileRepository(db)
        return await repo.get_user_profiles(user_id)
    except Exception as e:
        logger.error(f"Error retrieving user social profiles: {str(e)}")
        raise


async def get_user_profile_by_provider(
    db: Session, user_id: int, provider: SocialProvider
) -> Optional[SocialProfile]:
    """
    Lấy hồ sơ mạng xã hội của người dùng theo nhà cung cấp.

    Args:
        db: Database session
        user_id: ID của người dùng
        provider: Nhà cung cấp

    Returns:
        Thông tin hồ sơ mạng xã hội hoặc None nếu không có
    """
    try:
        repo = SocialProfileRepository(db)
        return await repo.get_by_user_and_provider(user_id, provider)
    except Exception as e:
        logger.error(f"Error retrieving user social profile by provider: {str(e)}")
        raise


async def create_social_profile(
    db: Session, profile_data: Dict[str, Any], admin_id: Optional[int] = None
) -> SocialProfile:
    """
    Tạo hồ sơ mạng xã hội mới.

    Args:
        db: Database session
        profile_data: Dữ liệu hồ sơ
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin hồ sơ mạng xã hội đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
        ConflictException: Nếu hồ sơ đã tồn tại
    """
    try:
        # Kiểm tra người dùng tồn tại
        if "user_id" in profile_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(profile_data["user_id"])

            if not user:
                logger.warning(f"User with ID {profile_data['user_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {profile_data['user_id']}"
                )

        # Kiểm tra xem người dùng đã có hồ sơ với nhà cung cấp này chưa
        repo = SocialProfileRepository(db)
        existing_profile = await repo.get_by_user_and_provider(
            user_id=profile_data["user_id"], provider=profile_data["provider"]
        )

        if existing_profile:
            logger.warning(
                f"User {profile_data['user_id']} already has a profile with provider {profile_data['provider']}"
            )
            raise ConflictException(
                detail=f"Người dùng đã có hồ sơ với nhà cung cấp {profile_data['provider']}"
            )

        # Tạo hồ sơ mới
        profile = await repo.create(profile_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="SOCIAL_PROFILE",
                        entity_id=profile.id,
                        description=f"Created social profile for user {profile.user_id}",
                        metadata={
                            "user_id": profile.user_id,
                            "provider": profile.provider.value,
                            "profile_url": (
                                profile.profile_url
                                if hasattr(profile, "profile_url")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Created new social profile with ID {profile.id} for user {profile.user_id}"
        )
        return profile
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error creating social profile: {str(e)}")
        raise


async def update_social_profile(
    db: Session,
    profile_id: int,
    profile_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> SocialProfile:
    """
    Cập nhật thông tin hồ sơ mạng xã hội.

    Args:
        db: Database session
        profile_id: ID của hồ sơ
        profile_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin hồ sơ mạng xã hội đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy hồ sơ
    """
    try:
        repo = SocialProfileRepository(db)

        # Get old profile data for logging
        old_profile = await get_social_profile_by_id(db, profile_id)

        # Cập nhật hồ sơ
        profile = await repo.update(profile_id, profile_data)

        # Xóa cache
        remove_cache(f"admin_social_profile:{profile_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="SOCIAL_PROFILE",
                        entity_id=profile_id,
                        description=f"Updated social profile for user {profile.user_id}",
                        metadata={
                            "user_id": profile.user_id,
                            "provider": profile.provider.value,
                            "updated_fields": list(profile_data.keys()),
                            "old_values": {
                                k: getattr(old_profile, k) for k in profile_data.keys()
                            },
                            "new_values": {
                                k: getattr(profile, k) for k in profile_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated social profile with ID {profile_id}")
        return profile
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating social profile: {str(e)}")
        raise


async def delete_social_profile(
    db: Session, profile_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa hồ sơ mạng xã hội.

    Args:
        db: Database session
        profile_id: ID của hồ sơ
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy hồ sơ
    """
    try:
        # Get profile details before deletion for logging
        profile = await get_social_profile_by_id(db, profile_id)

        repo = SocialProfileRepository(db)
        await repo.delete(profile_id)

        # Xóa cache
        remove_cache(f"admin_social_profile:{profile_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="SOCIAL_PROFILE",
                        entity_id=profile_id,
                        description=f"Deleted social profile for user {profile.user_id}",
                        metadata={
                            "user_id": profile.user_id,
                            "provider": profile.provider.value,
                            "profile_url": (
                                profile.profile_url
                                if hasattr(profile, "profile_url")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted social profile with ID {profile_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting social profile: {str(e)}")
        raise


@cached(key_prefix="admin_social_profile_statistics", ttl=3600)
async def get_social_profile_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê hồ sơ mạng xã hội.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê hồ sơ mạng xã hội
    """
    try:
        repo = SocialProfileRepository(db)

        total = await repo.count_social_profiles()

        # Thống kê theo nhà cung cấp
        by_provider = {}
        for provider in SocialProvider:
            count = await repo.count_social_profiles(provider=provider)
            by_provider[provider.value] = count

        # Số người dùng có kết nối mạng xã hội
        users_with_social = await repo.count_users_with_social_profiles()

        stats = {
            "total": total,
            "by_provider": by_provider,
            "users_with_social": users_with_social,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SOCIAL_PROFILE_STATISTICS",
                        entity_id=0,
                        description="Viewed social profile statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving social profile statistics: {str(e)}")
        raise
