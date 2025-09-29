from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.user_site.models.reading_history import ReadingHistory
from app.user_site.repositories.reading_history_repo import ReadingHistoryRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import NotFoundException
from app.common.utils.cache import cached, remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho reading history service
logger = logging.getLogger(__name__)


async def get_all_reading_histories(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    sort_by: str = "last_read_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[ReadingHistory]:
    """
    Lấy danh sách lịch sử đọc với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách lịch sử đọc
    """
    try:
        repo = ReadingHistoryRepository(db)
        histories = await repo.list_histories(
            skip=skip,
            limit=limit,
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            from_date=from_date,
            to_date=to_date,
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
                        entity_type="READING_HISTORIES",
                        entity_id=0,
                        description="Viewed reading history list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "book_id": book_id,
                            "chapter_id": chapter_id,
                            "from_date": from_date.isoformat() if from_date else None,
                            "to_date": to_date.isoformat() if to_date else None,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(histories),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return histories
    except Exception as e:
        logger.error(f"Error retrieving reading histories: {str(e)}")
        raise


async def count_reading_histories(
    db: Session,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> int:
    """
    Đếm số lượng lịch sử đọc.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày

    Returns:
        Số lượng lịch sử đọc
    """
    try:
        repo = ReadingHistoryRepository(db)
        return await repo.count_histories(
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as e:
        logger.error(f"Error counting reading histories: {str(e)}")
        raise


@cached(key_prefix="admin_reading_history", ttl=300)
async def get_reading_history_by_id(
    db: Session, history_id: int, admin_id: Optional[int] = None
) -> ReadingHistory:
    """
    Lấy thông tin lịch sử đọc theo ID.

    Args:
        db: Database session
        history_id: ID của lịch sử đọc
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin lịch sử đọc

    Raises:
        NotFoundException: Nếu không tìm thấy lịch sử đọc
    """
    try:
        repo = ReadingHistoryRepository(db)
        history = await repo.get_by_id(history_id)

        if not history:
            logger.warning(f"Reading history with ID {history_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy lịch sử đọc với ID {history_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_HISTORY",
                        entity_id=history_id,
                        description=f"Viewed reading history details for user {history.user_id}",
                        metadata={
                            "user_id": history.user_id,
                            "book_id": history.book_id,
                            "chapter_id": history.chapter_id,
                            "last_read_at": (
                                history.last_read_at.isoformat()
                                if hasattr(history, "last_read_at")
                                else None
                            ),
                            "last_position": history.last_position,
                            "completion_percentage": history.completion_percentage,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return history
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving reading history: {str(e)}")
        raise


async def get_user_book_history(
    db: Session, user_id: int, book_id: int
) -> Optional[ReadingHistory]:
    """
    Lấy lịch sử đọc của người dùng cho một sách cụ thể.

    Args:
        db: Database session
        user_id: ID của người dùng
        book_id: ID của sách

    Returns:
        Thông tin lịch sử đọc hoặc None nếu không có
    """
    try:
        repo = ReadingHistoryRepository(db)
        return await repo.get_by_user_and_book(user_id, book_id)
    except Exception as e:
        logger.error(f"Error retrieving user book history: {str(e)}")
        raise


async def get_user_chapter_history(
    db: Session, user_id: int, chapter_id: int
) -> Optional[ReadingHistory]:
    """
    Lấy lịch sử đọc của người dùng cho một chương cụ thể.

    Args:
        db: Database session
        user_id: ID của người dùng
        chapter_id: ID của chương

    Returns:
        Thông tin lịch sử đọc hoặc None nếu không có
    """
    try:
        repo = ReadingHistoryRepository(db)
        return await repo.get_by_user_and_chapter(user_id, chapter_id)
    except Exception as e:
        logger.error(f"Error retrieving user chapter history: {str(e)}")
        raise


async def get_user_reading_histories(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    admin_id: Optional[int] = None,
) -> List[ReadingHistory]:
    """
    Lấy danh sách lịch sử đọc của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách lịch sử đọc
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = ReadingHistoryRepository(db)
        histories = await repo.list_histories(
            user_id=user_id,
            skip=skip,
            limit=limit,
            sort_by="last_read_at",
            sort_desc=True,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_READING_HISTORIES",
                        entity_id=user_id,
                        description=f"Viewed reading histories for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "skip": skip,
                            "limit": limit,
                            "results_count": len(histories),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return histories
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user reading histories: {str(e)}")
        raise


async def get_book_reading_histories(
    db: Session,
    book_id: int,
    skip: int = 0,
    limit: int = 20,
    admin_id: Optional[int] = None,
) -> List[ReadingHistory]:
    """
    Lấy danh sách lịch sử đọc của một sách.

    Args:
        db: Database session
        book_id: ID của sách
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách lịch sử đọc
    """
    try:
        repo = ReadingHistoryRepository(db)
        histories = await repo.list_histories(
            book_id=book_id,
            skip=skip,
            limit=limit,
            sort_by="last_read_at",
            sort_desc=True,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOK_READING_HISTORIES",
                        entity_id=book_id,
                        description=f"Viewed reading histories for book {book_id}",
                        metadata={
                            "book_id": book_id,
                            "skip": skip,
                            "limit": limit,
                            "results_count": len(histories),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return histories
    except Exception as e:
        logger.error(f"Error retrieving book reading histories: {str(e)}")
        raise


async def get_chapter_reading_histories(
    db: Session, chapter_id: int, skip: int = 0, limit: int = 20
) -> List[ReadingHistory]:
    """
    Lấy danh sách lịch sử đọc của một chương.

    Args:
        db: Database session
        chapter_id: ID của chương
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách lịch sử đọc
    """
    try:
        repo = ReadingHistoryRepository(db)
        return await repo.list_histories(
            chapter_id=chapter_id,
            skip=skip,
            limit=limit,
            sort_by="last_read_at",
            sort_desc=True,
        )
    except Exception as e:
        logger.error(f"Error retrieving chapter reading histories: {str(e)}")
        raise


async def delete_reading_history(
    db: Session, history_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa lịch sử đọc.

    Args:
        db: Database session
        history_id: ID của lịch sử đọc
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy lịch sử đọc
    """
    try:
        # Kiểm tra lịch sử đọc tồn tại và lấy thông tin
        history = await get_reading_history_by_id(db, history_id)

        # Xóa lịch sử đọc
        repo = ReadingHistoryRepository(db)
        await repo.delete(history_id)

        # Log admin activity
        if admin_id:
            try:
                # Get username for logging
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(history.user_id)
                username = user.username if user and hasattr(user, "username") else None

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="READING_HISTORY",
                        entity_id=history_id,
                        description=f"Deleted reading history for user {history.user_id}",
                        metadata={
                            "user_id": history.user_id,
                            "username": username,
                            "book_id": history.book_id,
                            "chapter_id": history.chapter_id,
                            "last_read_at": (
                                history.last_read_at.isoformat()
                                if hasattr(history, "last_read_at")
                                else None
                            ),
                            "completion_percentage": history.completion_percentage,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        remove_cache(f"admin_reading_history:{history_id}")

        logger.info(f"Deleted reading history with ID {history_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting reading history: {str(e)}")
        raise


async def create_reading_history(
    db: Session, history_data: Dict[str, Any], admin_id: Optional[int] = None
) -> ReadingHistory:
    """
    Tạo lịch sử đọc mới.

    Args:
        db: Database session
        history_data: Dữ liệu lịch sử đọc
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin lịch sử đọc đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng hoặc sách
    """
    try:
        # Kiểm tra người dùng tồn tại
        if "user_id" in history_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(history_data["user_id"])

            if not user:
                logger.warning(f"User with ID {history_data['user_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {history_data['user_id']}"
                )

        # Kiểm tra sách tồn tại
        if "book_id" in history_data:
            book_repo = BookRepository(db)
            book = await book_repo.get_by_id(history_data["book_id"])

            if not book:
                logger.warning(f"Book with ID {history_data['book_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy sách với ID {history_data['book_id']}"
                )

        # Tạo lịch sử đọc mới
        repo = ReadingHistoryRepository(db)
        history = await repo.create(history_data)

        # Log admin activity
        if admin_id:
            try:
                username = user.username if user and hasattr(user, "username") else None
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="READING_HISTORY",
                        entity_id=history.id,
                        description=f"Created reading history for user {history.user_id}",
                        metadata={
                            "user_id": history.user_id,
                            "username": username,
                            "book_id": history.book_id,
                            "chapter_id": history.chapter_id,
                            "last_position": history.last_position,
                            "completion_percentage": history.completion_percentage,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Created new reading history with ID {history.id} for user {history.user_id}"
        )
        return history
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating reading history: {str(e)}")
        raise


async def update_reading_history(
    db: Session,
    history_id: int,
    history_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> ReadingHistory:
    """
    Cập nhật lịch sử đọc.

    Args:
        db: Database session
        history_id: ID của lịch sử đọc
        history_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin lịch sử đọc đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy lịch sử đọc
    """
    try:
        # Kiểm tra lịch sử đọc tồn tại
        history = await get_reading_history_by_id(db, history_id)

        # Cập nhật lịch sử đọc
        repo = ReadingHistoryRepository(db)
        updated_history = await repo.update(history_id, history_data)

        # Log admin activity
        if admin_id:
            try:
                # Get username for logging
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(updated_history.user_id)
                username = user.username if user and hasattr(user, "username") else None

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="READING_HISTORY",
                        entity_id=history_id,
                        description=f"Updated reading history for user {updated_history.user_id}",
                        metadata={
                            "user_id": updated_history.user_id,
                            "username": username,
                            "book_id": updated_history.book_id,
                            "chapter_id": updated_history.chapter_id,
                            "last_position": updated_history.last_position,
                            "completion_percentage": updated_history.completion_percentage,
                            "updated_fields": list(history_data.keys()),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Xóa cache
        remove_cache(f"admin_reading_history:{history_id}")

        logger.info(f"Updated reading history with ID {history_id}")
        return updated_history
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating reading history: {str(e)}")
        raise


async def delete_user_reading_histories(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> int:
    """
    Xóa tất cả lịch sử đọc của người dùng.

    Args:
        db: Session
        user_id: ID của người dùng
        admin_id: ID của admin thực hiện hành động

    Returns:
        Số lượng bản ghi đã xóa
    """
    try:
        # Check if user exists
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = ReadingHistoryRepository(db)
        count = await repo.delete_by_user(user_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="USER_READING_HISTORIES",
                        entity_id=user_id,
                        description=f"Deleted all reading histories for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "count": count,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted {count} reading histories for user {user_id}")
        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user reading histories: {str(e)}")
        raise


@cached(key_prefix="admin_reading_history_statistics", ttl=3600)
async def get_reading_history_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê lịch sử đọc.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê lịch sử đọc
    """
    try:
        repo = ReadingHistoryRepository(db)

        total = await repo.count_histories()

        # Thống kê theo thời gian
        now = datetime.now(timezone.utc)
        today = datetime(now.year, now.month, now.day)
        yesterday = today - timedelta(days=1)

        today_count = await repo.count_histories(
            from_date=today, to_date=today + timedelta(days=1)
        )

        yesterday_count = await repo.count_histories(from_date=yesterday, to_date=today)

        this_week = await repo.count_histories(
            from_date=today - timedelta(days=today.weekday()),
            to_date=today + timedelta(days=1),
        )

        this_month = await repo.count_histories(
            from_date=datetime(now.year, now.month, 1),
            to_date=(
                datetime(now.year, now.month + 1, 1)
                if now.month < 12
                else datetime(now.year + 1, 1, 1)
            ),
        )

        # Số người dùng đã đọc sách
        users_with_history = await repo.count_distinct_users()

        # Số sách đã được đọc
        books_with_history = await repo.count_distinct_books()

        # Số chương đã được đọc
        chapters_with_history = await repo.count_distinct_chapters()

        stats = {
            "total": total,
            "today": today_count,
            "yesterday": yesterday_count,
            "this_week": this_week,
            "this_month": this_month,
            "users_with_history": users_with_history,
            "books_with_history": books_with_history,
            "chapters_with_history": chapters_with_history,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_HISTORY_STATISTICS",
                        entity_id=0,
                        description="Viewed reading history statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving reading history statistics: {str(e)}")
        raise


async def get_most_read_books(
    db: Session, limit: int = 10, admin_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Lấy danh sách sách được đọc nhiều nhất.

    Args:
        db: Database session
        limit: Số lượng sách tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách sách kèm số lượt đọc
    """
    try:
        repo = ReadingHistoryRepository(db)
        most_read_books = await repo.get_most_read_books(limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="MOST_READ_BOOKS",
                        entity_id=0,
                        description="Viewed most read books",
                        metadata={
                            "limit": limit,
                            "results_count": len(most_read_books),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return most_read_books
    except Exception as e:
        logger.error(f"Error retrieving most read books: {str(e)}")
        raise


async def get_most_active_readers(
    db: Session, limit: int = 10, admin_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Lấy danh sách người dùng đọc nhiều nhất.

    Args:
        db: Database session
        limit: Số lượng người dùng tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách người dùng kèm số lượng sách đã đọc
    """
    try:
        repo = ReadingHistoryRepository(db)
        active_readers = await repo.get_most_active_readers(limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="MOST_ACTIVE_READERS",
                        entity_id=0,
                        description="Viewed most active readers",
                        metadata={"limit": limit, "results_count": len(active_readers)},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return active_readers
    except Exception as e:
        logger.error(f"Error retrieving most active readers: {str(e)}")
        raise


async def get_reading_trends(
    db: Session, days: int = 30, admin_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Lấy xu hướng đọc sách theo thời gian.

    Args:
        db: Database session
        days: Số ngày để phân tích
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách số lượt đọc theo ngày
    """
    try:
        repo = ReadingHistoryRepository(db)
        trends = await repo.get_reading_trends(days)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_TRENDS",
                        entity_id=0,
                        description="Viewed reading trends",
                        metadata={"days": days, "results_count": len(trends)},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return trends
    except Exception as e:
        logger.error(f"Error retrieving reading trends: {str(e)}")
        raise
