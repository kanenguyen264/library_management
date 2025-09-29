from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.bookmark_repo import BookmarkRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache


class BookmarkService:
    """Service để quản lý đánh dấu trang (bookmark) của người dùng."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo service với AsyncSession."""
        self.db = db
        self.bookmark_repo = BookmarkRepository(db)
        self.book_repo = BookRepository(db)
        self.chapter_repo = ChapterRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    @invalidate_cache(namespace="bookmarks", tags=["user_bookmarks"])
    async def create_bookmark(
        self,
        user_id: int,
        book_id: int,
        chapter_id: int,
        position: Optional[str] = None,
        note: Optional[str] = None,
        title: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Tạo đánh dấu trang mới.

        Args:
            user_id: ID người dùng
            book_id: ID sách
            chapter_id: ID chương
            position: Vị trí đánh dấu (offset trong nội dung)
            note: Ghi chú
            title: Tiêu đề bookmark
            color: Màu sắc bookmark

        Returns:
            Thông tin bookmark đã tạo

        Raises:
            NotFoundException: Nếu không tìm thấy sách hoặc chương
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra chương tồn tại và thuộc về sách
        chapter = await self.chapter_repo.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        if chapter.book_id != book_id:
            raise BadRequestException(detail="Chương không thuộc về sách này")

        # Kiểm tra nếu đã có bookmark cho chapter này, thì cập nhật
        existing_bookmark = await self.bookmark_repo.get_by_user_and_chapter(
            user_id, chapter_id
        )
        if existing_bookmark:
            update_data = {}
            if position is not None:
                update_data["position_offset"] = position
            if note is not None:
                update_data["note"] = note
            if title is not None:
                update_data["title"] = title
            if color is not None:
                update_data["color"] = color

            if update_data:
                updated_bookmark = await self.bookmark_repo.update(
                    existing_bookmark.id, update_data
                )
                # Track metric
                self.metrics.track_user_activity("bookmark_updated")
                return self._format_bookmark_response(updated_bookmark)
            return self._format_bookmark_response(existing_bookmark)

        # Tạo bookmark mới
        bookmark_data = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "position_offset": position or "0",
            "note": note,
            "title": title,
            "color": color,
        }

        # Track metric
        self.metrics.track_user_activity("bookmark_created")

        # Tạo bookmark
        created_bookmark = await self.bookmark_repo.create(bookmark_data)
        return self._format_bookmark_response(created_bookmark)

    @cached(ttl=3600, namespace="bookmarks", tags=["bookmark_details"])
    async def get_bookmark(
        self, bookmark_id: int, current_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin chi tiết của một bookmark.

        Args:
            bookmark_id: ID bookmark
            current_user_id: ID người dùng hiện tại (để kiểm tra quyền)

        Returns:
            Thông tin chi tiết bookmark

        Raises:
            NotFoundException: Nếu không tìm thấy bookmark
            ForbiddenException: Nếu không có quyền xem bookmark này
        """
        bookmark = await self.bookmark_repo.get_by_id(
            bookmark_id, with_relations=["book", "chapter"]
        )

        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID {bookmark_id}"
            )

        # Kiểm tra quyền: chỉ chủ sở hữu mới có quyền xem bookmark
        if current_user_id and bookmark.user_id != current_user_id:
            raise ForbiddenException(detail="Bạn không có quyền xem bookmark này")

        # Track metric
        self.metrics.track_user_activity("bookmark_viewed")

        return self._format_bookmark_response(bookmark)

    @cached(
        ttl=1800,
        namespace="bookmarks",
        tags=["user_bookmarks"],
        key_builder=lambda *args, **kwargs: f"user_chapter_bookmark:{kwargs.get('user_id')}:{kwargs.get('chapter_id')}",
    )
    async def get_user_chapter_bookmark(
        self, user_id: int, chapter_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy bookmark của người dùng tại một chương cụ thể.

        Args:
            user_id: ID người dùng
            chapter_id: ID chương

        Returns:
            Thông tin bookmark hoặc None nếu không có
        """
        bookmark = await self.bookmark_repo.get_by_user_and_chapter(user_id, chapter_id)
        if not bookmark:
            return None

        return self._format_bookmark_response(bookmark)

    @cached(
        ttl=1800,
        namespace="bookmarks",
        tags=["user_bookmarks"],
        key_builder=lambda *args, **kwargs: f"user_bookmarks:{kwargs.get('user_id')}:{kwargs.get('book_id')}:{kwargs.get('skip')}:{kwargs.get('limit')}",
    )
    async def list_user_bookmarks(
        self,
        user_id: int,
        book_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Liệt kê bookmark của người dùng, có thể lọc theo sách.

        Args:
            user_id: ID người dùng
            book_id: ID sách (tùy chọn)
            skip: Số mục bỏ qua (phân trang)
            limit: Số mục tối đa trả về

        Returns:
            Danh sách bookmark và tổng số
        """
        bookmarks = await self.bookmark_repo.list_by_user(
            user_id, book_id, skip, limit, with_relations=["book", "chapter"]
        )
        total = await self.bookmark_repo.count_by_user(user_id, book_id)

        # Track metric
        self.metrics.track_user_activity("bookmarks_listed")

        return {
            "items": [
                self._format_bookmark_response(bookmark) for bookmark in bookmarks
            ],
            "total": total,
        }

    @invalidate_cache(
        namespace="bookmarks", tags=["user_bookmarks", "bookmark_details"]
    )
    async def update_bookmark(
        self, bookmark_id: int, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin bookmark.

        Args:
            bookmark_id: ID bookmark
            user_id: ID người dùng (để kiểm tra quyền)
            data: Dữ liệu cập nhật (position_offset, note, title, color)

        Returns:
            Thông tin bookmark đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy bookmark
            ForbiddenException: Nếu không có quyền cập nhật
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra bookmark tồn tại
        bookmark = await self.bookmark_repo.get_by_id(bookmark_id)
        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID {bookmark_id}"
            )

        # Kiểm tra quyền: chỉ chủ sở hữu mới có quyền cập nhật
        if bookmark.user_id != user_id:
            raise ForbiddenException(detail="Bạn không có quyền cập nhật bookmark này")

        # Lọc dữ liệu hợp lệ
        allowed_fields = {"position_offset", "note", "title", "color"}
        update_data = {k: v for k, v in data.items() if k in allowed_fields}

        # Cập nhật bookmark
        updated_bookmark = await self.bookmark_repo.update(bookmark_id, update_data)

        # Track metric
        self.metrics.track_user_activity("bookmark_updated")

        return self._format_bookmark_response(updated_bookmark)

    @invalidate_cache(
        namespace="bookmarks", tags=["user_bookmarks", "bookmark_details"]
    )
    async def delete_bookmark(self, bookmark_id: int, user_id: int) -> Dict[str, Any]:
        """
        Xóa bookmark.

        Args:
            bookmark_id: ID bookmark
            user_id: ID người dùng (để kiểm tra quyền)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy bookmark
            ForbiddenException: Nếu không có quyền xóa
        """
        # Kiểm tra bookmark tồn tại
        bookmark = await self.bookmark_repo.get_by_id(bookmark_id)
        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID {bookmark_id}"
            )

        # Kiểm tra quyền: chỉ chủ sở hữu mới có quyền xóa
        if bookmark.user_id != user_id:
            raise ForbiddenException(detail="Bạn không có quyền xóa bookmark này")

        # Xóa bookmark
        success = await self.bookmark_repo.delete(bookmark_id)

        # Track metric
        self.metrics.track_user_activity("bookmark_deleted")

        return {"success": success, "message": "Bookmark đã được xóa thành công"}

    @invalidate_cache(namespace="bookmarks", tags=["user_bookmarks"])
    async def delete_book_bookmarks(self, user_id: int, book_id: int) -> Dict[str, Any]:
        """
        Xóa tất cả bookmark của một người dùng cho một cuốn sách.

        Args:
            user_id: ID người dùng
            book_id: ID sách

        Returns:
            Thông báo kết quả với số lượng đã xóa
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Đếm số lượng bookmark hiện có
        count = await self.bookmark_repo.count_by_user(user_id, book_id)

        # Xóa tất cả bookmark
        if count > 0:
            deleted_count = await self.bookmark_repo.delete_by_user_and_book(
                user_id, book_id
            )

            # Track metric
            self.metrics.track_user_activity("bookmarks_bulk_deleted")

            return {
                "success": True,
                "message": f"Đã xóa {deleted_count} bookmark cho sách này",
                "count": deleted_count,
            }
        else:
            return {
                "success": True,
                "message": "Không có bookmark nào để xóa",
                "count": 0,
            }

    @cached(
        ttl=1800,
        namespace="bookmarks",
        tags=["user_bookmarks"],
        key_builder=lambda *args, **kwargs: f"latest_book_bookmark:{kwargs.get('user_id')}:{kwargs.get('book_id')}",
    )
    async def get_latest_book_bookmark(
        self, user_id: int, book_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy bookmark gần đây nhất của người dùng cho một cuốn sách.
        Hữu ích để "đọc tiếp" từ vị trí gần nhất.

        Args:
            user_id: ID người dùng
            book_id: ID sách

        Returns:
            Thông tin bookmark hoặc None nếu chưa có
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy bookmark mới nhất
        bookmark = await self.bookmark_repo.get_latest_by_user_and_book(
            user_id, book_id, with_relations=["chapter", "book"]
        )

        if not bookmark:
            return None

        # Track metric
        self.metrics.track_user_activity("latest_bookmark_retrieved")

        return self._format_bookmark_response(bookmark)

    @cached(
        ttl=1800,
        namespace="bookmarks",
        tags=["user_bookmarks"],
        key_builder=lambda *args, **kwargs: f"recent_bookmarks:{kwargs.get('user_id')}:{kwargs.get('limit')}",
    )
    async def list_recent_bookmarks(
        self, user_id: int, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Liệt kê các bookmark gần đây của người dùng.
        Hữu ích cho tính năng "Đọc gần đây" hoặc "Tiếp tục đọc".

        Args:
            user_id: ID người dùng
            limit: Số lượng bookmark tối đa trả về

        Returns:
            Danh sách bookmark gần đây
        """
        bookmarks = await self.bookmark_repo.list_recent_by_user(
            user_id, limit, with_relations=["book", "chapter"]
        )

        # Track metric
        self.metrics.track_user_activity("recent_bookmarks_listed")

        return [self._format_bookmark_response(bookmark) for bookmark in bookmarks]

    def _format_bookmark_response(self, bookmark) -> Dict[str, Any]:
        """
        Chuyển đổi đối tượng bookmark thành response dict.

        Args:
            bookmark: Đối tượng Bookmark từ database

        Returns:
            Dict thông tin bookmark đã được format
        """
        result = {
            "id": bookmark.id,
            "user_id": bookmark.user_id,
            "book_id": bookmark.book_id,
            "chapter_id": bookmark.chapter_id,
            "position_offset": bookmark.position_offset,
            "title": bookmark.title,
            "note": bookmark.note,
            "color": bookmark.color,
            "created_at": bookmark.created_at,
            "updated_at": bookmark.updated_at,
        }

        # Thêm thông tin sách nếu đã load
        if hasattr(bookmark, "book") and bookmark.book:
            result["book"] = {
                "id": bookmark.book.id,
                "title": bookmark.book.title,
                "cover_thumbnail_url": bookmark.book.cover_thumbnail_url,
            }

        # Thêm thông tin chương nếu đã load
        if hasattr(bookmark, "chapter") and bookmark.chapter:
            result["chapter"] = {
                "id": bookmark.chapter.id,
                "title": bookmark.chapter.title,
                "number": bookmark.chapter.number,
            }

        return result
