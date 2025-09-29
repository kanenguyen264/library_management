from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
import logging

from app.user_site.models.user import User, Gender
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException, ConflictException
from app.common.utils.cache import cached, remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho user service
logger = logging.getLogger(__name__)


async def get_all_users(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    sort_by: str = "id",
    sort_desc: bool = False,
    only_active: bool = False,
    only_premium: bool = False,
    admin_id: Optional[int] = None,
) -> List[User]:
    """
    Lấy danh sách người dùng với các bộ lọc.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua (phân trang)
        limit: Số lượng bản ghi tối đa trả về
        search: Từ khóa tìm kiếm (username, email, họ tên)
        sort_by: Trường dùng để sắp xếp
        sort_desc: Sắp xếp giảm dần
        only_active: Chỉ lấy người dùng đang hoạt động
        only_premium: Chỉ lấy người dùng premium
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách người dùng
    """
    repo = UserRepository(db)

    if only_premium:
        users = await repo.list_premium_users(skip=skip, limit=limit)
    else:
        users = await repo.list_users(skip=skip, limit=limit, search=search)

    if only_active:
        users = [user for user in users if user.is_active]

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="USERS",
                    entity_id=0,
                    description=f"Viewed user list with filters",
                    metadata={
                        "skip": skip,
                        "limit": limit,
                        "search": search,
                        "only_active": only_active,
                        "only_premium": only_premium,
                        "results_count": len(users),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return users


async def count_users(
    db: Session,
    search: Optional[str] = None,
    only_active: bool = False,
    only_premium: bool = False,
) -> int:
    """
    Đếm số lượng người dùng.

    Args:
        db: Database session
        search: Từ khóa tìm kiếm
        only_active: Chỉ đếm người dùng đang hoạt động
        only_premium: Chỉ đếm người dùng premium

    Returns:
        Số lượng người dùng
    """
    repo = UserRepository(db)

    if only_premium:
        return await repo.count_premium_users()

    count = await repo.count_users(search=search)

    # Hiện tại repository không hỗ trợ lọc theo trạng thái active
    # Nếu cần lọc, có thể cần cải tiến repository hoặc lọc tại đây

    return count


@cached(key_prefix="admin_user", ttl=3600)
async def get_user_by_id(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> User:
    """
    Lấy thông tin người dùng theo ID.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin người dùng

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)

    if not user:
        logger.warning(f"User with ID {user_id} not found")
        raise NotFoundException(detail=f"Không tìm thấy người dùng với ID {user_id}")

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="USER",
                    entity_id=user_id,
                    description=f"Viewed user details: {user.username}",
                    metadata={"username": user.username, "email": user.email},
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return user


async def get_user_by_username(db: Session, username: str) -> User:
    """
    Lấy thông tin người dùng theo username.

    Args:
        db: Database session
        username: Username của người dùng

    Returns:
        Thông tin người dùng

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)
    user = await repo.get_by_username(username)

    if not user:
        logger.warning(f"User with username {username} not found")
        raise NotFoundException(
            detail=f"Không tìm thấy người dùng với username {username}"
        )

    return user


async def get_user_by_email(db: Session, email: str) -> User:
    """
    Lấy thông tin người dùng theo email.

    Args:
        db: Database session
        email: Email của người dùng

    Returns:
        Thông tin người dùng

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)
    user = await repo.get_by_email(email)

    if not user:
        logger.warning(f"User with email {email} not found")
        raise NotFoundException(detail=f"Không tìm thấy người dùng với email {email}")

    return user


async def create_user(
    db: Session, user_data: Dict[str, Any], admin_id: Optional[int] = None
) -> User:
    """
    Tạo người dùng mới.

    Args:
        db: Database session
        user_data: Dữ liệu người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin người dùng đã tạo

    Raises:
        ConflictException: Nếu username hoặc email đã tồn tại
    """
    repo = UserRepository(db)

    try:
        user = await repo.create(user_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="USER",
                        entity_id=user.id,
                        description=f"Created new user: {user.username}",
                        metadata={
                            "username": user.username,
                            "email": user.email,
                            "is_active": user.is_active,
                            "is_premium": user.is_premium,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new user with ID {user.id} and username {user.username}")
        return user
    except ConflictException as e:
        logger.warning(f"User creation failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in user creation: {str(e)}")
        raise


async def update_user(
    db: Session, user_id: int, user_data: Dict[str, Any], admin_id: Optional[int] = None
) -> User:
    """
    Cập nhật thông tin người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        user_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin người dùng đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)

    # Kiểm tra người dùng tồn tại
    old_user = await get_user_by_id(db, user_id)

    user = await repo.update(user_id, user_data)

    # Xóa cache
    remove_cache(f"admin_user:{user_id}")

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="UPDATE",
                    entity_type="USER",
                    entity_id=user_id,
                    description=f"Updated user: {user.username}",
                    metadata={
                        "username": user.username,
                        "updated_fields": list(user_data.keys()),
                        "old_values": {
                            k: getattr(old_user, k) for k in user_data.keys()
                        },
                        "new_values": {k: getattr(user, k) for k in user_data.keys()},
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    logger.info(f"Updated user with ID {user_id}")
    return user


async def delete_user(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)

    # Get user details before deletion for logging
    user = await get_user_by_id(db, user_id)

    try:
        await repo.delete(user_id)

        # Xóa cache
        remove_cache(f"admin_user:{user_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="USER",
                        entity_id=user_id,
                        description=f"Deleted user: {user.username}",
                        metadata={
                            "username": user.username,
                            "email": user.email,
                            "created_at": (
                                user.created_at.isoformat() if user.created_at else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted user with ID {user_id}")
    except NotFoundException as e:
        logger.warning(f"User deletion failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in user deletion: {str(e)}")
        raise


async def set_premium_status(
    db: Session,
    user_id: int,
    is_premium: bool,
    premium_until: Optional[Any] = None,
    admin_id: Optional[int] = None,
) -> User:
    """
    Đặt trạng thái premium cho người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        is_premium: Trạng thái premium
        premium_until: Thời hạn premium
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin người dùng đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)

    # Get user details before update for logging
    old_user = await get_user_by_id(db, user_id)

    user = await repo.set_premium_status(user_id, is_premium, premium_until)

    # Xóa cache
    remove_cache(f"admin_user:{user_id}")

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="UPDATE",
                    entity_type="USER",
                    entity_id=user_id,
                    description=f"{'Enabled' if is_premium else 'Disabled'} premium status for user: {user.username}",
                    metadata={
                        "username": user.username,
                        "old_premium_status": old_user.is_premium,
                        "new_premium_status": is_premium,
                        "premium_until": (
                            premium_until.isoformat() if premium_until else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    logger.info(f"Set premium status to {is_premium} for user with ID {user_id}")
    return user


async def verify_user_email(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> User:
    """
    Xác thực email người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin người dùng đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)

    # Get user details before verification for logging
    user = await get_user_by_id(db, user_id)

    user = await repo.verify_email(user_id)

    # Xóa cache
    remove_cache(f"admin_user:{user_id}")

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VERIFY",
                    entity_type="USER_EMAIL",
                    entity_id=user_id,
                    description=f"Verified email for user: {user.username}",
                    metadata={"username": user.username, "email": user.email},
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    logger.info(f"Verified email for user with ID {user_id}")
    return user


async def deactivate_user(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> User:
    """
    Vô hiệu hóa tài khoản người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin người dùng đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)

    # Get user details before deactivation for logging
    user = await get_user_by_id(db, user_id)

    user = await repo.deactivate_user(user_id)

    # Xóa cache
    remove_cache(f"admin_user:{user_id}")

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="DEACTIVATE",
                    entity_type="USER",
                    entity_id=user_id,
                    description=f"Deactivated user account: {user.username}",
                    metadata={
                        "username": user.username,
                        "email": user.email,
                        "deactivation_date": (
                            user.updated_at.isoformat() if user.updated_at else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    logger.info(f"Deactivated user with ID {user_id}")
    return user


async def reactivate_user(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> User:
    """
    Kích hoạt lại tài khoản người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin người dùng đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    repo = UserRepository(db)

    # Get user details before reactivation for logging
    user = await get_user_by_id(db, user_id)

    user = await repo.reactivate_user(user_id)

    # Xóa cache
    remove_cache(f"admin_user:{user_id}")

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="REACTIVATE",
                    entity_type="USER",
                    entity_id=user_id,
                    description=f"Reactivated user account: {user.username}",
                    metadata={
                        "username": user.username,
                        "email": user.email,
                        "reactivation_date": (
                            user.updated_at.isoformat() if user.updated_at else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    logger.info(f"Reactivated user with ID {user_id}")
    return user


@cached(key_prefix="admin_user_statistics", ttl=3600)
async def get_user_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê người dùng.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê người dùng
    """
    repo = UserRepository(db)

    total_users = await repo.count_users()
    premium_users = await repo.count_premium_users()

    stats = {
        "total_users": total_users,
        "premium_users": premium_users,
        "conversion_rate": (
            round(premium_users / total_users * 100, 2) if total_users > 0 else 0
        ),
    }

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="USER_STATISTICS",
                    entity_id=0,
                    description="Viewed user statistics",
                    metadata=stats,
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return stats
