from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.user_site.models.reading_session import ReadingSession
from app.user_site.repositories.reading_session_repo import ReadingSessionRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundException
from app.common.utils.cache import cached, remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho reading session service
logger = logging.getLogger(__name__)


async def get_all_reading_sessions(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    min_duration: Optional[int] = None,  # Thời gian tối thiểu (giây)
    sort_by: str = "start_time",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[ReadingSession]:
    """
    Lấy danh sách phiên đọc với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        min_duration: Thời gian đọc tối thiểu (giây)
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách phiên đọc
    """
    try:
        repo = ReadingSessionRepository(db)
        sessions = await repo.list_sessions(
            skip=skip,
            limit=limit,
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            from_date=from_date,
            to_date=to_date,
            min_duration=min_duration,
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
                        entity_type="READING_SESSIONS",
                        entity_id=0,
                        description="Viewed reading sessions list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "book_id": book_id,
                            "chapter_id": chapter_id,
                            "from_date": from_date.isoformat() if from_date else None,
                            "to_date": to_date.isoformat() if to_date else None,
                            "min_duration": min_duration,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(sessions),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return sessions
    except Exception as e:
        logger.error(f"Error retrieving reading sessions: {str(e)}")
        raise


async def count_reading_sessions(
    db: Session,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    min_duration: Optional[int] = None,
) -> int:
    """
    Đếm số lượng phiên đọc.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        min_duration: Thời gian đọc tối thiểu (giây)

    Returns:
        Số lượng phiên đọc
    """
    try:
        repo = ReadingSessionRepository(db)
        return await repo.count_sessions(
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            from_date=from_date,
            to_date=to_date,
            min_duration=min_duration,
        )
    except Exception as e:
        logger.error(f"Error counting reading sessions: {str(e)}")
        raise


@cached(key_prefix="admin_reading_session", ttl=300)
async def get_reading_session_by_id(
    db: Session, session_id: int, admin_id: Optional[int] = None
) -> ReadingSession:
    """
    Lấy thông tin phiên đọc theo ID.

    Args:
        db: Database session
        session_id: ID của phiên đọc
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin phiên đọc

    Raises:
        NotFoundException: Nếu không tìm thấy phiên đọc
    """
    try:
        repo = ReadingSessionRepository(db)
        session = await repo.get_by_id(session_id)

        if not session:
            logger.warning(f"Reading session with ID {session_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc với ID {session_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_SESSION",
                        entity_id=session_id,
                        description=f"Viewed reading session details for user {session.user_id}",
                        metadata={
                            "user_id": session.user_id,
                            "book_id": session.book_id,
                            "chapter_id": session.chapter_id,
                            "start_time": (
                                session.start_time.isoformat()
                                if hasattr(session, "start_time")
                                else None
                            ),
                            "end_time": (
                                session.end_time.isoformat()
                                if hasattr(session, "end_time") and session.end_time
                                else None
                            ),
                            "duration": session.duration,
                            "pages_read": session.pages_read,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return session
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving reading session: {str(e)}")
        raise


async def create_reading_session(
    db: Session, session_data: Dict[str, Any], admin_id: Optional[int] = None
) -> ReadingSession:
    """
    Tạo phiên đọc mới.

    Args:
        db: Database session
        session_data: Dữ liệu phiên đọc
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin phiên đọc đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng hoặc sách
    """
    try:
        # Kiểm tra người dùng tồn tại
        if "user_id" in session_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(session_data["user_id"])

            if not user:
                logger.warning(f"User with ID {session_data['user_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {session_data['user_id']}"
                )

        # Tạo phiên đọc mới
        repo = ReadingSessionRepository(db)
        session = await repo.create(session_data)

        # Log admin activity
        if admin_id:
            try:
                # Get username for logging
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(session.user_id)
                username = user.username if user and hasattr(user, "username") else None

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="READING_SESSION",
                        entity_id=session.id,
                        description=f"Created reading session for user {session.user_id}",
                        metadata={
                            "user_id": session.user_id,
                            "username": username,
                            "book_id": session.book_id,
                            "chapter_id": session.chapter_id,
                            "start_time": (
                                session.start_time.isoformat()
                                if hasattr(session, "start_time")
                                else None
                            ),
                            "duration": session.duration,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Created new reading session with ID {session.id} for user {session.user_id}"
        )
        return session
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating reading session: {str(e)}")
        raise


async def update_reading_session(
    db: Session,
    session_id: int,
    session_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> ReadingSession:
    """
    Cập nhật phiên đọc.

    Args:
        db: Database session
        session_id: ID của phiên đọc
        session_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin phiên đọc đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy phiên đọc
    """
    try:
        # Kiểm tra phiên đọc tồn tại
        session = await get_reading_session_by_id(db, session_id)

        # Cập nhật phiên đọc
        repo = ReadingSessionRepository(db)
        updated_session = await repo.update(session_id, session_data)

        # Log admin activity
        if admin_id:
            try:
                # Get username for logging
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(updated_session.user_id)
                username = user.username if user and hasattr(user, "username") else None

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="READING_SESSION",
                        entity_id=session_id,
                        description=f"Updated reading session for user {updated_session.user_id}",
                        metadata={
                            "user_id": updated_session.user_id,
                            "username": username,
                            "book_id": updated_session.book_id,
                            "chapter_id": updated_session.chapter_id,
                            "duration": updated_session.duration,
                            "updated_fields": list(session_data.keys()),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Xóa cache
        remove_cache(f"admin_reading_session:{session_id}")

        logger.info(f"Updated reading session with ID {session_id}")
        return updated_session
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating reading session: {str(e)}")
        raise


async def get_user_reading_sessions(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> List[ReadingSession]:
    """
    Lấy danh sách phiên đọc của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách phiên đọc
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

        repo = ReadingSessionRepository(db)
        sessions = await repo.list_sessions(
            user_id=user_id,
            skip=skip,
            limit=limit,
            from_date=from_date,
            to_date=to_date,
            sort_by="start_time",
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
                        entity_type="USER_READING_SESSIONS",
                        entity_id=user_id,
                        description=f"Viewed reading sessions for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "skip": skip,
                            "limit": limit,
                            "from_date": from_date.isoformat() if from_date else None,
                            "to_date": to_date.isoformat() if to_date else None,
                            "results_count": len(sessions),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return sessions
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user reading sessions: {str(e)}")
        raise


async def get_book_reading_sessions(
    db: Session,
    book_id: int,
    skip: int = 0,
    limit: int = 20,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> List[ReadingSession]:
    """
    Lấy danh sách phiên đọc của một sách.

    Args:
        db: Database session
        book_id: ID của sách
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày

    Returns:
        Danh sách phiên đọc
    """
    try:
        repo = ReadingSessionRepository(db)
        return await repo.list_sessions(
            book_id=book_id,
            skip=skip,
            limit=limit,
            from_date=from_date,
            to_date=to_date,
            sort_by="start_time",
            sort_desc=True,
        )
    except Exception as e:
        logger.error(f"Error retrieving book reading sessions: {str(e)}")
        raise


async def get_chapter_reading_sessions(
    db: Session,
    chapter_id: int,
    skip: int = 0,
    limit: int = 20,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> List[ReadingSession]:
    """
    Lấy danh sách phiên đọc của một chương.

    Args:
        db: Database session
        chapter_id: ID của chương
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày

    Returns:
        Danh sách phiên đọc
    """
    try:
        repo = ReadingSessionRepository(db)
        return await repo.list_sessions(
            chapter_id=chapter_id,
            skip=skip,
            limit=limit,
            from_date=from_date,
            to_date=to_date,
            sort_by="start_time",
            sort_desc=True,
        )
    except Exception as e:
        logger.error(f"Error retrieving chapter reading sessions: {str(e)}")
        raise


async def delete_reading_session(
    db: Session, session_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa phiên đọc.

    Args:
        db: Database session
        session_id: ID của phiên đọc
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy phiên đọc
    """
    try:
        # Kiểm tra phiên đọc tồn tại và lấy thông tin
        session = await get_reading_session_by_id(db, session_id)

        # Xóa phiên đọc
        repo = ReadingSessionRepository(db)
        await repo.delete(session_id)

        # Log admin activity
        if admin_id:
            try:
                # Get username for logging
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(session.user_id)
                username = user.username if user and hasattr(user, "username") else None

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="READING_SESSION",
                        entity_id=session_id,
                        description=f"Deleted reading session for user {session.user_id}",
                        metadata={
                            "user_id": session.user_id,
                            "username": username,
                            "book_id": session.book_id,
                            "chapter_id": session.chapter_id,
                            "start_time": (
                                session.start_time.isoformat()
                                if hasattr(session, "start_time")
                                else None
                            ),
                            "end_time": (
                                session.end_time.isoformat()
                                if hasattr(session, "end_time") and session.end_time
                                else None
                            ),
                            "duration": session.duration,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        remove_cache(f"admin_reading_session:{session_id}")

        logger.info(f"Deleted reading session with ID {session_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting reading session: {str(e)}")
        raise


async def delete_user_reading_sessions(
    db: Session, user_id: int, admin_id: Optional[int] = None
) -> int:
    """
    Xóa tất cả phiên đọc của người dùng.

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

        repo = ReadingSessionRepository(db)
        count = await repo.delete_by_user(user_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="USER_READING_SESSIONS",
                        entity_id=user_id,
                        description=f"Deleted all reading sessions for user {user_id}",
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

        logger.info(f"Deleted {count} reading sessions for user {user_id}")
        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user reading sessions: {str(e)}")
        raise


@cached(key_prefix="admin_reading_session_statistics", ttl=3600)
async def get_reading_session_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê phiên đọc.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê phiên đọc
    """
    try:
        repo = ReadingSessionRepository(db)

        total = await repo.count_sessions()

        # Thống kê theo thời gian
        now = datetime.now(timezone.utc)
        today = datetime(now.year, now.month, now.day)
        yesterday = today - timedelta(days=1)

        today_count = await repo.count_sessions(
            from_date=today, to_date=today + timedelta(days=1)
        )

        yesterday_count = await repo.count_sessions(from_date=yesterday, to_date=today)

        this_week = await repo.count_sessions(
            from_date=today - timedelta(days=today.weekday()),
            to_date=today + timedelta(days=1),
        )

        this_month = await repo.count_sessions(
            from_date=datetime(now.year, now.month, 1),
            to_date=(
                datetime(now.year, now.month + 1, 1)
                if now.month < 12
                else datetime(now.year + 1, 1, 1)
            ),
        )

        # Tổng thời gian đọc
        total_duration = await repo.get_total_reading_time()
        avg_duration = await repo.get_average_session_duration()

        # Số người dùng có phiên đọc
        users_with_sessions = await repo.count_distinct_users()

        # Số sách được đọc
        books_with_sessions = await repo.count_distinct_books()

        # Số chương được đọc
        chapters_with_sessions = await repo.count_distinct_chapters()

        stats = {
            "total": total,
            "today": today_count,
            "yesterday": yesterday_count,
            "this_week": this_week,
            "this_month": this_month,
            "total_duration_hours": (
                round(total_duration / 3600, 2) if total_duration else 0
            ),
            "avg_duration_minutes": round(avg_duration / 60, 2) if avg_duration else 0,
            "users_with_sessions": users_with_sessions,
            "books_with_sessions": books_with_sessions,
            "chapters_with_sessions": chapters_with_sessions,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_SESSION_STATISTICS",
                        entity_id=0,
                        description="Viewed reading session statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving reading session statistics: {str(e)}")
        raise


async def get_user_reading_time(
    db: Session,
    user_id: int,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> int:
    """
    Lấy tổng thời gian đọc của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        admin_id: ID của admin thực hiện hành động

    Returns:
        Tổng thời gian đọc (giây)
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

        repo = ReadingSessionRepository(db)
        reading_time = await repo.get_user_reading_time(
            user_id=user_id, from_date=from_date, to_date=to_date
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_READING_TIME",
                        entity_id=user_id,
                        description=f"Viewed reading time for user {user_id}",
                        metadata={
                            "user_id": user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "from_date": from_date.isoformat() if from_date else None,
                            "to_date": to_date.isoformat() if to_date else None,
                            "reading_time_seconds": reading_time,
                            "reading_time_hours": (
                                round(reading_time / 3600, 2) if reading_time else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return reading_time
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user reading time: {str(e)}")
        raise


async def get_book_reading_time(
    db: Session,
    book_id: int,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> int:
    """
    Lấy tổng thời gian đọc của một sách.

    Args:
        db: Database session
        book_id: ID của sách
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày

    Returns:
        Tổng thời gian đọc (giây)
    """
    try:
        repo = ReadingSessionRepository(db)
        return await repo.get_book_reading_time(
            book_id=book_id, from_date=from_date, to_date=to_date
        )
    except Exception as e:
        logger.error(f"Error retrieving book reading time: {str(e)}")
        raise


async def get_most_engaged_readers(
    db: Session, limit: int = 10, admin_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Lấy danh sách người dùng đọc nhiều thời gian nhất.

    Args:
        db: Database session
        limit: Số lượng người dùng tối đa trả về
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách người dùng kèm thời gian đọc
    """
    try:
        repo = ReadingSessionRepository(db)
        readers = await repo.get_most_engaged_readers(limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="MOST_ENGAGED_READERS",
                        entity_id=0,
                        description="Viewed most engaged readers",
                        metadata={"limit": limit, "results_count": len(readers)},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return readers
    except Exception as e:
        logger.error(f"Error retrieving most engaged readers: {str(e)}")
        raise


async def get_most_time_spent_books(
    db: Session, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Lấy danh sách sách được đọc nhiều thời gian nhất.

    Args:
        db: Database session
        limit: Số lượng sách tối đa trả về

    Returns:
        Danh sách sách kèm thời gian đọc
    """
    try:
        repo = ReadingSessionRepository(db)
        return await repo.get_most_time_spent_books(limit)
    except Exception as e:
        logger.error(f"Error retrieving most time spent books: {str(e)}")
        raise


async def get_reading_time_trends(
    db: Session, days: int = 30, admin_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Lấy xu hướng thời gian đọc sách theo ngày.

    Args:
        db: Database session
        days: Số ngày để phân tích
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách thời gian đọc theo ngày
    """
    try:
        repo = ReadingSessionRepository(db)
        trends = await repo.get_reading_time_trends(days)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_TIME_TRENDS",
                        entity_id=0,
                        description="Viewed reading time trends",
                        metadata={"days": days, "results_count": len(trends)},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return trends
    except Exception as e:
        logger.error(f"Error retrieving reading time trends: {str(e)}")
        raise
