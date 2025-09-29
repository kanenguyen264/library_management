from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.chapter_repo import ChapterRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.bookmark_repo import BookmarkRepository
from app.user_site.repositories.reading_history_repo import ReadingHistoryRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import requires_role, check_permission


class ChapterService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.chapter_repo = ChapterRepository(db)
        self.book_repo = BookRepository(db)
        self.bookmark_repo = BookmarkRepository(db)
        self.reading_history_repo = ReadingHistoryRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    async def create_chapter(
        self,
        book_id: int,
        title: str,
        content: str,
        number: int,
        is_free: bool = False,
        words_count: Optional[int] = None,
        admin_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Tạo chương mới cho sách.

        Args:
            book_id: ID của sách
            title: Tiêu đề chương
            content: Nội dung chương
            number: Số thứ tự chương
            is_free: Là chương miễn phí hay không
            words_count: Số từ trong chương (tùy chọn)
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông tin chương đã tạo

        Raises:
            NotFoundException: Nếu không tìm thấy sách
            BadRequestException: Nếu số thứ tự chương đã tồn tại
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra số thứ tự chương
        existing_chapter = await self.chapter_repo.get_by_book_and_number(
            book_id, number
        )
        if existing_chapter:
            raise BadRequestException(
                detail=f"Đã tồn tại chương số {number} trong sách này"
            )

        # Tính số từ nếu không cung cấp
        if words_count is None:
            words_count = len(content.split())

        # Tạo chương mới
        chapter = await self.chapter_repo.create(
            book_id=book_id,
            title=title,
            content=content,
            number=number,
            is_free=is_free,
            words_count=words_count,
        )

        # Cập nhật tổng số chương và tổng số từ cho sách
        await self.book_repo.update_chapter_stats(book_id)

        # Log the creation activity if admin_id is provided
        if admin_id:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="CHAPTER",
                        entity_id=chapter.id,
                        description=f"Created chapter {number} for book: {book.title}",
                        metadata={
                            "book_id": book_id,
                            "book_title": book.title,
                            "chapter_number": number,
                            "chapter_title": title,
                            "is_free": is_free,
                            "words_count": words_count,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {
            "id": chapter.id,
            "book_id": chapter.book_id,
            "title": chapter.title,
            "number": chapter.number,
            "is_free": chapter.is_free,
            "words_count": chapter.words_count,
            "created_at": chapter.created_at,
            "updated_at": chapter.updated_at,
        }

    @cached(
        ttl=1800,
        namespace="chapters",
        tags=["chapter_detail"],
        key_builder=lambda *args, **kwargs: f"chapter:{kwargs.get('chapter_id')}",
    )
    async def get_chapter(
        self,
        chapter_id: int,
        user_id: Optional[int] = None,
        include_content: bool = True,
    ) -> Dict[str, Any]:
        """
        Lấy thông tin chi tiết của một chương sách.

        Args:
            chapter_id: ID của chương
            user_id: ID người dùng đang xem (nếu có)
            include_content: Có bao gồm nội dung chương hay không

        Returns:
            Thông tin chi tiết của chương

        Raises:
            NotFoundException: Nếu không tìm thấy chương
        """
        with self.profiler.profile("get_chapter"):
            # Lấy thông tin chương
            chapter = await self.chapter_repo.get_by_id(
                chapter_id, with_relations=["book"]
            )

            if not chapter:
                raise NotFoundException(
                    detail=f"Không tìm thấy chương với ID {chapter_id}"
                )

            # Kiểm tra xem sách có trạng thái công khai không
            if chapter.book.status != "published" and (
                not user_id
                or not await check_permission(
                    user_id, "read_unpublished_book", chapter.book.id
                )
            ):
                raise ForbiddenException(detail="Bạn không có quyền xem chương này")

            # Lưu lịch sử đọc cho người dùng nếu có user_id
            if user_id:
                await self._save_reading_history(user_id, chapter.id, chapter.book_id)

            # Tăng lượt xem cho chương
            await self.chapter_repo.increment_views(chapter_id)

            # Track metric
            self.metrics.track_user_activity("chapter_viewed")

            # Format kết quả trả về
            result = self._format_chapter_response(chapter, include_content)

            # Nếu có user_id, kiểm tra và thêm thông tin bookmark
            if user_id:
                bookmark = await self.bookmark_repo.get_by_user_and_chapter(
                    user_id, chapter_id
                )
                if bookmark:
                    result["bookmark"] = {
                        "id": bookmark.id,
                        "position": bookmark.position,
                        "note": bookmark.note,
                        "created_at": bookmark.created_at,
                    }

            # Lấy thông tin chương trước và sau
            result["prev_chapter"] = await self._get_adjacent_chapter(chapter, False)
            result["next_chapter"] = await self._get_adjacent_chapter(chapter, True)

            return result

    @cached(
        ttl=1800,
        namespace="chapters",
        tags=["book_chapters"],
        key_builder=lambda *args, **kwargs: (
            f"book_chapters:{kwargs.get('book_id')}:"
            f"{kwargs.get('skip')}:{kwargs.get('limit')}"
        ),
    )
    async def list_chapters_by_book(
        self,
        book_id: int,
        skip: int = 0,
        limit: int = 100,
        include_unpublished: bool = False,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách các chương của một cuốn sách.

        Args:
            book_id: ID của sách
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            include_unpublished: Có bao gồm chương chưa xuất bản không
            user_id: ID người dùng (để kiểm tra quyền)

        Returns:
            Danh sách chương và thông tin tổng số

        Raises:
            NotFoundException: Nếu không tìm thấy sách
            ForbiddenException: Nếu người dùng không có quyền xem chương chưa xuất bản
        """
        with self.profiler.profile("list_chapters_by_book"):
            # Kiểm tra sách tồn tại
            book = await self.book_repo.get_by_id(book_id)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Kiểm tra quyền xem các chương chưa xuất bản
            if include_unpublished and (
                not user_id
                or not await check_permission(user_id, "read_unpublished_book", book_id)
            ):
                raise ForbiddenException(
                    detail="Bạn không có quyền xem các chương chưa xuất bản"
                )

            # Lấy danh sách chương
            chapters = await self.chapter_repo.list_by_book(
                book_id, skip, limit, include_unpublished=include_unpublished
            )

            # Đếm tổng số chương
            total = await self.chapter_repo.count_by_book(book_id, include_unpublished)

            # Track metric
            self.metrics.track_user_activity("book_chapters_listed")

            return {
                "items": [
                    self._format_chapter_response(chapter, include_content=False)
                    for chapter in chapters
                ],
                "total": total,
                "book": {
                    "id": book.id,
                    "title": book.title,
                    "slug": book.slug,
                    "cover_image": book.cover_image,
                },
            }

    async def get_user_reading_progress(
        self, user_id: int, book_id: int
    ) -> Dict[str, Any]:
        """
        Lấy tiến độ đọc sách của người dùng.

        Args:
            user_id: ID người dùng
            book_id: ID sách

        Returns:
            Thông tin tiến độ đọc, chương đang đọc và trạng thái
        """
        with self.profiler.profile("get_user_reading_progress"):
            # Kiểm tra sách tồn tại
            book = await self.book_repo.get_by_id(book_id)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Lấy tổng số chương
            total_chapters = await self.chapter_repo.count_by_book(
                book_id, include_unpublished=False
            )

            # Lấy chương đọc gần nhất
            last_read = await self.reading_history_repo.get_last_read_chapter(
                user_id, book_id
            )

            # Đếm số chương đã đọc
            read_chapters = await self.reading_history_repo.count_read_chapters(
                user_id, book_id
            )

            # Tính phần trăm hoàn thành
            progress_percent = 0
            if total_chapters > 0:
                progress_percent = (read_chapters / total_chapters) * 100

            result = {
                "book_id": book_id,
                "total_chapters": total_chapters,
                "read_chapters": read_chapters,
                "progress_percent": round(progress_percent, 2),
                "last_read_at": None,
                "current_chapter": None,
            }

            if last_read:
                result["last_read_at"] = last_read.updated_at
                result["current_chapter"] = {
                    "id": last_read.chapter_id,
                    "title": (
                        last_read.chapter.title
                        if hasattr(last_read, "chapter")
                        else None
                    ),
                    "number": (
                        last_read.chapter.number
                        if hasattr(last_read, "chapter")
                        else None
                    ),
                }

            # Track metric
            self.metrics.track_user_activity("reading_progress_viewed")

            return result

    @cached(
        ttl=1800,
        namespace="chapters",
        tags=["chapter_comments"],
        key_builder=lambda *args, **kwargs: (
            f"chapter_comments:{kwargs.get('chapter_id')}:"
            f"{kwargs.get('skip')}:{kwargs.get('limit')}"
        ),
    )
    async def list_chapter_comments(
        self, chapter_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách bình luận của một chương.

        Args:
            chapter_id: ID chương
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách bình luận và thông tin tổng số

        Raises:
            NotFoundException: Nếu không tìm thấy chương
        """
        # Kiểm tra chương tồn tại
        chapter = await self.chapter_repo.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        # Lấy danh sách bình luận
        comments = await self.chapter_repo.list_comments(chapter_id, skip, limit)

        # Đếm tổng số bình luận
        total = await self.chapter_repo.count_comments(chapter_id)

        # Track metric
        self.metrics.track_user_activity("chapter_comments_viewed")

        return {
            "items": [
                {
                    "id": comment.id,
                    "content": comment.content,
                    "user": (
                        {
                            "id": comment.user.id,
                            "username": comment.user.username,
                            "avatar": comment.user.avatar,
                        }
                        if hasattr(comment, "user")
                        else None
                    ),
                    "created_at": comment.created_at,
                    "updated_at": comment.updated_at,
                    "replies_count": (
                        comment.replies_count
                        if hasattr(comment, "replies_count")
                        else 0
                    ),
                }
                for comment in comments
            ],
            "total": total,
        }

    async def _save_reading_history(
        self, user_id: int, chapter_id: int, book_id: int
    ) -> None:
        """
        Lưu lịch sử đọc của người dùng.

        Args:
            user_id: ID người dùng
            chapter_id: ID chương
            book_id: ID sách
        """
        await self.reading_history_repo.create_or_update(
            user_id=user_id, book_id=book_id, chapter_id=chapter_id
        )

        # Invalidate cache cho tiến độ đọc
        cache_key = f"reading_progress:{user_id}:{book_id}"
        await self.cache.delete(cache_key)

    async def _get_adjacent_chapter(
        self, chapter: Any, is_next: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin chương trước hoặc sau.

        Args:
            chapter: Đối tượng chương hiện tại
            is_next: True để lấy chương tiếp theo, False để lấy chương trước

        Returns:
            Thông tin chương trước hoặc sau, hoặc None nếu không có
        """
        adjacent_chapter = await self.chapter_repo.get_adjacent_chapter(
            chapter.book_id, chapter.number, is_next
        )

        if not adjacent_chapter:
            return None

        return {
            "id": adjacent_chapter.id,
            "title": adjacent_chapter.title,
            "number": adjacent_chapter.number,
            "slug": adjacent_chapter.slug,
        }

    def _format_chapter_response(
        self, chapter: Any, include_content: bool = True
    ) -> Dict[str, Any]:
        """
        Chuyển đổi đối tượng chapter thành response dict.

        Args:
            chapter: Đối tượng Chapter từ database
            include_content: Có bao gồm nội dung không

        Returns:
            Dict thông tin chapter đã được format
        """
        result = {
            "id": chapter.id,
            "title": chapter.title,
            "number": chapter.number,
            "slug": chapter.slug,
            "status": chapter.status,
            "views": chapter.views,
            "created_at": chapter.created_at,
            "updated_at": chapter.updated_at,
            "book_id": chapter.book_id,
        }

        # Thêm thông tin sách nếu đã load
        if hasattr(chapter, "book") and chapter.book:
            result["book"] = {
                "id": chapter.book.id,
                "title": chapter.book.title,
                "slug": chapter.book.slug,
                "cover_image": chapter.book.cover_image,
            }

        # Thêm nội dung nếu được yêu cầu
        if include_content:
            result["content"] = chapter.content

        return result

    async def get_chapter_by_number(
        self, book_id: int, number: int, with_content: bool = True
    ) -> Dict[str, Any]:
        """
        Lấy thông tin chương theo số thứ tự.

        Args:
            book_id: ID của sách
            number: Số thứ tự chương
            with_content: Bao gồm nội dung hay không

        Returns:
            Thông tin chương

        Raises:
            NotFoundException: Nếu không tìm thấy sách hoặc chương
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy thông tin chương
        chapter = await self.chapter_repo.get_by_book_and_number(book_id, number)
        if not chapter:
            raise NotFoundException(
                detail=f"Không tìm thấy chương số {number} trong sách này"
            )

        result = {
            "id": chapter.id,
            "book_id": chapter.book_id,
            "title": chapter.title,
            "number": chapter.number,
            "is_free": chapter.is_free,
            "words_count": chapter.words_count,
            "created_at": chapter.created_at,
            "updated_at": chapter.updated_at,
        }

        if with_content:
            result["content"] = chapter.content

        return result

    async def list_book_chapters(
        self, book_id: int, skip: int = 0, limit: int = 100
    ) -> Dict[str, Any]:
        """
        Lấy danh sách chương của sách.

        Args:
            book_id: ID của sách
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách chương và thông tin phân trang

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy danh sách chương
        chapters = await self.chapter_repo.list_by_book(book_id, skip, limit)
        total = await self.chapter_repo.count_by_book(book_id)

        return {
            "book": {
                "id": book.id,
                "title": book.title,
                "cover_image": book.cover_image,
            },
            "items": [
                {
                    "id": chapter.id,
                    "title": chapter.title,
                    "number": chapter.number,
                    "is_free": chapter.is_free,
                    "words_count": chapter.words_count,
                    "created_at": chapter.created_at,
                }
                for chapter in chapters
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def update_chapter(
        self, chapter_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin chương.

        Args:
            chapter_id: ID của chương
            data: Dữ liệu cập nhật

        Returns:
            Thông tin chương đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy chương
            BadRequestException: Nếu số thứ tự chương mới đã tồn tại
        """
        # Kiểm tra chương tồn tại
        chapter = await self.chapter_repo.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        # Get book info for logging
        book = await self.book_repo.get_by_id(chapter.book_id)

        # Kiểm tra số thứ tự chương mới nếu có
        if "number" in data and data["number"] != chapter.number:
            existing_chapter = await self.chapter_repo.get_by_book_and_number(
                chapter.book_id, data["number"]
            )
            if existing_chapter:
                raise BadRequestException(
                    detail=f"Đã tồn tại chương số {data['number']} trong sách này"
                )

        # Cập nhật số từ nếu nội dung thay đổi
        if "content" in data and "words_count" not in data:
            data["words_count"] = len(data["content"].split())

        # Ngăn cập nhật book_id
        if "book_id" in data:
            del data["book_id"]

        # Cập nhật
        updated = await self.chapter_repo.update(chapter_id, data)

        # Cập nhật thống kê sách nếu số từ thay đổi
        if "content" in data or "words_count" in data:
            await self.book_repo.update_chapter_stats(updated.book_id)

        # Log the update activity if admin_id is provided
        if "admin_id" in data:
            try:
                # Track which fields were updated
                updated_fields = list(data.keys())
                updated_fields.remove("admin_id")

                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=data["admin_id"],
                        activity_type="UPDATE",
                        entity_type="CHAPTER",
                        entity_id=chapter_id,
                        description=f"Updated chapter {updated.number} for book: {book.title if book else 'Unknown'}",
                        metadata={
                            "book_id": updated.book_id,
                            "book_title": book.title if book else "Unknown",
                            "chapter_number": updated.number,
                            "chapter_title": updated.title,
                            "updated_fields": updated_fields,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        result = {
            "id": updated.id,
            "book_id": updated.book_id,
            "title": updated.title,
            "number": updated.number,
            "is_free": updated.is_free,
            "words_count": updated.words_count,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
        }

        # Trả về nội dung nếu đã cập nhật
        if "content" in data:
            result["content"] = updated.content

        return result

    async def delete_chapter(
        self, chapter_id: int, admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Xóa chương.

        Args:
            chapter_id: ID của chương
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy chương
        """
        # Kiểm tra chương tồn tại
        chapter = await self.chapter_repo.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        book_id = chapter.book_id

        # Get book info for logging
        book = await self.book_repo.get_by_id(book_id)

        # Xóa chương
        await self.chapter_repo.delete(chapter_id)

        # Cập nhật thống kê sách
        await self.book_repo.update_chapter_stats(book_id)

        # Log the deletion activity if admin_id is provided
        if admin_id:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="CHAPTER",
                        entity_id=chapter_id,
                        description=f"Deleted chapter {chapter.number} from book: {book.title if book else 'Unknown'}",
                        metadata={
                            "book_id": book_id,
                            "book_title": book.title if book else "Unknown",
                            "chapter_number": chapter.number,
                            "chapter_title": chapter.title,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {"message": "Đã xóa chương thành công"}

    async def get_nearby_chapters(self, chapter_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin chương trước và chương sau.

        Args:
            chapter_id: ID của chương hiện tại

        Returns:
            Thông tin chương trước và chương sau

        Raises:
            NotFoundException: Nếu không tìm thấy chương
        """
        # Kiểm tra chương tồn tại
        chapter = await self.chapter_repo.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        prev_chapter = await self.chapter_repo.get_prev_chapter(
            chapter.book_id, chapter.number
        )
        next_chapter = await self.chapter_repo.get_next_chapter(
            chapter.book_id, chapter.number
        )

        result = {
            "current": {
                "id": chapter.id,
                "book_id": chapter.book_id,
                "title": chapter.title,
                "number": chapter.number,
            }
        }

        if prev_chapter:
            result["prev"] = {
                "id": prev_chapter.id,
                "title": prev_chapter.title,
                "number": prev_chapter.number,
                "is_free": prev_chapter.is_free,
            }
        else:
            result["prev"] = None

        if next_chapter:
            result["next"] = {
                "id": next_chapter.id,
                "title": next_chapter.title,
                "number": next_chapter.number,
                "is_free": next_chapter.is_free,
            }
        else:
            result["next"] = None

        return result

    async def reorder_chapters(
        self,
        book_id: int,
        chapter_orders: List[Dict[str, Any]],
        admin_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Sắp xếp lại thứ tự các chương trong sách.

        Args:
            book_id: ID của sách
            chapter_orders: Danh sách thông tin sắp xếp (id và number mới)
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy sách
            BadRequestException: Nếu thông tin sắp xếp không hợp lệ
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra thông tin sắp xếp
        for order in chapter_orders:
            if "id" not in order or "number" not in order:
                raise BadRequestException(
                    detail="Thông tin sắp xếp phải có id và number"
                )

        # Lấy tất cả chương của sách
        book_chapters = await self.chapter_repo.list_by_book(book_id, 0, 1000)
        chapter_ids = {chapter.id for chapter in book_chapters}

        # Kiểm tra tất cả chương cần sắp xếp thuộc về sách
        for order in chapter_orders:
            if order["id"] not in chapter_ids:
                raise BadRequestException(
                    detail=f"Chương với ID {order['id']} không thuộc về sách này"
                )

        # Sắp xếp lại
        for order in chapter_orders:
            await self.chapter_repo.update(order["id"], {"number": order["number"]})

        # Log the reordering activity if admin_id is provided
        if admin_id:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="REORDER",
                        entity_type="CHAPTERS",
                        entity_id=book_id,
                        description=f"Reordered chapters for book: {book.title}",
                        metadata={
                            "book_id": book_id,
                            "book_title": book.title,
                            "chapter_count": len(chapter_orders),
                            "chapter_orders": chapter_orders,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {"message": "Đã sắp xếp lại thứ tự chương thành công"}

    async def get_free_chapters(
        self, book_id: int, limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách chương miễn phí của sách.

        Args:
            book_id: ID của sách
            limit: Số lượng chương tối đa trả về

        Returns:
            Danh sách chương miễn phí

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        chapters = await self.chapter_repo.list_free_by_book(book_id, limit)

        return [
            {
                "id": chapter.id,
                "title": chapter.title,
                "number": chapter.number,
                "words_count": chapter.words_count,
                "created_at": chapter.created_at,
            }
            for chapter in chapters
        ]

    async def check_chapter_access(
        self, user_id: int, chapter_id: int
    ) -> Dict[str, Any]:
        """
        Kiểm tra người dùng có quyền truy cập chương hay không.

        Args:
            user_id: ID của người dùng
            chapter_id: ID của chương

        Returns:
            Kết quả kiểm tra quyền truy cập

        Raises:
            NotFoundException: Nếu không tìm thấy chương
        """
        # Kiểm tra chương tồn tại
        chapter = await self.chapter_repo.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        # Kiểm tra chương miễn phí
        if chapter.is_free:
            return {"has_access": True, "reason": "free_chapter"}

        # Kiểm tra người dùng đã mua sách
        has_purchased = await self.book_repo.user_has_purchased(
            user_id, chapter.book_id
        )
        if has_purchased:
            return {"has_access": True, "reason": "purchased_book"}

        # Kiểm tra người dùng có gói đọc không giới hạn
        has_unlimited = await self.book_repo.user_has_unlimited_access(user_id)
        if has_unlimited:
            return {"has_access": True, "reason": "unlimited_plan"}

        return {"has_access": False, "reason": "no_access"}
