from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
import logging

from app.admin_site.models import Achievement
from app.admin_site.schemas.achievement import AchievementCreate, AchievementUpdate
from app.admin_site.repositories.achievement_repo import AchievementRepository
from app.logging.setup import get_logger
from app.user_site.models.achievement import UserAchievement
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho achievement service
logger = logging.getLogger(__name__)


def get_all_achievements(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    difficulty_level: Optional[str] = None,
    is_active: Optional[bool] = None,
    order_by: str = "name",
    order_desc: bool = False,
) -> List[Achievement]:
    """
    Lấy danh sách thành tựu.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        search: Tìm kiếm theo tên
        difficulty_level: Lọc theo độ khó
        is_active: Lọc theo trạng thái kích hoạt
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần nếu True

    Returns:
        Danh sách thành tựu
    """
    try:
        return AchievementRepository.get_all(
            db, skip, limit, search, difficulty_level, is_active, order_by, order_desc
        )
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thành tựu: {str(e)}")
        raise e


def count_achievements(
    db: Session,
    search: Optional[str] = None,
    difficulty_level: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> int:
    """
    Đếm số lượng thành tựu với các điều kiện lọc.

    Args:
        db: Database session
        search: Tìm kiếm theo tên
        difficulty_level: Lọc theo độ khó
        is_active: Lọc theo trạng thái kích hoạt

    Returns:
        Số lượng thành tựu
    """
    try:
        return AchievementRepository.count(db, search, difficulty_level, is_active)
    except Exception as e:
        logger.error(f"Lỗi khi đếm thành tựu: {str(e)}")
        raise e


def get_achievement_by_id(db: Session, achievement_id: int) -> Optional[Achievement]:
    """
    Lấy thông tin thành tựu theo ID.

    Args:
        db: Database session
        achievement_id: ID thành tựu

    Returns:
        Achievement object nếu tìm thấy, None nếu không
    """
    return AchievementRepository.get_by_id(db, achievement_id)


def get_achievement_by_name(db: Session, name: str) -> Optional[Achievement]:
    """
    Lấy thông tin thành tựu theo tên.

    Args:
        db: Database session
        name: Tên thành tựu

    Returns:
        Achievement object nếu tìm thấy, None nếu không
    """
    return AchievementRepository.get_by_name(db, name)


def create_achievement(db: Session, achievement_data: AchievementCreate) -> Achievement:
    """
    Tạo thành tựu mới.

    Args:
        db: Database session
        achievement_data: Thông tin thành tựu mới

    Returns:
        Achievement object đã tạo

    Raises:
        ValueError: Nếu có lỗi xảy ra
    """
    # Kiểm tra tên thành tựu đã tồn tại chưa
    existing_achievement = AchievementRepository.get_by_name(db, achievement_data.name)
    if existing_achievement:
        logger.warning(f"Tên thành tựu đã tồn tại: {achievement_data.name}")
        raise ValueError("Tên thành tựu đã tồn tại")

    # Chuẩn bị dữ liệu criteria_json
    criteria_json_str = None
    if achievement_data.criteria_json:
        try:
            if isinstance(achievement_data.criteria_json, str):
                # Kiểm tra nếu là chuỗi JSON hợp lệ
                json.loads(achievement_data.criteria_json)
                criteria_json_str = achievement_data.criteria_json
            else:
                # Chuyển đổi đối tượng thành chuỗi JSON
                criteria_json_str = json.dumps(achievement_data.criteria_json)
        except Exception as e:
            logger.error(f"Lỗi khi chuyển đổi criteria_json sang JSON: {str(e)}")
            raise ValueError("criteria_json không hợp lệ")

    # Chuẩn bị dữ liệu thành tựu
    achievement_dict = achievement_data.model_dump()
    achievement_dict["criteria_json"] = criteria_json_str
    achievement_dict["created_at"] = datetime.now(timezone.utc)
    achievement_dict["updated_at"] = datetime.now(timezone.utc)

    # Tạo thành tựu mới
    try:
        return AchievementRepository.create(db, achievement_dict)
    except Exception as e:
        logger.error(f"Lỗi khi tạo thành tựu: {str(e)}")
        raise ValueError(f"Không thể tạo thành tựu: {str(e)}")


def update_achievement(
    db: Session, achievement_id: int, achievement_data: AchievementUpdate
) -> Achievement:
    """
    Cập nhật thông tin thành tựu.

    Args:
        db: Database session
        achievement_id: ID thành tựu
        achievement_data: Thông tin cần cập nhật

    Returns:
        Achievement object đã cập nhật

    Raises:
        ValueError: Nếu thành tựu không tồn tại hoặc có lỗi khác
    """
    # Kiểm tra thành tựu tồn tại
    achievement = AchievementRepository.get_by_id(db, achievement_id)
    if not achievement:
        logger.warning(f"Thành tựu không tồn tại: ID {achievement_id}")
        raise ValueError("Thành tựu không tồn tại")

    # Kiểm tra tên thành tựu đã tồn tại chưa
    if achievement_data.name and achievement_data.name != achievement.name:
        existing = AchievementRepository.get_by_name(db, achievement_data.name)
        if existing and existing.id != achievement_id:
            logger.warning(f"Tên thành tựu đã tồn tại: {achievement_data.name}")
            raise ValueError("Tên thành tựu đã tồn tại")

    # Chuẩn bị dữ liệu cập nhật
    update_data = achievement_data.model_dump(exclude_unset=True)

    # Xử lý criteria_json nếu có
    if "criteria_json" in update_data and update_data["criteria_json"] is not None:
        try:
            if isinstance(update_data["criteria_json"], str):
                # Kiểm tra nếu là chuỗi JSON hợp lệ
                json.loads(update_data["criteria_json"])
            else:
                # Chuyển đổi đối tượng thành chuỗi JSON
                update_data["criteria_json"] = json.dumps(update_data["criteria_json"])
        except Exception as e:
            logger.error(f"Lỗi khi chuyển đổi criteria_json sang JSON: {str(e)}")
            raise ValueError("criteria_json không hợp lệ")

    update_data["updated_at"] = datetime.now(timezone.utc)

    # Cập nhật thành tựu
    try:
        return AchievementRepository.update(db, achievement_id, update_data)
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thành tựu: {str(e)}")
        raise ValueError(f"Không thể cập nhật thành tựu: {str(e)}")


def delete_achievement(db: Session, achievement_id: int) -> bool:
    """
    Xóa thành tựu.

    Args:
        db: Database session
        achievement_id: ID thành tựu

    Returns:
        True nếu xóa thành công, False nếu thất bại
    """
    try:
        return AchievementRepository.delete(db, achievement_id)
    except Exception as e:
        logger.error(f"Lỗi khi xóa thành tựu: {str(e)}")
        raise e


def toggle_achievement_status(db: Session, achievement_id: int) -> Achievement:
    """
    Bật/tắt trạng thái thành tựu.

    Args:
        db: Database session
        achievement_id: ID thành tựu

    Returns:
        Achievement object đã cập nhật

    Raises:
        ValueError: Nếu không tìm thấy thành tựu
    """
    try:
        achievement = AchievementRepository.toggle_status(db, achievement_id)
        if not achievement:
            raise ValueError(f"Không tìm thấy thành tựu với ID={achievement_id}")
        return achievement
    except Exception as e:
        logger.error(f"Lỗi khi thay đổi trạng thái thành tựu: {str(e)}")
        raise e


async def get_all_achievements(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    admin_id: Optional[int] = None,
) -> List[UserAchievement]:
    """
    Lấy danh sách thành tựu với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách thành tựu
    """
    try:
        repo = AchievementRepository(db)

        achievements = []
        if user_id:
            achievements = await repo.list_by_user(user_id, skip, limit)
        else:
            logger.warning("Yêu cầu lấy tất cả thành tựu không được hỗ trợ")

        # Log admin activity
        if admin_id:
            try:
                activity_description = "Viewed achievements"
                if user_id:
                    activity_description = f"Viewed achievements for user {user_id}"

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ACHIEVEMENTS",
                        entity_id=0,
                        description=activity_description,
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "results_count": len(achievements),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return achievements
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thành tựu: {str(e)}")
        raise


async def count_achievements(db: Session, user_id: Optional[int] = None) -> int:
    """
    Đếm số lượng thành tựu.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng

    Returns:
        Số lượng thành tựu
    """
    try:
        repo = AchievementRepository(db)

        if user_id:
            return await repo.count_by_user(user_id)
        else:
            logger.warning("Yêu cầu đếm tất cả thành tựu không được hỗ trợ")
            return 0
    except Exception as e:
        logger.error(f"Lỗi khi đếm thành tựu: {str(e)}")
        raise


@cached(key_prefix="admin_achievement", ttl=300)
async def get_achievement_by_id(
    db: Session,
    achievement_id: int,
    with_relations: bool = False,
    admin_id: Optional[int] = None,
) -> UserAchievement:
    """
    Lấy thông tin thành tựu theo ID.

    Args:
        db: Database session
        achievement_id: ID của thành tựu
        with_relations: Có load các mối quan hệ không
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thành tựu

    Raises:
        NotFoundException: Nếu không tìm thấy thành tựu
    """
    try:
        repo = AchievementRepository(db)
        achievement = await repo.get_by_id(achievement_id, with_relations)

        if not achievement:
            logger.warning(f"Không tìm thấy thành tựu với ID {achievement_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy thành tựu với ID {achievement_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ACHIEVEMENT",
                        entity_id=achievement_id,
                        description=f"Viewed achievement details for ID {achievement_id}",
                        metadata={
                            "user_id": (
                                achievement.user_id
                                if hasattr(achievement, "user_id")
                                else None
                            ),
                            "achievement_id": (
                                achievement.achievement_id
                                if hasattr(achievement, "achievement_id")
                                else None
                            ),
                            "earned_at": (
                                achievement.earned_at.isoformat()
                                if hasattr(achievement, "earned_at")
                                and achievement.earned_at
                                else None
                            ),
                            "progress": (
                                achievement.progress
                                if hasattr(achievement, "progress")
                                else None
                            ),
                            "with_relations": with_relations,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return achievement
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin thành tựu: {str(e)}")
        raise


async def get_achievement_by_user_and_achievement(
    db: Session, user_id: int, achievement_id: int
) -> UserAchievement:
    """
    Lấy thông tin thành tựu theo user_id và achievement_id.

    Args:
        db: Database session
        user_id: ID của người dùng
        achievement_id: ID của loại thành tựu

    Returns:
        Thông tin thành tựu

    Raises:
        NotFoundException: Nếu không tìm thấy thành tựu
    """
    try:
        repo = AchievementRepository(db)
        achievement = await repo.get_by_user_and_achievement(user_id, achievement_id)

        if not achievement:
            logger.warning(
                f"Không tìm thấy thành tựu với user_id {user_id} và achievement_id {achievement_id}"
            )
            raise NotFoundException(
                detail=f"Không tìm thấy thành tựu với user_id {user_id} và achievement_id {achievement_id}"
            )

        return achievement
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin thành tựu: {str(e)}")
        raise


async def create_achievement(
    db: Session, achievement_data: Dict[str, Any], admin_id: Optional[int] = None
) -> UserAchievement:
    """
    Tạo thành tựu mới.

    Args:
        db: Database session
        achievement_data: Dữ liệu thành tựu
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thành tựu đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
        ForbiddenException: Nếu người dùng đã có thành tựu này
    """
    try:
        # Kiểm tra người dùng tồn tại
        user = None
        if "user_id" in achievement_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(achievement_data["user_id"])

            if not user:
                logger.warning(
                    f"Không tìm thấy người dùng với ID {achievement_data['user_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {achievement_data['user_id']}"
                )

        # Kiểm tra người dùng đã có thành tựu này chưa
        if "user_id" in achievement_data and "achievement_id" in achievement_data:
            repo = AchievementRepository(db)
            existing_achievement = await repo.get_by_user_and_achievement(
                achievement_data["user_id"], achievement_data["achievement_id"]
            )

            if existing_achievement:
                logger.warning(
                    f"Người dùng {achievement_data['user_id']} đã có thành tựu {achievement_data['achievement_id']}"
                )
                raise ForbiddenException(detail=f"Người dùng đã có thành tựu này")

        # Tạo thành tựu mới
        repo = AchievementRepository(db)
        achievement = await repo.create(achievement_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="ACHIEVEMENT",
                        entity_id=achievement.id,
                        description=f"Created achievement for user {achievement_data.get('user_id')}",
                        metadata={
                            "user_id": achievement_data.get("user_id"),
                            "username": (
                                user.username
                                if user and hasattr(user, "username")
                                else None
                            ),
                            "achievement_id": achievement_data.get("achievement_id"),
                            "progress": achievement_data.get("progress"),
                            "earned_at": achievement_data.get("earned_at"),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache if needed
        if "user_id" in achievement_data:
            invalidate_cache(f"admin_user_achievements:{achievement_data['user_id']}")

        logger.info(f"Đã tạo thành tựu mới với ID {achievement.id}")
        return achievement
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo thành tựu: {str(e)}")
        raise


async def delete_achievement(
    db: Session, achievement_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa thành tựu.

    Args:
        db: Database session
        achievement_id: ID của thành tựu
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy thành tựu
    """
    try:
        # Kiểm tra thành tựu tồn tại
        achievement = await get_achievement_by_id(db, achievement_id)

        # Xóa thành tựu
        repo = AchievementRepository(db)
        result = await repo.delete(achievement_id)

        # Log admin activity
        if admin_id and result:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="ACHIEVEMENT",
                        entity_id=achievement_id,
                        description=f"Deleted achievement for user {achievement.user_id if hasattr(achievement, 'user_id') else 'unknown'}",
                        metadata={
                            "user_id": (
                                achievement.user_id
                                if hasattr(achievement, "user_id")
                                else None
                            ),
                            "achievement_id": (
                                achievement.achievement_id
                                if hasattr(achievement, "achievement_id")
                                else None
                            ),
                            "earned_at": (
                                achievement.earned_at.isoformat()
                                if hasattr(achievement, "earned_at")
                                and achievement.earned_at
                                else None
                            ),
                            "progress": (
                                achievement.progress
                                if hasattr(achievement, "progress")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_achievement:{achievement_id}")
        if hasattr(achievement, "user_id") and achievement.user_id:
            invalidate_cache(f"admin_user_achievements:{achievement.user_id}")

        logger.info(f"Đã xóa thành tựu với ID {achievement_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa thành tựu: {str(e)}")
        raise


async def delete_user_achievement(
    db: Session, user_id: int, achievement_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa thành tựu của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        achievement_id: ID của loại thành tựu
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công, False nếu không tìm thấy
    """
    try:
        # Check if achievement exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        username = user.username if user and hasattr(user, "username") else "unknown"

        repo = AchievementRepository(db)
        result = await repo.delete_by_user_and_achievement(user_id, achievement_id)

        # Log admin activity if deletion was successful
        if admin_id and result:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="USER_ACHIEVEMENT",
                        entity_id=0,
                        description=f"Deleted achievement {achievement_id} for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": username,
                            "achievement_id": achievement_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_user_achievements:{user_id}")

        if result:
            logger.info(
                f"Đã xóa thành tựu của người dùng {user_id} với achievement_id {achievement_id}"
            )
        else:
            logger.warning(
                f"Không tìm thấy thành tựu để xóa với user_id {user_id} và achievement_id {achievement_id}"
            )

        return result
    except Exception as e:
        logger.error(f"Lỗi khi xóa thành tựu của người dùng: {str(e)}")
        raise


@cached(key_prefix="admin_user_achievements", ttl=300)
async def get_user_achievements(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    admin_id: Optional[int] = None,
) -> List[UserAchievement]:
    """
    Lấy danh sách thành tựu của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách thành tựu của người dùng

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"Không tìm thấy người dùng với ID {user_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Lấy danh sách thành tựu
        repo = AchievementRepository(db)
        achievements = await repo.list_by_user(user_id, skip, limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_ACHIEVEMENTS",
                        entity_id=user_id,
                        description=f"Viewed achievements for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "skip": skip,
                            "limit": limit,
                            "results_count": len(achievements),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return achievements
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thành tựu của người dùng: {str(e)}")
        raise


@cached(key_prefix="admin_achievement_statistics", ttl=3600)
async def get_achievement_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về thành tựu.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê thành tựu
    """
    try:
        # Đây là code demo, cần bổ sung các phương thức hỗ trợ trong repository
        stats = {
            "total_achievements": 0,  # Cần bổ sung phương thức count_all
            "users_with_achievements": 0,  # Cần bổ sung phương thức count_users_with_achievements
            "most_common_achievements": [],  # Cần bổ sung phương thức get_most_common_achievements
            "achievements_by_month": [],  # Cần bổ sung phương thức get_achievements_by_month
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ACHIEVEMENT_STATISTICS",
                        entity_id=0,
                        description="Viewed achievement statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê thành tựu: {str(e)}")
        raise
