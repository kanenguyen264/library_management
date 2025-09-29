from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.models.bookmark import Bookmark
from app.user_site.repositories.bookmark_repo import BookmarkRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho bookmark service
logger = logging.getLogger(__name__)


async def get_all_bookmarks(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Bookmark]:
    """
    Lấy danh sách bookmark với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách bookmark
    """
    try:
        repo = BookmarkRepository(db)
        bookmarks = await repo.list_bookmarks(
            skip=skip,
            limit=limit,
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
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
                        entity_type="BOOKMARKS",
                        entity_id=0,
                        description="Viewed bookmark list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "book_id": book_id,
                            "chapter_id": chapter_id,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(bookmarks),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return bookmarks
    except Exception as e:
        logger.error(f"Error retrieving bookmarks: {str(e)}")
        raise


async def count_bookmarks(
    db: Session, user_id: Optional[int] = None, book_id: Optional[int] = None
) -> int:
    """
    Đếm số lượng bookmark.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách

    Returns:
        Số lượng bookmark
    """
    try:
        repo = BookmarkRepository(db)

        if user_id:
            return await repo.count_by_user(user_id, book_id)
        else:
            logger.warning("Yêu cầu đếm tất cả bookmark không được hỗ trợ")
            return 0
    except Exception as e:
        logger.error(f"Lỗi khi đếm bookmark: {str(e)}")
        raise


@cached(key_prefix="admin_bookmark", ttl=300)
async def get_bookmark_by_id(
    db: Session, bookmark_id: int, admin_id: Optional[int] = None
) -> Bookmark:
    """
    Lấy thông tin bookmark theo ID.

    Args:
        db: Database session
        bookmark_id: ID của bookmark
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin bookmark

    Raises:
        NotFoundException: Nếu không tìm thấy bookmark
    """
    try:
        repo = BookmarkRepository(db)
        bookmark = await repo.get_by_id(bookmark_id)

        if not bookmark:
            logger.warning(f"Bookmark with ID {bookmark_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID {bookmark_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOKMARK",
                        entity_id=bookmark_id,
                        description=f"Viewed bookmark details for user {bookmark.user_id}",
                        metadata={
                            "user_id": bookmark.user_id,
                            "book_id": bookmark.book_id,
                            "chapter_id": bookmark.chapter_id,
                            "position": bookmark.position,
                            "note": bookmark.note,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving bookmark: {str(e)}")
        raise


async def create_bookmark(
    db: Session, bookmark_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Bookmark:
    """
    Tạo bookmark mới.

    Args:
        db: Database session
        bookmark_data: Dữ liệu bookmark
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin bookmark đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng, sách hoặc chương
    """
    try:
        # Kiểm tra người dùng tồn tại
        if "user_id" in bookmark_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(bookmark_data["user_id"])

            if not user:
                logger.warning(f"User with ID {bookmark_data['user_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {bookmark_data['user_id']}"
                )

        # Kiểm tra sách tồn tại
        if "book_id" in bookmark_data:
            book_repo = BookRepository(db)
            book = await book_repo.get_by_id(bookmark_data["book_id"])

            if not book:
                logger.warning(f"Book with ID {bookmark_data['book_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy sách với ID {bookmark_data['book_id']}"
                )

        # Kiểm tra chương tồn tại
        if "chapter_id" in bookmark_data and bookmark_data["chapter_id"] is not None:
            chapter_repo = ChapterRepository(db)
            chapter = await chapter_repo.get_by_id(bookmark_data["chapter_id"])

            if not chapter:
                logger.warning(
                    f"Chapter with ID {bookmark_data['chapter_id']} not found"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy chương với ID {bookmark_data['chapter_id']}"
                )

        # Tạo bookmark mới
        repo = BookmarkRepository(db)
        bookmark = await repo.create(bookmark_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="BOOKMARK",
                        entity_id=bookmark.id,
                        description=f"Created new bookmark for user {bookmark.user_id}",
                        metadata={
                            "user_id": bookmark.user_id,
                            "book_id": bookmark.book_id,
                            "chapter_id": bookmark.chapter_id,
                            "position": bookmark.position,
                            "note": bookmark.note,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new bookmark with ID {bookmark.id}")
        return bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating bookmark: {str(e)}")
        raise


async def update_bookmark(
    db: Session,
    bookmark_id: int,
    bookmark_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Bookmark:
    """
    Cập nhật thông tin bookmark.

    Args:
        db: Database session
        bookmark_id: ID của bookmark
        bookmark_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin bookmark đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy bookmark
    """
    try:
        # Get old bookmark data for logging
        old_bookmark = await get_bookmark_by_id(db, bookmark_id)

        # Cập nhật bookmark
        repo = BookmarkRepository(db)
        bookmark = await repo.update(bookmark_id, bookmark_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="BOOKMARK",
                        entity_id=bookmark_id,
                        description=f"Updated bookmark for user {bookmark.user_id}",
                        metadata={
                            "updated_fields": list(bookmark_data.keys()),
                            "old_values": {
                                k: getattr(old_bookmark, k)
                                for k in bookmark_data.keys()
                            },
                            "new_values": {
                                k: getattr(bookmark, k) for k in bookmark_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated bookmark with ID {bookmark_id}")
        return bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating bookmark: {str(e)}")
        raise


async def delete_bookmark(
    db: Session, bookmark_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa bookmark.

    Args:
        db: Database session
        bookmark_id: ID của bookmark
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy bookmark
    """
    try:
        # Get bookmark details before deletion for logging
        bookmark = await get_bookmark_by_id(db, bookmark_id)

        # Xóa bookmark
        repo = BookmarkRepository(db)
        result = await repo.delete(bookmark_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="BOOKMARK",
                        entity_id=bookmark_id,
                        description=f"Deleted bookmark for user {bookmark.user_id}",
                        metadata={
                            "user_id": bookmark.user_id,
                            "book_id": bookmark.book_id,
                            "chapter_id": bookmark.chapter_id,
                            "position": bookmark.position,
                            "note": bookmark.note,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted bookmark with ID {bookmark_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting bookmark: {str(e)}")
        raise


async def get_user_bookmark_for_chapter(
    db: Session, user_id: int, chapter_id: int
) -> Optional[Bookmark]:
    """
    Lấy bookmark của người dùng cho một chương cụ thể.

    Args:
        db: Database session
        user_id: ID của người dùng
        chapter_id: ID của chương

    Returns:
        Thông tin bookmark hoặc None nếu không có
    """
    try:
        repo = BookmarkRepository(db)
        return await repo.get_by_user_and_chapter(user_id, chapter_id)
    except Exception as e:
        logger.error(f"Lỗi khi lấy bookmark cho chương: {str(e)}")
        raise


async def get_latest_user_bookmark_for_book(
    db: Session, user_id: int, book_id: int
) -> Optional[Bookmark]:
    """
    Lấy bookmark mới nhất của người dùng cho một cuốn sách.

    Args:
        db: Database session
        user_id: ID của người dùng
        book_id: ID của sách

    Returns:
        Thông tin bookmark hoặc None nếu không có
    """
    try:
        repo = BookmarkRepository(db)
        return await repo.get_latest_by_user_and_book(user_id, book_id)
    except Exception as e:
        logger.error(f"Lỗi khi lấy bookmark mới nhất cho sách: {str(e)}")
        raise


async def add_or_update_bookmark(
    db: Session,
    user_id: int,
    book_id: int,
    chapter_id: int,
    position: Optional[int] = None,
    note: Optional[str] = None,
) -> Bookmark:
    """
    Thêm hoặc cập nhật bookmark.

    Args:
        db: Database session
        user_id: ID của người dùng
        book_id: ID của sách
        chapter_id: ID của chương
        position: Vị trí trong chương
        note: Ghi chú

    Returns:
        Thông tin bookmark đã tạo hoặc cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng, sách hoặc chương
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

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra chương tồn tại
        chapter_repo = ChapterRepository(db)
        chapter = await chapter_repo.get_by_id(chapter_id)

        if not chapter:
            logger.warning(f"Không tìm thấy chương với ID {chapter_id}")
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        # Thêm hoặc cập nhật bookmark
        repo = BookmarkRepository(db)
        bookmark = await repo.add_or_update(
            user_id, book_id, chapter_id, position, note
        )

        logger.info(f"Đã thêm hoặc cập nhật bookmark với ID {bookmark.id}")
        return bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm hoặc cập nhật bookmark: {str(e)}")
        raise


async def delete_user_bookmarks_for_book(
    db: Session, user_id: int, book_id: int
) -> bool:
    """
    Xóa tất cả bookmark của người dùng cho một cuốn sách.

    Args:
        db: Database session
        user_id: ID của người dùng
        book_id: ID của sách

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng hoặc sách
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

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Xóa bookmark
        repo = BookmarkRepository(db)
        result = await repo.delete_by_user_and_book(user_id, book_id)

        logger.info(f"Đã xóa bookmark của người dùng {user_id} cho sách {book_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa bookmark cho sách: {str(e)}")
        raise


@cached(key_prefix="admin_user_recent_bookmarks", ttl=300)
async def get_user_recent_bookmarks(
    db: Session, user_id: int, limit: int = 5
) -> List[Bookmark]:
    """
    Lấy danh sách bookmark gần đây của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách bookmark gần đây

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

        # Lấy danh sách bookmark gần đây
        repo = BookmarkRepository(db)
        bookmarks = await repo.list_recent_by_user(user_id, limit)

        return bookmarks
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách bookmark gần đây: {str(e)}")
        raise


@cached(key_prefix="admin_bookmark_statistics", ttl=3600)
async def get_bookmark_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về bookmark.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê bookmark
    """
    try:
        repo = BookmarkRepository(db)

        # Đếm tổng số bookmark
        total = await repo.count_bookmarks()

        # Thống kê theo người dùng
        by_user = await repo.count_bookmarks_by_user()

        # Thống kê theo sách
        by_book = await repo.count_bookmarks_by_book()

        # Thống kê theo chương
        by_chapter = await repo.count_bookmarks_by_chapter()

        stats = {
            "total": total,
            "by_user": by_user,
            "by_book": by_book,
            "by_chapter": by_chapter,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOKMARK_STATISTICS",
                        entity_id=0,
                        description="Viewed bookmark statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving bookmark statistics: {str(e)}")
        raise
