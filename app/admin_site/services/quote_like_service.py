from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.models.quote import QuoteLike
from app.user_site.repositories.quote_like_repo import QuoteLikeRepository
from app.user_site.repositories.quote_repo import QuoteRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException, ForbiddenException, ConflictException
from app.common.utils.cache import cached, remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho quote like service
logger = logging.getLogger(__name__)


async def get_all_quote_likes(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    quote_id: Optional[int] = None,
    user_id: Optional[int] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[QuoteLike]:
    """
    Lấy danh sách lượt thích trích dẫn với bộ lọc.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa trả về
        quote_id: Lọc theo ID trích dẫn
        user_id: Lọc theo ID người dùng
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách lượt thích trích dẫn
    """
    try:
        repo = QuoteLikeRepository(db)
        likes = await repo.list_quote_likes(
            skip=skip,
            limit=limit,
            quote_id=quote_id,
            user_id=user_id,
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
                        entity_type="QUOTE_LIKES",
                        entity_id=0,
                        description="Viewed quote like list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "quote_id": quote_id,
                            "user_id": user_id,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(likes),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return likes
    except Exception as e:
        logger.error(f"Error retrieving quote likes: {str(e)}")
        raise


async def count_quote_likes(
    db: Session, quote_id: Optional[int] = None, user_id: Optional[int] = None
) -> int:
    """
    Đếm số lượng lượt thích trích dẫn.

    Args:
        db: Database session
        quote_id: Lọc theo ID trích dẫn
        user_id: Lọc theo ID người dùng

    Returns:
        Số lượng lượt thích trích dẫn
    """
    try:
        repo = QuoteLikeRepository(db)

        if quote_id:
            return await repo.count_by_quote(quote_id)
        elif user_id:
            return await repo.count_by_user(user_id)
        else:
            # Repository hiện tại không có phương thức count_all
            logger.warning(
                "Chưa có phương thức để đếm tất cả lượt thích trích dẫn, bổ sung vào repository"
            )
            return 0

    except Exception as e:
        logger.error(f"Lỗi khi đếm lượt thích trích dẫn: {str(e)}")
        raise


@cached(key_prefix="admin_quote_like", ttl=300)
async def get_quote_like_by_id(
    db: Session, like_id: int, admin_id: Optional[int] = None
) -> QuoteLike:
    """
    Lấy thông tin lượt thích trích dẫn theo ID.

    Args:
        db: Database session
        like_id: ID của lượt thích
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin lượt thích trích dẫn

    Raises:
        NotFoundException: Nếu không tìm thấy lượt thích
    """
    try:
        repo = QuoteLikeRepository(db)
        like = await repo.get_by_id(like_id)

        if not like:
            logger.warning(f"Quote like with ID {like_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy lượt thích với ID {like_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="QUOTE_LIKE",
                        entity_id=like_id,
                        description=f"Viewed quote like details for quote {like.quote_id}",
                        metadata={"quote_id": like.quote_id, "user_id": like.user_id},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return like
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving quote like: {str(e)}")
        raise


async def create_quote_like(
    db: Session, like_data: Dict[str, Any], admin_id: Optional[int] = None
) -> QuoteLike:
    """
    Tạo lượt thích trích dẫn mới.

    Args:
        db: Database session
        like_data: Dữ liệu lượt thích
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin lượt thích đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn hoặc người dùng
        ConflictException: Nếu lượt thích đã tồn tại
    """
    try:
        # Kiểm tra trích dẫn tồn tại
        if "quote_id" in like_data:
            quote_repo = QuoteRepository(db)
            quote = await quote_repo.get_by_id(like_data["quote_id"])

            if not quote:
                logger.warning(f"Quote with ID {like_data['quote_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy trích dẫn với ID {like_data['quote_id']}"
                )

        # Kiểm tra người dùng tồn tại
        if "user_id" in like_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(like_data["user_id"])

            if not user:
                logger.warning(f"User with ID {like_data['user_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {like_data['user_id']}"
                )

        # Kiểm tra xem lượt thích đã tồn tại chưa
        repo = QuoteLikeRepository(db)
        existing_like = await repo.get_by_quote_and_user(
            quote_id=like_data["quote_id"], user_id=like_data["user_id"]
        )

        if existing_like:
            logger.warning(
                f"Quote like already exists for quote {like_data['quote_id']} by user {like_data['user_id']}"
            )
            raise ConflictException(detail=f"Người dùng đã thích trích dẫn này")

        # Tạo lượt thích mới
        like = await repo.create(like_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="QUOTE_LIKE",
                        entity_id=like.id,
                        description=f"Created quote like for quote {like.quote_id}",
                        metadata={"quote_id": like.quote_id, "user_id": like.user_id},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Created new quote like with ID {like.id} for quote {like.quote_id}"
        )
        return like
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error creating quote like: {str(e)}")
        raise


async def delete_quote_like(
    db: Session, like_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa lượt thích trích dẫn.

    Args:
        db: Database session
        like_id: ID của lượt thích
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy lượt thích
    """
    try:
        # Get like details before deletion for logging
        like = await get_quote_like_by_id(db, like_id)

        repo = QuoteLikeRepository(db)
        await repo.delete(like_id)

        # Xóa cache
        remove_cache(f"admin_quote_like:{like_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="QUOTE_LIKE",
                        entity_id=like_id,
                        description=f"Deleted quote like for quote {like.quote_id}",
                        metadata={"quote_id": like.quote_id, "user_id": like.user_id},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted quote like with ID {like_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting quote like: {str(e)}")
        raise


async def delete_user_likes(db: Session, user_id: int) -> int:
    """
    Xóa tất cả lượt thích của một người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Số lượng lượt thích đã xóa

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

        # Xóa tất cả lượt thích của người dùng
        repo = QuoteLikeRepository(db)
        deleted_count = await repo.delete_by_user(user_id)

        logger.info(f"Đã xóa {deleted_count} lượt thích của người dùng {user_id}")
        return deleted_count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa lượt thích của người dùng: {str(e)}")
        raise


async def delete_quote_likes(db: Session, quote_id: int) -> int:
    """
    Xóa tất cả lượt thích của một trích dẫn.

    Args:
        db: Database session
        quote_id: ID của trích dẫn

    Returns:
        Số lượng lượt thích đã xóa

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn
    """
    try:
        # Kiểm tra trích dẫn tồn tại
        quote_repo = QuoteRepository(db)
        quote = await quote_repo.get_by_id(quote_id)

        if not quote:
            logger.warning(f"Không tìm thấy trích dẫn với ID {quote_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID {quote_id}"
            )

        # Xóa tất cả lượt thích của trích dẫn
        repo = QuoteLikeRepository(db)
        deleted_count = await repo.delete_by_quote(quote_id)

        # Cập nhật số lượt thích trong quote
        await quote_repo.update(quote.id, {"likes_count": 0})

        logger.info(f"Đã xóa {deleted_count} lượt thích của trích dẫn {quote_id}")
        return deleted_count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa lượt thích của trích dẫn: {str(e)}")
        raise


async def check_user_liked_quote(db: Session, user_id: int, quote_id: int) -> bool:
    """
    Kiểm tra người dùng đã thích trích dẫn chưa.

    Args:
        db: Database session
        user_id: ID của người dùng
        quote_id: ID của trích dẫn

    Returns:
        True nếu người dùng đã thích, False nếu chưa
    """
    try:
        repo = QuoteLikeRepository(db)
        like = await repo.get_by_user_and_quote(user_id, quote_id)
        return like is not None
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra thích trích dẫn: {str(e)}")
        raise


@cached(key_prefix="admin_quote_like_statistics", ttl=3600)
async def get_quote_like_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê lượt thích trích dẫn.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê lượt thích trích dẫn
    """
    try:
        repo = QuoteLikeRepository(db)

        total = await repo.count_quote_likes()

        # Thống kê theo trích dẫn
        by_quote = await repo.count_likes_by_quote()

        # Thống kê theo người dùng
        by_user = await repo.count_likes_by_user()

        stats = {"total": total, "by_quote": by_quote, "by_user": by_user}

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="QUOTE_LIKE_STATISTICS",
                        entity_id=0,
                        description="Viewed quote like statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving quote like statistics: {str(e)}")
        raise
