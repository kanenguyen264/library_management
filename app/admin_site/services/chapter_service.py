from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging
from datetime import datetime

from app.user_site.models.chapter import Chapter, ChapterMedia
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.schemas.chapter import ChapterStatus
from app.cache.decorators import cached, invalidate_cache
from app.core.exceptions import NotFoundException, ForbiddenException

logger = logging.getLogger(__name__)


async def get_all_chapters(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    book_id: Optional[int] = None,
    is_published: Optional[bool] = None,
    search_query: Optional[str] = None,
) -> List[Chapter]:
    """
    Lấy danh sách chương với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        book_id: Lọc theo ID sách
        is_published: Lọc theo trạng thái xuất bản
        search_query: Chuỗi tìm kiếm

    Returns:
        Danh sách chương
    """
    try:
        repo = ChapterRepository(db)

        if book_id:
            return await repo.list_book_chapters(
                book_id, skip, limit, is_published, search_query
            )
        else:
            return await repo.list_chapters(skip, limit, is_published, search_query)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách chương: {str(e)}")
        raise


async def count_chapters(
    db: Session,
    book_id: Optional[int] = None,
    is_published: Optional[bool] = None,
    search_query: Optional[str] = None,
) -> int:
    """
    Đếm số lượng chương.

    Args:
        db: Database session
        book_id: Lọc theo ID sách
        is_published: Lọc theo trạng thái xuất bản
        search_query: Chuỗi tìm kiếm

    Returns:
        Số lượng chương
    """
    try:
        repo = ChapterRepository(db)

        if book_id:
            return await repo.count_book_chapters(book_id, is_published, search_query)
        else:
            return await repo.count_chapters(is_published, search_query)
    except Exception as e:
        logger.error(f"Lỗi khi đếm chương: {str(e)}")
        raise


@cached(key_prefix="admin_chapter", ttl=300)
async def get_chapter_by_id(db: Session, chapter_id: int) -> Chapter:
    """
    Lấy thông tin chương theo ID.

    Args:
        db: Database session
        chapter_id: ID của chương

    Returns:
        Thông tin chương

    Raises:
        NotFoundException: Nếu không tìm thấy chương
    """
    try:
        repo = ChapterRepository(db)
        chapter = await repo.get_chapter_by_id(chapter_id)

        if not chapter:
            logger.warning(f"Không tìm thấy chương với ID {chapter_id}")
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        return chapter
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin chương: {str(e)}")
        raise


async def get_chapter_by_number(
    db: Session, book_id: int, chapter_number: int
) -> Chapter:
    """
    Lấy thông tin chương theo số thứ tự trong sách.

    Args:
        db: Database session
        book_id: ID của sách
        chapter_number: Số thứ tự chương

    Returns:
        Thông tin chương

    Raises:
        NotFoundException: Nếu không tìm thấy chương
    """
    try:
        repo = ChapterRepository(db)
        chapter = await repo.get_chapter_by_number(book_id, chapter_number)

        if not chapter:
            logger.warning(
                f"Không tìm thấy chương số {chapter_number} của sách {book_id}"
            )
            raise NotFoundException(
                detail=f"Không tìm thấy chương số {chapter_number} của sách {book_id}"
            )

        return chapter
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin chương theo số thứ tự: {str(e)}")
        raise


async def create_chapter(db: Session, chapter_data: Dict[str, Any]) -> Chapter:
    """
    Tạo chương mới.

    Args:
        db: Database session
        chapter_data: Dữ liệu chương

    Returns:
        Thông tin chương đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy sách
        ForbiddenException: Nếu số thứ tự chương đã tồn tại trong sách
    """
    try:
        # Kiểm tra sách tồn tại
        if "book_id" in chapter_data:
            book_repo = BookRepository(db)
            book = await book_repo.get_by_id(chapter_data["book_id"])

            if not book:
                logger.warning(f"Không tìm thấy sách với ID {chapter_data['book_id']}")
                raise NotFoundException(
                    detail=f"Không tìm thấy sách với ID {chapter_data['book_id']}"
                )

        # Kiểm tra số thứ tự chương trong sách đã tồn tại
        if "book_id" in chapter_data and "number" in chapter_data:
            repo = ChapterRepository(db)
            existing_chapter = await repo.get_chapter_by_number(
                chapter_data["book_id"], chapter_data["number"]
            )

            if existing_chapter:
                logger.warning(
                    f"Chương số {chapter_data['number']} đã tồn tại trong sách {chapter_data['book_id']}"
                )
                raise ForbiddenException(
                    detail=f"Chương số {chapter_data['number']} đã tồn tại trong sách"
                )

        # Tạo chương mới
        repo = ChapterRepository(db)
        chapter = await repo.create_chapter(chapter_data)

        # Cập nhật số lượng chương trong sách
        if "book_id" in chapter_data:
            book_repo = BookRepository(db)
            await book_repo.update_chapter_count(chapter_data["book_id"])

        logger.info(f"Đã tạo chương mới với ID {chapter.id}")
        return chapter
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo chương: {str(e)}")
        raise


async def update_chapter(
    db: Session, chapter_id: int, chapter_data: Dict[str, Any]
) -> Chapter:
    """
    Cập nhật thông tin chương.

    Args:
        db: Database session
        chapter_id: ID của chương
        chapter_data: Dữ liệu cập nhật

    Returns:
        Thông tin chương đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy chương
        ForbiddenException: Nếu số thứ tự chương đã tồn tại trong sách
    """
    try:
        # Kiểm tra chương tồn tại
        chapter = await get_chapter_by_id(db, chapter_id)

        # Kiểm tra xung đột số thứ tự nếu đổi số thứ tự
        if (
            "number" in chapter_data
            and "book_id" in chapter_data
            and chapter_data["number"] != chapter.number
        ):
            repo = ChapterRepository(db)
            existing_chapter = await repo.get_chapter_by_number(
                chapter_data["book_id"], chapter_data["number"]
            )

            if existing_chapter and existing_chapter.id != chapter_id:
                logger.warning(
                    f"Chương số {chapter_data['number']} đã tồn tại trong sách {chapter_data['book_id']}"
                )
                raise ForbiddenException(
                    detail=f"Chương số {chapter_data['number']} đã tồn tại trong sách"
                )

        # Cập nhật chương
        repo = ChapterRepository(db)
        updated_chapter = await repo.update_chapter(chapter_id, chapter_data)

        logger.info(f"Đã cập nhật chương với ID {chapter_id}")
        return updated_chapter
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật chương: {str(e)}")
        raise


async def delete_chapter(db: Session, chapter_id: int) -> None:
    """
    Xóa chương.

    Args:
        db: Database session
        chapter_id: ID của chương

    Raises:
        NotFoundException: Nếu không tìm thấy chương
    """
    try:
        # Kiểm tra chương tồn tại và lấy thông tin
        chapter = await get_chapter_by_id(db, chapter_id)
        book_id = chapter.book_id

        # Xóa chương
        repo = ChapterRepository(db)
        await repo.delete_chapter(chapter_id)

        # Cập nhật số lượng chương trong sách
        book_repo = BookRepository(db)
        await book_repo.update_chapter_count(book_id)

        # Cập nhật số thứ tự các chương sau nếu cần
        await repo.reorder_chapters_after_delete(book_id, chapter.number)

        logger.info(f"Đã xóa chương với ID {chapter_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa chương: {str(e)}")
        raise


@cached(key_prefix="admin_book_chapters", ttl=300)
async def get_book_chapters(
    db: Session,
    book_id: int,
    skip: int = 0,
    limit: int = 20,
    is_published: Optional[bool] = None,
) -> List[Chapter]:
    """
    Lấy danh sách chương của sách.

    Args:
        db: Database session
        book_id: ID của sách
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        is_published: Lọc theo trạng thái xuất bản

    Returns:
        Danh sách chương

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy danh sách chương
        repo = ChapterRepository(db)
        chapters = await repo.list_book_chapters(book_id, skip, limit, is_published)

        return chapters
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách chương của sách: {str(e)}")
        raise


async def get_next_chapter(db: Session, chapter_id: int) -> Optional[Chapter]:
    """
    Lấy chương tiếp theo trong sách.

    Args:
        db: Database session
        chapter_id: ID của chương hiện tại

    Returns:
        Chương tiếp theo hoặc None nếu là chương cuối

    Raises:
        NotFoundException: Nếu không tìm thấy chương hiện tại
    """
    try:
        # Kiểm tra chương tồn tại
        chapter = await get_chapter_by_id(db, chapter_id)

        # Lấy chương tiếp theo
        repo = ChapterRepository(db)
        next_chapter = await repo.get_next_chapter(chapter.book_id, chapter.number)

        return next_chapter
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy chương tiếp theo: {str(e)}")
        raise


async def get_previous_chapter(db: Session, chapter_id: int) -> Optional[Chapter]:
    """
    Lấy chương trước trong sách.

    Args:
        db: Database session
        chapter_id: ID của chương hiện tại

    Returns:
        Chương trước hoặc None nếu là chương đầu tiên

    Raises:
        NotFoundException: Nếu không tìm thấy chương hiện tại
    """
    try:
        # Kiểm tra chương tồn tại
        chapter = await get_chapter_by_id(db, chapter_id)

        # Lấy chương trước
        repo = ChapterRepository(db)
        previous_chapter = await repo.get_previous_chapter(
            chapter.book_id, chapter.number
        )

        return previous_chapter
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy chương trước: {str(e)}")
        raise


async def publish_chapter(db: Session, chapter_id: int) -> Chapter:
    """
    Xuất bản chương.

    Args:
        db: Database session
        chapter_id: ID của chương

    Returns:
        Thông tin chương đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy chương
    """
    try:
        # Kiểm tra chương tồn tại
        await get_chapter_by_id(db, chapter_id)

        # Cập nhật trạng thái xuất bản
        repo = ChapterRepository(db)
        updated_chapter = await repo.update_chapter(chapter_id, {"is_published": True})

        logger.info(f"Đã xuất bản chương với ID {chapter_id}")
        return updated_chapter
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xuất bản chương: {str(e)}")
        raise


async def unpublish_chapter(db: Session, chapter_id: int) -> Chapter:
    """
    Hủy xuất bản chương.

    Args:
        db: Database session
        chapter_id: ID của chương

    Returns:
        Thông tin chương đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy chương
    """
    try:
        # Kiểm tra chương tồn tại
        await get_chapter_by_id(db, chapter_id)

        # Cập nhật trạng thái xuất bản
        repo = ChapterRepository(db)
        updated_chapter = await repo.update_chapter(chapter_id, {"is_published": False})

        logger.info(f"Đã hủy xuất bản chương với ID {chapter_id}")
        return updated_chapter
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi hủy xuất bản chương: {str(e)}")
        raise


async def update_chapter_views(
    db: Session, chapter_id: int, increment: int = 1
) -> Chapter:
    """
    Cập nhật số lượt xem của chương.

    Args:
        db: Database session
        chapter_id: ID của chương
        increment: Số lượng tăng thêm

    Returns:
        Thông tin chương đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy chương
    """
    try:
        # Kiểm tra chương tồn tại
        chapter = await get_chapter_by_id(db, chapter_id)

        # Cập nhật số lượt xem
        new_views = chapter.views + increment

        repo = ChapterRepository(db)
        updated_chapter = await repo.update_chapter(chapter_id, {"views": new_views})

        logger.info(
            f"Đã cập nhật số lượt xem của chương {chapter_id} thành {new_views}"
        )
        return updated_chapter
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật số lượt xem: {str(e)}")
        raise


async def reorder_chapter(db: Session, chapter_id: int, new_number: int) -> Chapter:
    """
    Thay đổi thứ tự của chương trong sách.

    Args:
        db: Database session
        chapter_id: ID của chương
        new_number: Số thứ tự mới

    Returns:
        Thông tin chương đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy chương
        ForbiddenException: Nếu số thứ tự mới không hợp lệ
    """
    try:
        # Kiểm tra chương tồn tại
        chapter = await get_chapter_by_id(db, chapter_id)

        if new_number < 1:
            logger.warning(f"Số thứ tự chương phải lớn hơn 0")
            raise ForbiddenException(detail=f"Số thứ tự chương phải lớn hơn 0")

        # Kiểm tra số thứ tự mới có khác với số thứ tự hiện tại
        if chapter.number == new_number:
            return chapter

        # Thực hiện sắp xếp lại
        repo = ChapterRepository(db)
        updated_chapter = await repo.reorder_chapter(chapter_id, new_number)

        logger.info(
            f"Đã thay đổi thứ tự của chương {chapter_id} từ {chapter.number} thành {new_number}"
        )
        return updated_chapter
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thay đổi thứ tự chương: {str(e)}")
        raise


@cached(key_prefix="admin_chapter_statistics", ttl=3600)
async def get_chapter_statistics(db: Session) -> Dict[str, Any]:
    """
    Lấy thống kê về chương.

    Args:
        db: Database session

    Returns:
        Thống kê chương
    """
    try:
        repo = ChapterRepository(db)

        # Đếm tổng số chương
        total_count = await repo.count_chapters()

        # Đếm số chương đã xuất bản
        published_count = await repo.count_chapters(is_published=True)

        # Đây là code demo, cần bổ sung các phương thức hỗ trợ trong repository
        stats = {
            "total_chapters": total_count,
            "published_chapters": published_count,
            "average_chapter_length": None,  # Cần bổ sung phương thức calculate_average_chapter_length
            "most_viewed_chapters": [],  # Cần bổ sung phương thức get_most_viewed_chapters
            "longest_chapters": [],  # Cần bổ sung phương thức get_longest_chapters
        }

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê chương: {str(e)}")
        raise


async def get_chapter_media(db: Session, chapter_id: int) -> List[ChapterMedia]:
    """
    Get media associated with a chapter.

    Args:
        db: Database session
        chapter_id: ID of the chapter

    Returns:
        List of ChapterMedia objects

    Raises:
        HTTPException: If chapter not found or error occurs
    """
    try:
        # Check if chapter exists
        chapter = ChapterRepository.get_by_id(db, chapter_id)
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chapter with ID {chapter_id} not found",
            )

        return ChapterRepository.get_chapter_media(db, chapter_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving chapter media: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving chapter media",
        )


async def add_media_to_chapter(db: Session, media_data: Dict[str, Any]) -> ChapterMedia:
    """
    Add media to a chapter.

    Args:
        db: Database session
        media_data: Dictionary with media data

    Returns:
        Created ChapterMedia object

    Raises:
        HTTPException: If chapter not found or error occurs
    """
    try:
        chapter_id = media_data.get("chapter_id")

        # Check if chapter exists
        chapter = ChapterRepository.get_by_id(db, chapter_id)
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chapter with ID {chapter_id} not found",
            )

        return ChapterRepository.add_media(db, media_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding media to chapter: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error adding media to chapter",
        )


async def delete_chapter_media(db: Session, media_id: int) -> bool:
    """
    Delete chapter media.

    Args:
        db: Database session
        media_id: ID of the media to delete

    Returns:
        True if successful

    Raises:
        HTTPException: If media not found or error occurs
    """
    try:
        success = ChapterRepository.delete_media(db, media_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Media with ID {media_id} not found",
            )

        return True
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chapter media: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting chapter media",
        )


async def check_and_publish_scheduled_chapters(db: Session) -> List[Chapter]:
    """
    Check for chapters scheduled to be published and publish them.

    Args:
        db: Database session

    Returns:
        List of published chapters
    """
    try:
        scheduled_chapters = ChapterRepository.check_scheduled_chapters(db)
        published_chapters = []

        for chapter in scheduled_chapters:
            published_chapter = ChapterRepository.publish_chapter(db, chapter.id)
            published_chapters.append(published_chapter)

        return published_chapters
    except Exception as e:
        logger.error(f"Error checking scheduled chapters: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error checking scheduled chapters",
        )
