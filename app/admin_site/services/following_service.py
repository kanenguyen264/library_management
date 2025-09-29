from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.user_site.models.following import UserFollowing
from app.user_site.models.user import User
from app.user_site.repositories.following_repo import FollowingRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho following service
logger = logging.getLogger(__name__)


async def get_all_followings(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    follower_id: Optional[int] = None,
    following_id: Optional[int] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[UserFollowing]:
    """
    Lấy danh sách quan hệ theo dõi với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        follower_id: Lọc theo người theo dõi
        following_id: Lọc theo người được theo dõi
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách quan hệ theo dõi
    """
    try:
        repo = FollowingRepository(db)
        followings = await repo.list_followings(
            skip=skip,
            limit=limit,
            follower_id=follower_id,
            following_id=following_id,
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
                        entity_type="FOLLOWINGS",
                        entity_id=0,
                        description="Viewed following relationships list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "follower_id": follower_id,
                            "following_id": following_id,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(followings),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return followings
    except Exception as e:
        logger.error(f"Error retrieving followings: {str(e)}")
        raise


@cached(key_prefix="admin_following_by_id", ttl=300)
async def get_following_by_id(
    db: Session, following_id: int, admin_id: Optional[int] = None
) -> Optional[UserFollowing]:
    """
    Lấy thông tin quan hệ theo dõi theo ID.

    Args:
        db: Database session
        following_id: ID của quan hệ theo dõi
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin quan hệ theo dõi hoặc None nếu không tìm thấy
    """
    try:
        repo = FollowingRepository(db)
        following = await repo.get_by_id(following_id)

        # Log admin activity
        if admin_id and following:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="FOLLOWING",
                        entity_id=following_id,
                        description=f"Viewed following relationship details - ID: {following_id}",
                        metadata={
                            "following_id": following_id,
                            "follower_id": following.follower_id if following else None,
                            "following_user_id": (
                                following.following_id if following else None
                            ),
                            "created_at": (
                                following.created_at.isoformat()
                                if following and following.created_at
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return following
    except Exception as e:
        logger.error(f"Error retrieving following by ID: {str(e)}")
        raise


async def create_following(
    db: Session, follower_id: int, following_id: int, admin_id: Optional[int] = None
) -> UserFollowing:
    """
    Tạo quan hệ theo dõi mới từ admin.

    Args:
        db: Database session
        follower_id: ID của người dùng thực hiện follow
        following_id: ID của người dùng được follow
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin quan hệ theo dõi đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
        ForbiddenException: Nếu người dùng cố follow chính mình
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)

        follower = await user_repo.get_by_id(follower_id)
        if not follower:
            logger.warning(f"Follower with ID {follower_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {follower_id}"
            )

        following = await user_repo.get_by_id(following_id)
        if not following:
            logger.warning(f"Following with ID {following_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {following_id}"
            )

        # Kiểm tra nếu người dùng follow chính mình
        if follower_id == following_id:
            logger.warning(f"User {follower_id} attempted to follow themselves")
            raise ForbiddenException(detail="Người dùng không thể follow chính mình")

        # Kiểm tra nếu đã follow rồi
        repo = FollowingRepository(db)
        existing = await repo.get_following_relation(follower_id, following_id)
        if existing:
            logger.info(f"User {follower_id} already follows user {following_id}")
            return existing

        # Tạo quan hệ follow mới
        following_relation = await repo.follow_user(follower_id, following_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="FOLLOWING",
                        entity_id=following_relation.id,
                        description=f"Admin created following relationship: User {follower_id} follows user {following_id}",
                        metadata={
                            "follower_id": follower_id,
                            "follower_username": (
                                follower.username
                                if hasattr(follower, "username")
                                else None
                            ),
                            "following_id": following_id,
                            "following_username": (
                                following.username
                                if hasattr(following, "username")
                                else None
                            ),
                            "created_at": (
                                following_relation.created_at.isoformat()
                                if hasattr(following_relation, "created_at")
                                else None
                            ),
                            "created_by_admin": True,
                            "admin_id": admin_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Admin {admin_id} created following: User {follower_id} follows user {following_id}"
        )
        return following_relation
    except ForbiddenException:
        raise
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating following: {str(e)}")
        raise


async def follow_user(
    db: Session, follower_id: int, following_id: int, admin_id: Optional[int] = None
) -> UserFollowing:
    """
    Người dùng follow một người dùng khác.

    Args:
        db: Database session
        follower_id: ID của người dùng thực hiện follow
        following_id: ID của người dùng được follow
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin follow

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
        ForbiddenException: Nếu người dùng cố follow chính mình
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)

        follower = await user_repo.get_by_id(follower_id)
        if not follower:
            logger.warning(f"Follower with ID {follower_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {follower_id}"
            )

        following = await user_repo.get_by_id(following_id)
        if not following:
            logger.warning(f"Following with ID {following_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {following_id}"
            )

        # Thực hiện follow
        repo = FollowingRepository(db)
        following_relation = await repo.follow_user(follower_id, following_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="FOLLOWING",
                        entity_id=following_relation.id,
                        description=f"Created following relationship: User {follower_id} follows user {following_id}",
                        metadata={
                            "follower_id": follower_id,
                            "follower_username": (
                                follower.username
                                if hasattr(follower, "username")
                                else None
                            ),
                            "following_id": following_id,
                            "following_username": (
                                following.username
                                if hasattr(following, "username")
                                else None
                            ),
                            "created_at": (
                                following_relation.created_at.isoformat()
                                if hasattr(following_relation, "created_at")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"User {follower_id} followed user {following_id}")
        return following_relation
    except ForbiddenException:
        logger.warning(f"User {follower_id} attempted to follow themselves")
        raise
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error following user: {str(e)}")
        raise


async def unfollow_user(
    db: Session, follower_id: int, following_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Người dùng unfollow một người dùng khác.

    Args:
        db: Database session
        follower_id: ID của người dùng thực hiện unfollow
        following_id: ID của người dùng bị unfollow
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu unfollow thành công, False nếu không có mối quan hệ follow
    """
    try:
        # Get relationship details for logging
        repo = FollowingRepository(db)
        following_relation = await repo.get_following_relation(
            follower_id, following_id
        )

        if following_relation:
            relation_id = following_relation.id
        else:
            relation_id = 0

        # Unfollow user
        result = await repo.unfollow_user(follower_id, following_id)

        # Log admin activity if successful
        if result and admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="FOLLOWING",
                        entity_id=relation_id,
                        description=f"Deleted following relationship: User {follower_id} unfollowed user {following_id}",
                        metadata={
                            "follower_id": follower_id,
                            "following_id": following_id,
                            "relation_found": bool(following_relation),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        if result:
            logger.info(f"User {follower_id} unfollowed user {following_id}")
        else:
            logger.info(
                f"No follow relationship found for user {follower_id} and {following_id}"
            )

        return result
    except Exception as e:
        logger.error(f"Error unfollowing user: {str(e)}")
        raise


@cached(key_prefix="admin_user_followers", ttl=300)
async def get_user_followers(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    admin_id: Optional[int] = None,
) -> List[User]:
    """
    Lấy danh sách người đang follow người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách người dùng đang follow

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)
        followers = await repo.list_followers(user_id, skip, limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_FOLLOWERS",
                        entity_id=user_id,
                        description=f"Viewed followers of user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "skip": skip,
                            "limit": limit,
                            "results_count": len(followers),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return followers
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user followers: {str(e)}")
        raise


@cached(key_prefix="admin_user_following", ttl=300)
async def get_user_following(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    admin_id: Optional[int] = None,
) -> List[User]:
    """
    Lấy danh sách người mà người dùng đang follow.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách người dùng được follow

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)
        following = await repo.list_following(user_id, skip, limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_FOLLOWING",
                        entity_id=user_id,
                        description=f"Viewed users followed by user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "skip": skip,
                            "limit": limit,
                            "results_count": len(following),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return following
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user following: {str(e)}")
        raise


async def check_is_following(db: Session, follower_id: int, following_id: int) -> bool:
    """
    Kiểm tra xem người dùng có đang theo dõi người dùng khác không.

    Args:
        db: Database session
        follower_id: ID của người dùng thực hiện follow
        following_id: ID của người dùng được follow

    Returns:
        True nếu đang follow, False nếu không
    """
    try:
        repo = FollowingRepository(db)
        return await repo.check_is_following(follower_id, following_id)
    except Exception as e:
        logger.error(f"Error checking follow status: {str(e)}")
        raise


@cached(key_prefix="admin_user_followers", ttl=300)
async def get_user_followers(
    db: Session, user_id: int, skip: int = 0, limit: int = 20
) -> List[User]:
    """
    Lấy danh sách người đang follow người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách người dùng đang follow

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)
        return await repo.list_followers(user_id, skip, limit)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user followers: {str(e)}")
        raise


@cached(key_prefix="admin_user_following", ttl=300)
async def get_user_following(
    db: Session, user_id: int, skip: int = 0, limit: int = 20
) -> List[User]:
    """
    Lấy danh sách người mà người dùng đang follow.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách người dùng được follow

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)
        return await repo.list_following(user_id, skip, limit)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user following: {str(e)}")
        raise


async def count_followers(db: Session, user_id: int) -> int:
    """
    Đếm số người đang follow người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Số lượng người đang follow

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)
        return await repo.count_followers(user_id)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error counting followers: {str(e)}")
        raise


async def count_following(db: Session, user_id: int) -> int:
    """
    Đếm số người mà người dùng đang follow.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Số lượng người được follow

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)
        return await repo.count_following(user_id)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error counting following: {str(e)}")
        raise


async def get_mutual_followers(
    db: Session, user_id: int, other_user_id: int
) -> List[User]:
    """
    Lấy danh sách người dùng cùng follow cả hai người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng thứ nhất
        other_user_id: ID của người dùng thứ hai

    Returns:
        Danh sách người dùng cùng follow cả hai
    """
    try:
        repo = FollowingRepository(db)
        return await repo.get_mutual_followers(user_id, other_user_id)
    except Exception as e:
        logger.error(f"Error retrieving mutual followers: {str(e)}")
        raise


async def get_recent_followers(
    db: Session, user_id: int, limit: int = 5
) -> List[Tuple[User, datetime]]:
    """
    Lấy danh sách người mới follow người dùng gần đây.

    Args:
        db: Database session
        user_id: ID của người dùng
        limit: Số lượng người dùng tối đa trả về

    Returns:
        Danh sách (người dùng, thời gian follow)

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)
        return await repo.get_recent_followers(user_id, limit)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving recent followers: {str(e)}")
        raise


async def get_follow_suggestions(
    db: Session, user_id: int, limit: int = 10
) -> List[User]:
    """
    Đề xuất người dùng để follow.

    Args:
        db: Database session
        user_id: ID của người dùng
        limit: Số lượng đề xuất tối đa

    Returns:
        Danh sách người dùng được đề xuất

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)
        return await repo.get_follow_suggestions(user_id, limit)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving follow suggestions: {str(e)}")
        raise


async def get_following_statistics(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về follow của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê follow

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = FollowingRepository(db)

        followers_count = await repo.count_followers(user_id)
        following_count = await repo.count_following(user_id)

        # Lấy danh sách người mới follow gần đây
        recent_followers = await repo.get_recent_followers(user_id, 5)

        stats = {
            "user_id": user_id,
            "followers_count": followers_count,
            "following_count": following_count,
            "recent_followers": [
                (follower.id, created_at) for follower, created_at in recent_followers
            ],
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_FOLLOWING_STATISTICS",
                        entity_id=user_id,
                        description=f"Viewed following statistics for user {user_id}",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving following statistics: {str(e)}")
        raise


@cached(key_prefix="admin_following_statistics", ttl=3600)
async def get_following_system_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê tổng quan về hệ thống follow.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê hệ thống follow
    """
    try:
        # Tính tổng số mối quan hệ follow
        # (Cần triển khai ở repository)
        repo = FollowingRepository(db)

        # Đây là pseudocode, cần bổ sung phương thức này ở repository
        # total_relations = await repo.count_total_relations()
        total_relations = 0  # Tạm thời để 0

        # Đây là thống kê dự kiến, có thể cần thêm các phương thức ở repository
        stats = {
            "total_follow_relations": total_relations,
            "avg_followers_per_user": 0,  # Cần cài đặt phương thức ở repository
            "avg_following_per_user": 0,  # Cần cài đặt phương thức ở repository
            "most_followed_users": [],  # Cần cài đặt phương thức ở repository
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="FOLLOWING_SYSTEM_STATISTICS",
                        entity_id=0,
                        description="Viewed following system statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving following system statistics: {str(e)}")
        raise


async def delete_following(
    db: Session, following_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa quan hệ theo dõi theo ID.

    Args:
        db: Database session
        following_id: ID của quan hệ theo dõi cần xóa
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công, False nếu không tìm thấy
    """
    try:
        # Kiểm tra quan hệ follow tồn tại
        repo = FollowingRepository(db)
        following = await repo.get_by_id(following_id)

        if not following:
            logger.warning(f"Following relationship with ID {following_id} not found")
            return False

        # Lưu thông tin để ghi log
        follower_id = following.follower_id
        following_user_id = following.following_id

        # Xóa quan hệ follow
        success = await repo.delete_by_id(following_id)

        # Log admin activity
        if success and admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="FOLLOWING",
                        entity_id=following_id,
                        description=f"Admin deleted following relationship with ID {following_id}",
                        metadata={
                            "following_id": following_id,
                            "follower_id": follower_id,
                            "following_user_id": following_user_id,
                            "deleted_by_admin": True,
                            "admin_id": admin_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        if success:
            logger.info(
                f"Admin {admin_id} deleted following relationship ID {following_id}"
            )

        return success
    except Exception as e:
        logger.error(f"Error deleting following relationship: {str(e)}")
        raise
