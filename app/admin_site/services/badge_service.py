from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import logging

from app.admin_site.models import Badge
from app.admin_site.schemas.badge import BadgeCreate, BadgeUpdate
from app.admin_site.repositories.badge_repo import BadgeRepository
from app.cache.decorators import cached, invalidate_cache
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ServerException,
    ValidationException,
    ForbiddenException,
)
from app.logging.setup import get_logger
from app.user_site.models.badge import UserBadge
from app.user_site.repositories.user_repo import UserRepository
from app.common.utils.cache import remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho badge service
logger = logging.getLogger(__name__)


@cached(ttl=300, namespace="admin:badges", tags=["badges"])
def get_all_badges(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    badge_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    order_by: str = "name",
    order_desc: bool = False,
) -> List[Badge]:
    """
    Lấy danh sách huy hiệu với các tùy chọn lọc.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        search: Tìm kiếm theo tên, mô tả
        badge_type: Lọc theo loại huy hiệu
        is_active: Lọc theo trạng thái kích hoạt
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần nếu True

    Returns:
        Danh sách huy hiệu
    """
    try:
        return BadgeRepository.get_all(
            db=db,
            skip=skip,
            limit=limit,
            search=search,
            badge_type=badge_type,
            is_active=is_active,
            order_by=order_by,
            order_desc=order_desc,
        )
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách huy hiệu: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách huy hiệu: {str(e)}")


def count_badges(
    db: Session,
    search: Optional[str] = None,
    badge_type: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> int:
    """
    Đếm số lượng huy hiệu theo điều kiện lọc.

    Args:
        db: Database session
        search: Tìm kiếm theo tên, mô tả
        badge_type: Lọc theo loại huy hiệu
        is_active: Lọc theo trạng thái kích hoạt

    Returns:
        Tổng số huy hiệu thỏa mãn điều kiện
    """
    try:
        return BadgeRepository.count(
            db=db, search=search, badge_type=badge_type, is_active=is_active
        )
    except Exception as e:
        logger.error(f"Lỗi khi đếm huy hiệu: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm huy hiệu: {str(e)}")


@cached(ttl=3600, namespace="admin:badges", tags=["badges"])
def get_badge_by_id(db: Session, badge_id: int) -> Badge:
    """
    Lấy thông tin huy hiệu theo ID.

    Args:
        db: Database session
        badge_id: ID huy hiệu

    Returns:
        Badge object

    Raises:
        NotFoundException: Nếu không tìm thấy huy hiệu
    """
    badge = BadgeRepository.get_by_id(db, badge_id)
    if not badge:
        logger.warning(f"Không tìm thấy huy hiệu với ID={badge_id}")
        raise NotFoundException(detail=f"Không tìm thấy huy hiệu với ID={badge_id}")
    return badge


@cached(ttl=3600, namespace="admin:badges", tags=["badges"])
def get_badge_by_name(db: Session, name: str) -> Optional[Badge]:
    """
    Lấy thông tin huy hiệu theo tên.

    Args:
        db: Database session
        name: Tên huy hiệu

    Returns:
        Badge object hoặc None nếu không tìm thấy
    """
    return BadgeRepository.get_by_name(db, name)


@invalidate_cache(tags=["badges"])
def create_badge(db: Session, badge_data: BadgeCreate) -> Badge:
    """
    Tạo huy hiệu mới.

    Args:
        db: Database session
        badge_data: Thông tin huy hiệu mới

    Returns:
        Badge object đã tạo

    Raises:
        ConflictException: Nếu tên huy hiệu đã tồn tại
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra tên huy hiệu đã tồn tại chưa
    existing_badge = BadgeRepository.get_by_name(db, badge_data.name)
    if existing_badge:
        logger.warning(f"Tên huy hiệu đã tồn tại: {badge_data.name}")
        raise ConflictException(detail="Tên huy hiệu đã tồn tại", field="name")

    # Chuẩn bị dữ liệu
    badge_dict = badge_data.model_dump()
    badge_dict.update(
        {"created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
    )

    # Tạo huy hiệu mới
    try:
        return BadgeRepository.create(db, badge_dict)
    except Exception as e:
        logger.error(f"Lỗi khi tạo huy hiệu: {str(e)}")
        raise ServerException(detail=f"Không thể tạo huy hiệu: {str(e)}")


@invalidate_cache(tags=["badges"])
def update_badge(db: Session, badge_id: int, badge_data: BadgeUpdate) -> Badge:
    """
    Cập nhật thông tin huy hiệu.

    Args:
        db: Database session
        badge_id: ID huy hiệu
        badge_data: Thông tin cần cập nhật

    Returns:
        Badge object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy huy hiệu
        ConflictException: Nếu tên huy hiệu đã tồn tại
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra huy hiệu tồn tại
    badge = BadgeRepository.get_by_id(db, badge_id)
    if not badge:
        logger.warning(f"Không tìm thấy huy hiệu với ID={badge_id}")
        raise NotFoundException(detail=f"Không tìm thấy huy hiệu với ID={badge_id}")

    # Kiểm tra tên huy hiệu đã tồn tại chưa nếu có thay đổi tên
    if badge_data.name and badge_data.name != badge.name:
        existing_badge = BadgeRepository.get_by_name(db, badge_data.name)
        if existing_badge:
            logger.warning(f"Tên huy hiệu đã tồn tại: {badge_data.name}")
            raise ConflictException(detail="Tên huy hiệu đã tồn tại", field="name")

    # Chuẩn bị dữ liệu cập nhật
    update_data = badge_data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Cập nhật huy hiệu
    try:
        updated_badge = BadgeRepository.update(db, badge_id, update_data)
        if not updated_badge:
            raise NotFoundException(detail=f"Không tìm thấy huy hiệu với ID={badge_id}")
        return updated_badge
    except Exception as e:
        if isinstance(e, NotFoundException):
            raise e
        logger.error(f"Lỗi khi cập nhật huy hiệu: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật huy hiệu: {str(e)}")


@invalidate_cache(tags=["badges"])
def delete_badge(db: Session, badge_id: int) -> bool:
    """
    Xóa huy hiệu.

    Args:
        db: Database session
        badge_id: ID huy hiệu

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy huy hiệu
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra huy hiệu tồn tại
    badge = BadgeRepository.get_by_id(db, badge_id)
    if not badge:
        logger.warning(f"Không tìm thấy huy hiệu với ID={badge_id}")
        raise NotFoundException(detail=f"Không tìm thấy huy hiệu với ID={badge_id}")

    # TODO: Kiểm tra xem huy hiệu có đang được sử dụng không
    # Có thể thêm repository method để kiểm tra xem có user đang sở hữu badge này không

    # Xóa huy hiệu
    try:
        success = BadgeRepository.delete(db, badge_id)
        if not success:
            raise ServerException(detail=f"Không thể xóa huy hiệu với ID={badge_id}")
        return True
    except Exception as e:
        if isinstance(e, NotFoundException) or isinstance(e, ServerException):
            raise e
        logger.error(f"Lỗi khi xóa huy hiệu: {str(e)}")
        raise ServerException(detail=f"Không thể xóa huy hiệu: {str(e)}")


@invalidate_cache(tags=["badges"])
def toggle_badge_status(db: Session, badge_id: int) -> Badge:
    """
    Bật/tắt trạng thái của huy hiệu.

    Args:
        db: Database session
        badge_id: ID huy hiệu

    Returns:
        Badge object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy huy hiệu
        ServerException: Nếu có lỗi khác xảy ra
    """
    try:
        # Gọi repository method để toggle status
        badge = BadgeRepository.toggle_status(db, badge_id)
        if not badge:
            raise NotFoundException(detail=f"Không tìm thấy huy hiệu với ID={badge_id}")
        return badge
    except Exception as e:
        if isinstance(e, NotFoundException):
            raise e
        logger.error(f"Lỗi khi thay đổi trạng thái huy hiệu: {str(e)}")
        raise ServerException(
            detail=f"Không thể thay đổi trạng thái huy hiệu: {str(e)}"
        )


async def get_all_badges(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    admin_id: Optional[int] = None,
) -> List[UserBadge]:
    """
    Lấy danh sách huy hiệu với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách huy hiệu
    """
    try:
        repo = BadgeRepository(db)

        badges = []
        if user_id:
            badges = await repo.list_by_user(user_id, skip, limit)
        else:
            logger.warning("Yêu cầu lấy tất cả huy hiệu không được hỗ trợ")

        # Log admin activity
        if admin_id:
            try:
                activity_description = "Viewed badges"
                if user_id:
                    activity_description = f"Viewed badges for user {user_id}"

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BADGES",
                        entity_id=0,
                        description=activity_description,
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "results_count": len(badges),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return badges
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách huy hiệu: {str(e)}")
        raise


async def count_badges(db: Session, user_id: Optional[int] = None) -> int:
    """
    Đếm số lượng huy hiệu.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng

    Returns:
        Số lượng huy hiệu
    """
    try:
        repo = BadgeRepository(db)

        if user_id:
            return await repo.count_by_user(user_id)
        else:
            logger.warning("Yêu cầu đếm tất cả huy hiệu không được hỗ trợ")
            return 0
    except Exception as e:
        logger.error(f"Lỗi khi đếm huy hiệu: {str(e)}")
        raise


@cached(key_prefix="admin_badge", ttl=300)
async def get_badge_by_id(
    db: Session,
    badge_id: int,
    with_relations: bool = False,
    admin_id: Optional[int] = None,
) -> UserBadge:
    """
    Lấy thông tin huy hiệu theo ID.

    Args:
        db: Database session
        badge_id: ID của huy hiệu
        with_relations: Có load các mối quan hệ không
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin huy hiệu

    Raises:
        NotFoundException: Nếu không tìm thấy huy hiệu
    """
    try:
        repo = BadgeRepository(db)
        badge = await repo.get_by_id(badge_id, with_relations)

        if not badge:
            logger.warning(f"Không tìm thấy huy hiệu với ID {badge_id}")
            raise NotFoundException(detail=f"Không tìm thấy huy hiệu với ID {badge_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BADGE",
                        entity_id=badge_id,
                        description=f"Viewed badge details for ID {badge_id}",
                        metadata={
                            "user_id": (
                                badge.user_id if hasattr(badge, "user_id") else None
                            ),
                            "badge_id": (
                                badge.badge_id if hasattr(badge, "badge_id") else None
                            ),
                            "earned_at": (
                                badge.earned_at.isoformat()
                                if hasattr(badge, "earned_at") and badge.earned_at
                                else None
                            ),
                            "with_relations": with_relations,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return badge
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin huy hiệu: {str(e)}")
        raise


async def get_badge_by_user_and_badge(
    db: Session, user_id: int, badge_id: int, admin_id: Optional[int] = None
) -> UserBadge:
    """
    Lấy thông tin huy hiệu theo user_id và badge_id.

    Args:
        db: Database session
        user_id: ID của người dùng
        badge_id: ID của loại huy hiệu
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin huy hiệu

    Raises:
        NotFoundException: Nếu không tìm thấy huy hiệu
    """
    try:
        repo = BadgeRepository(db)
        badge = await repo.get_by_user_and_badge(user_id, badge_id)

        if not badge:
            logger.warning(
                f"Không tìm thấy huy hiệu với user_id {user_id} và badge_id {badge_id}"
            )
            raise NotFoundException(
                detail=f"Không tìm thấy huy hiệu với user_id {user_id} và badge_id {badge_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                # Get username for logging
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(user_id)
                username = user.username if user and hasattr(user, "username") else None

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_BADGE",
                        entity_id=badge.id if hasattr(badge, "id") else 0,
                        description=f"Viewed badge {badge_id} for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": username,
                            "badge_id": badge_id,
                            "earned_at": (
                                badge.earned_at.isoformat()
                                if hasattr(badge, "earned_at") and badge.earned_at
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return badge
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin huy hiệu: {str(e)}")
        raise


async def create_badge(
    db: Session, badge_data: Dict[str, Any], admin_id: Optional[int] = None
) -> UserBadge:
    """
    Tạo huy hiệu mới.

    Args:
        db: Database session
        badge_data: Dữ liệu huy hiệu
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin huy hiệu đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
        ForbiddenException: Nếu người dùng đã có huy hiệu này
    """
    try:
        # Kiểm tra người dùng tồn tại
        user = None
        if "user_id" in badge_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(badge_data["user_id"])

            if not user:
                logger.warning(
                    f"Không tìm thấy người dùng với ID {badge_data['user_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {badge_data['user_id']}"
                )

        # Kiểm tra người dùng đã có huy hiệu này chưa
        if "user_id" in badge_data and "badge_id" in badge_data:
            repo = BadgeRepository(db)
            existing_badge = await repo.get_by_user_and_badge(
                badge_data["user_id"], badge_data["badge_id"]
            )

            if existing_badge:
                logger.warning(
                    f"Người dùng {badge_data['user_id']} đã có huy hiệu {badge_data['badge_id']}"
                )
                raise ForbiddenException(detail=f"Người dùng đã có huy hiệu này")

        # Tạo huy hiệu mới
        repo = BadgeRepository(db)
        badge = await repo.create(badge_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="BADGE",
                        entity_id=badge.id,
                        description=f"Created badge for user {badge_data.get('user_id')}",
                        metadata={
                            "user_id": badge_data.get("user_id"),
                            "username": (
                                user.username
                                if user and hasattr(user, "username")
                                else None
                            ),
                            "badge_id": badge_data.get("badge_id"),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache if needed
        if "user_id" in badge_data:
            remove_cache(f"admin_user_badges:{badge_data['user_id']}")

        logger.info(f"Đã tạo huy hiệu mới với ID {badge.id}")
        return badge
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo huy hiệu: {str(e)}")
        raise


async def delete_badge(
    db: Session, badge_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa huy hiệu.

    Args:
        db: Database session
        badge_id: ID của huy hiệu
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy huy hiệu
    """
    try:
        # Kiểm tra huy hiệu tồn tại
        badge = await get_badge_by_id(db, badge_id)

        # Xóa huy hiệu
        repo = BadgeRepository(db)
        result = await repo.delete(badge_id)

        # Log admin activity
        if admin_id and result:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="BADGE",
                        entity_id=badge_id,
                        description=f"Deleted badge for user {badge.user_id if hasattr(badge, 'user_id') else 'unknown'}",
                        metadata={
                            "user_id": (
                                badge.user_id if hasattr(badge, "user_id") else None
                            ),
                            "badge_id": (
                                badge.badge_id if hasattr(badge, "badge_id") else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        remove_cache(f"admin_badge:{badge_id}")
        if hasattr(badge, "user_id") and badge.user_id:
            remove_cache(f"admin_user_badges:{badge.user_id}")

        logger.info(f"Đã xóa huy hiệu với ID {badge_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa huy hiệu: {str(e)}")
        raise


async def delete_user_badge(
    db: Session, user_id: int, badge_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa huy hiệu của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        badge_id: ID của loại huy hiệu
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công, False nếu không tìm thấy
    """
    try:
        # Get user info for logging
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        username = user.username if user and hasattr(user, "username") else "unknown"

        repo = BadgeRepository(db)
        result = await repo.delete_by_user_and_badge(user_id, badge_id)

        # Log admin activity if deletion was successful
        if admin_id and result:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="USER_BADGE",
                        entity_id=0,
                        description=f"Deleted badge {badge_id} for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": username,
                            "badge_id": badge_id,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        remove_cache(f"admin_user_badges:{user_id}")

        if result:
            logger.info(
                f"Đã xóa huy hiệu của người dùng {user_id} với badge_id {badge_id}"
            )
        else:
            logger.warning(
                f"Không tìm thấy huy hiệu để xóa với user_id {user_id} và badge_id {badge_id}"
            )

        return result
    except Exception as e:
        logger.error(f"Lỗi khi xóa huy hiệu của người dùng: {str(e)}")
        raise


@cached(key_prefix="admin_user_badges", ttl=300)
async def get_user_badges(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    admin_id: Optional[int] = None,
) -> List[UserBadge]:
    """
    Lấy danh sách huy hiệu của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách huy hiệu của người dùng

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

        # Lấy danh sách huy hiệu
        repo = BadgeRepository(db)
        badges = await repo.list_by_user(user_id, skip, limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_BADGES",
                        entity_id=user_id,
                        description=f"Viewed badges for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "skip": skip,
                            "limit": limit,
                            "results_count": len(badges),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return badges
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách huy hiệu của người dùng: {str(e)}")
        raise


@cached(key_prefix="admin_badge_statistics", ttl=3600)
async def get_badge_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về huy hiệu.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê huy hiệu
    """
    try:
        # Đây là code demo, cần bổ sung các phương thức hỗ trợ trong repository
        stats = {
            "total_badges": 0,  # Cần bổ sung phương thức count_all
            "users_with_badges": 0,  # Cần bổ sung phương thức count_users_with_badges
            "most_common_badges": [],  # Cần bổ sung phương thức get_most_common_badges
            "badges_by_month": [],  # Cần bổ sung phương thức get_badges_by_month
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BADGE_STATISTICS",
                        entity_id=0,
                        description="Viewed badge statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê huy hiệu: {str(e)}")
        raise
