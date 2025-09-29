from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.quote_repo import QuoteRepository
from app.user_site.repositories.quote_like_repo import QuoteLikeRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache
from app.cache.keys import CacheKeyBuilder
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import check_permission
from app.logs_manager.services.user_activity_log_service import UserActivityLogService
from app.core.config import get_settings

settings = get_settings()


class QuoteService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.quote_repo = QuoteRepository(db)
        self.quote_like_repo = QuoteLikeRepository(db)
        self.book_repo = BookRepository(db)
        self.chapter_repo = ChapterRepository(db)
        self.user_repo = UserRepository(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="quotes", tags=["user_quotes", "book_quotes", "chapter_quotes"]
    )
    async def create_quote(
        self,
        user_id: int,
        book_id: int,
        content: str,
        chapter_id: Optional[int] = None,
        start_offset: Optional[str] = None,
        end_offset: Optional[str] = None,
        is_public: bool = True,
    ) -> Dict[str, Any]:
        """
        Tạo trích dẫn mới.

        Args:
            user_id: ID của người dùng
            book_id: ID của sách
            content: Nội dung trích dẫn
            chapter_id: ID của chương (tùy chọn)
            start_offset: Vị trí bắt đầu trích dẫn (tùy chọn)
            end_offset: Vị trí kết thúc trích dẫn (tùy chọn)
            is_public: Trạng thái công khai

        Returns:
            Thông tin trích dẫn đã tạo

        Raises:
            NotFoundException: Nếu không tìm thấy sách hoặc chương
            BadRequestException: Nếu nội dung trống
        """
        # Kiểm tra nội dung
        if not content or not content.strip():
            raise BadRequestException(detail="Nội dung trích dẫn không được để trống")

        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra chương tồn tại nếu có
        chapter = None
        if chapter_id:
            chapter = await self.chapter_repo.get_by_id(chapter_id)
            if not chapter:
                raise NotFoundException(
                    detail=f"Không tìm thấy chương với ID {chapter_id}"
                )

            if chapter.book_id != book_id:
                raise BadRequestException(detail="Chương không thuộc về sách này")

        # Tạo trích dẫn
        quote_data = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "content": content,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "is_public": is_public,
            "likes_count": 0,
            "shares_count": 0,
        }

        quote = await self.quote_repo.create(quote_data)

        # Log user activity - creating a quote
        try:
            metadata = {
                "book_id": book_id,
                "book_title": book.title,
                "content_preview": (
                    content[:100] + "..." if len(content) > 100 else content
                ),
                "is_public": is_public,
            }

            if chapter_id and chapter:
                metadata["chapter_id"] = chapter_id
                metadata["chapter_title"] = chapter.title

            await self.user_log_service.log_activity(
                self.db,
                user_id=user_id,
                activity_type="CREATE_QUOTE",
                resource_type="quote",
                resource_id=str(quote.id),
                metadata=metadata,
            )
        except Exception:
            # Log but don't fail if logging fails
            pass

        return {
            "id": quote.id,
            "user_id": quote.user_id,
            "book_id": quote.book_id,
            "chapter_id": quote.chapter_id,
            "content": quote.content,
            "start_offset": quote.start_offset,
            "end_offset": quote.end_offset,
            "is_public": quote.is_public,
            "likes_count": quote.likes_count,
            "shares_count": quote.shares_count,
            "created_at": quote.created_at,
            "updated_at": quote.updated_at,
            "book_title": book.title,
            "chapter_title": chapter.title if chapter_id and chapter else None,
            "user_name": (await self.user_repo.get(user_id)).username,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="quotes", tags=["quote_details"])
    async def get_quote(
        self, quote_id: int, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin trích dẫn theo ID.

        Args:
            quote_id: ID của trích dẫn
            user_id: ID của người dùng (tùy chọn, để kiểm tra thích)

        Returns:
            Thông tin trích dẫn

        Raises:
            NotFoundException: Nếu không tìm thấy trích dẫn
            ForbiddenException: Nếu trích dẫn không công khai và không phải của người dùng
        """
        # Kiểm tra trích dẫn tồn tại
        quote = await self.quote_repo.get_by_id(quote_id)
        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID {quote_id}"
            )

        # Kiểm tra quyền truy cập
        if not quote.is_public and user_id is not None and quote.user_id != user_id:
            try:
                has_permission = await check_permission(user_id, "view_all_quotes")
                if not has_permission:
                    raise ForbiddenException(
                        detail="Bạn không có quyền xem trích dẫn này"
                    )
            except:
                raise ForbiddenException(detail="Bạn không có quyền xem trích dẫn này")

        result = {
            "id": quote.id,
            "user_id": quote.user_id,
            "book_id": quote.book_id,
            "chapter_id": quote.chapter_id,
            "content": quote.content,
            "start_offset": quote.start_offset,
            "end_offset": quote.end_offset,
            "is_public": quote.is_public,
            "likes_count": quote.likes_count,
            "shares_count": quote.shares_count,
            "created_at": quote.created_at,
            "updated_at": quote.updated_at,
            "book": (
                {
                    "id": quote.book.id,
                    "title": quote.book.title,
                    "cover_image": quote.book.cover_image,
                    "cover_thumbnail_url": quote.book.cover_thumbnail_url,
                }
                if hasattr(quote, "book") and quote.book
                else None
            ),
            "chapter": (
                {
                    "id": quote.chapter.id,
                    "title": quote.chapter.title,
                    "number": quote.chapter.number,
                }
                if hasattr(quote, "chapter") and quote.chapter
                else None
            ),
            "user": (
                {
                    "id": quote.user.id,
                    "username": quote.user.username,
                    "display_name": quote.user.display_name,
                    "avatar_url": quote.user.avatar_url,
                }
                if hasattr(quote, "user") and quote.user
                else None
            ),
            "has_liked": await self.quote_like_repo.get_by_user_and_quote(
                user_id, quote_id
            )
            is not None,
            "is_owner": user_id == quote.user_id,
        }

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="quotes", tags=["quote_details", "user_quotes"])
    async def update_quote(
        self, quote_id: int, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin trích dẫn.

        Args:
            quote_id: ID của trích dẫn
            user_id: ID của người dùng (để kiểm tra quyền)
            data: Dữ liệu cập nhật

        Returns:
            Thông tin trích dẫn đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy trích dẫn
            ForbiddenException: Nếu người dùng không có quyền
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra trích dẫn tồn tại
        quote = await self.quote_repo.get_by_id(quote_id)
        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID {quote_id}"
            )

        # Kiểm tra quyền
        if quote.user_id != user_id:
            try:
                has_permission = await check_permission(user_id, "manage_quotes")
                if not has_permission:
                    raise ForbiddenException(
                        detail="Bạn không có quyền cập nhật trích dẫn này"
                    )
            except:
                raise ForbiddenException(
                    detail="Bạn không có quyền cập nhật trích dẫn này"
                )

        # Kiểm tra nội dung nếu có
        if "content" in data and (not data["content"] or not data["content"].strip()):
            raise BadRequestException(detail="Nội dung trích dẫn không được để trống")

        # Ngăn cập nhật một số trường
        protected_fields = [
            "user_id",
            "book_id",
            "chapter_id",
            "likes_count",
            "shares_count",
        ]
        for field in protected_fields:
            if field in data:
                del data[field]

        # Lưu trạng thái cũ
        before_state = {
            "id": quote.id,
            "content": quote.content,
            "is_public": quote.is_public,
        }

        # Cập nhật trích dẫn
        updated = await self.quote_repo.update(quote_id, data)

        # Lấy thông tin sách và chương
        book = await self.book_repo.get_by_id(updated.book_id)
        chapter = None
        if updated.chapter_id:
            chapter = await self.chapter_repo.get_by_id(updated.chapter_id)

        # Lấy thông tin người dùng
        quote_user = await self.user_repo.get(updated.user_id)

        result = {
            "id": updated.id,
            "user_id": updated.user_id,
            "book_id": updated.book_id,
            "chapter_id": updated.chapter_id,
            "content": updated.content,
            "start_offset": updated.start_offset,
            "end_offset": updated.end_offset,
            "is_public": updated.is_public,
            "likes_count": updated.likes_count,
            "shares_count": updated.shares_count,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
            "book_title": book.title if book else None,
            "chapter_title": chapter.title if chapter else None,
            "user_name": quote_user.username if quote_user else None,
        }

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="UPDATE_QUOTE",
            resource_type="quote",
            resource_id=str(quote_id),
            before_state=before_state,
            after_state={
                "id": updated.id,
                "content": updated.content,
                "is_public": updated.is_public,
            },
            metadata={"updated_fields": list(data.keys())},
        )

        # Metrics
        self.metrics.track_user_activity("update_quote", "registered")

        # Xóa cache
        cache_key = CacheKeyBuilder.build_key("quote", quote_id)
        await self.cache.delete(cache_key)

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="quotes",
        tags=["quote_details", "user_quotes", "book_quotes", "chapter_quotes"],
    )
    async def delete_quote(self, quote_id: int, user_id: int) -> Dict[str, Any]:
        """
        Xóa trích dẫn.

        Args:
            quote_id: ID của trích dẫn
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy trích dẫn
            ForbiddenException: Nếu người dùng không có quyền
        """
        # Kiểm tra trích dẫn tồn tại
        quote = await self.quote_repo.get_by_id(quote_id)
        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID {quote_id}"
            )

        # Kiểm tra quyền
        if quote.user_id != user_id:
            try:
                has_permission = await check_permission(user_id, "manage_quotes")
                if not has_permission:
                    raise ForbiddenException(
                        detail="Bạn không có quyền xóa trích dẫn này"
                    )
            except:
                raise ForbiddenException(detail="Bạn không có quyền xóa trích dẫn này")

        # Lưu thông tin trước khi xóa
        book = await self.book_repo.get_by_id(quote.book_id)
        chapter = None
        if quote.chapter_id:
            chapter = await self.chapter_repo.get_by_id(quote.chapter_id)

        before_state = {
            "id": quote.id,
            "content": quote.content,
            "book_id": quote.book_id,
            "book_title": book.title if book else None,
            "chapter_id": quote.chapter_id,
            "chapter_title": chapter.title if chapter else None,
            "is_public": quote.is_public,
        }

        # Xóa trích dẫn
        await self.quote_repo.delete(quote_id)

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="DELETE_QUOTE",
            resource_type="quote",
            resource_id=str(quote_id),
            before_state=before_state,
        )

        # Metrics
        self.metrics.track_user_activity("delete_quote", "registered")

        # Xóa cache
        cache_key = CacheKeyBuilder.build_key("quote", quote_id)
        await self.cache.delete(cache_key)

        return {"message": "Đã xóa trích dẫn thành công"}

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="quotes", tags=["book_quotes"])
    async def list_book_quotes(
        self,
        book_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách trích dẫn của một sách.

        Args:
            book_id: ID của sách
            user_id: ID của người dùng (tùy chọn, để kiểm tra thích)
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách trích dẫn và thông tin phân trang
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key(
            "book_quotes", book_id, user_id or "anonymous", skip, limit
        )

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy danh sách trích dẫn
        quotes = await self.quote_repo.list_by_book(book_id, skip, limit)
        total = await self.quote_repo.count_by_book(book_id)

        # Xử lý quyền riêng tư và lấy thông tin người dùng
        filtered_quotes = []
        user_ids = set()

        for quote in quotes:
            if quote.is_public or (user_id and quote.user_id == user_id):
                filtered_quotes.append(quote)
                user_ids.add(quote.user_id)

        # Lấy thông tin người dùng
        users = {}
        for u_id in user_ids:
            user = await self.user_repo.get(u_id)
            if user:
                users[u_id] = {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar": user.avatar,
                }

        # Lấy thông tin đã thích của người dùng
        liked_quotes = {}
        if user_id:
            for quote in filtered_quotes:
                liked = await self.quote_repo.check_user_liked(quote.id, user_id)
                liked_quotes[quote.id] = liked

        result = {
            "items": [
                {
                    "id": quote.id,
                    "user_id": quote.user_id,
                    "book_id": quote.book_id,
                    "chapter_id": quote.chapter_id,
                    "content": quote.content,
                    "is_public": quote.is_public,
                    "likes_count": quote.likes_count,
                    "shares_count": quote.shares_count,
                    "created_at": quote.created_at,
                    "user": users.get(quote.user_id),
                    "has_liked": (
                        liked_quotes.get(quote.id, False) if user_id else False
                    ),
                    "is_owner": user_id == quote.user_id,
                }
                for quote in filtered_quotes
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
            "book": {
                "id": book.id,
                "title": book.title,
                "author_name": book.author_name,
                "cover_image": book.cover_image,
            },
        }

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=1800)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="quotes", tags=["chapter_quotes"])
    async def list_chapter_quotes(
        self,
        chapter_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách trích dẫn của một chương.

        Args:
            chapter_id: ID của chương
            user_id: ID của người dùng (tùy chọn, để kiểm tra thích)
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách trích dẫn và thông tin phân trang
        """
        # Kiểm tra chương tồn tại
        chapter = await self.chapter_repo.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key(
            "chapter_quotes", chapter_id, user_id or "anonymous", skip, limit
        )

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy thông tin sách
        book = await self.book_repo.get_by_id(chapter.book_id)

        # Lấy danh sách trích dẫn
        quotes = await self.quote_repo.list_by_chapter(chapter_id, skip, limit)
        total = await self.quote_repo.count_by_chapter(chapter_id)

        # Xử lý quyền riêng tư và lấy thông tin người dùng
        filtered_quotes = []
        user_ids = set()

        for quote in quotes:
            if quote.is_public or (user_id and quote.user_id == user_id):
                filtered_quotes.append(quote)
                user_ids.add(quote.user_id)

        # Lấy thông tin người dùng
        users = {}
        for u_id in user_ids:
            user = await self.user_repo.get(u_id)
            if user:
                users[u_id] = {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar": user.avatar,
                }

        # Lấy thông tin đã thích của người dùng
        liked_quotes = {}
        if user_id:
            for quote in filtered_quotes:
                liked = await self.quote_repo.check_user_liked(quote.id, user_id)
                liked_quotes[quote.id] = liked

        result = {
            "items": [
                {
                    "id": quote.id,
                    "user_id": quote.user_id,
                    "book_id": quote.book_id,
                    "chapter_id": quote.chapter_id,
                    "content": quote.content,
                    "start_offset": quote.start_offset,
                    "end_offset": quote.end_offset,
                    "is_public": quote.is_public,
                    "likes_count": quote.likes_count,
                    "shares_count": quote.shares_count,
                    "created_at": quote.created_at,
                    "user": users.get(quote.user_id),
                    "has_liked": (
                        liked_quotes.get(quote.id, False) if user_id else False
                    ),
                    "is_owner": user_id == quote.user_id,
                }
                for quote in filtered_quotes
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
            "chapter": {
                "id": chapter.id,
                "title": chapter.title,
                "number": chapter.number,
            },
            "book": (
                {
                    "id": book.id,
                    "title": book.title,
                    "author_name": book.author_name,
                    "cover_image": book.cover_image,
                }
                if book
                else None
            ),
        }

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=1800)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="quotes", tags=["user_quotes"])
    async def list_user_quotes(
        self,
        user_id: int,
        current_user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách trích dẫn của một người dùng.

        Args:
            user_id: ID của người dùng chủ sở hữu trích dẫn
            current_user_id: ID của người dùng đang xem (tùy chọn, để kiểm tra thích)
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách trích dẫn và thông tin phân trang
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key(
            "user_quotes", user_id, current_user_id or "anonymous", skip, limit
        )

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Kiểm tra quyền xem
        view_private = False
        if current_user_id == user_id:
            view_private = True
        elif current_user_id:
            try:
                has_permission = await check_permission(
                    current_user_id, "view_all_quotes"
                )
                view_private = has_permission
            except:
                view_private = False

        # Lấy danh sách trích dẫn
        quotes = await self.quote_repo.list_by_user(user_id, skip, limit, view_private)
        total = await self.quote_repo.count_by_user(user_id, view_private)

        # Lấy thông tin sách và chương
        book_ids = {quote.book_id for quote in quotes}
        chapter_ids = {quote.chapter_id for quote in quotes if quote.chapter_id}

        books = {}
        for book_id in book_ids:
            book = await self.book_repo.get_by_id(book_id)
            if book:
                books[book_id] = {
                    "id": book.id,
                    "title": book.title,
                    "author_name": book.author_name,
                    "cover_image": book.cover_image,
                }

        chapters = {}
        for chapter_id in chapter_ids:
            chapter = await self.chapter_repo.get_by_id(chapter_id)
            if chapter:
                chapters[chapter_id] = {
                    "id": chapter.id,
                    "title": chapter.title,
                    "number": chapter.number,
                }

        # Lấy thông tin đã thích
        liked_quotes = {}
        if current_user_id:
            for quote in quotes:
                liked = await self.quote_repo.check_user_liked(
                    quote.id, current_user_id
                )
                liked_quotes[quote.id] = liked

        result = {
            "items": [
                {
                    "id": quote.id,
                    "user_id": quote.user_id,
                    "book_id": quote.book_id,
                    "chapter_id": quote.chapter_id,
                    "content": quote.content,
                    "is_public": quote.is_public,
                    "likes_count": quote.likes_count,
                    "shares_count": quote.shares_count,
                    "created_at": quote.created_at,
                    "updated_at": quote.updated_at,
                    "book": books.get(quote.book_id),
                    "chapter": (
                        chapters.get(quote.chapter_id) if quote.chapter_id else None
                    ),
                    "has_liked": (
                        liked_quotes.get(quote.id, False) if current_user_id else False
                    ),
                    "is_owner": current_user_id == quote.user_id,
                }
                for quote in quotes
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "avatar": user.avatar,
            },
        }

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=1800)

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="quotes", tags=["quote_details"])
    async def like_quote(self, quote_id: int, user_id: int) -> Dict[str, Any]:
        """
        Thích trích dẫn.

        Args:
            quote_id: ID của trích dẫn
            user_id: ID của người dùng

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy trích dẫn
            BadRequestException: Nếu người dùng đã thích trích dẫn này
        """
        # Kiểm tra trích dẫn tồn tại
        quote = await self.quote_repo.get_by_id(quote_id)
        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID {quote_id}"
            )

        # Kiểm tra người dùng đã thích trích dẫn này chưa
        existing = await self.quote_like_repo.get_by_user_and_quote(user_id, quote_id)
        if existing:
            raise BadRequestException(detail="Bạn đã thích trích dẫn này")

        # Tạo lượt thích
        like_data = {"user_id": user_id, "quote_id": quote_id}

        like = await self.quote_like_repo.create(like_data)

        # Cập nhật số lượt thích của trích dẫn
        await self.quote_repo.update(quote_id, {"likes_count": quote.likes_count + 1})

        # Log user activity - liking a quote
        try:
            book = await self.book_repo.get_by_id(quote.book_id)
            book_title = book.title if book else f"Book ID: {quote.book_id}"

            # Get quote creator's username for more meaningful log
            quote_creator = await self.user_repo.get_by_id(quote.user_id)
            creator_name = (
                quote_creator.username if quote_creator else f"User ID: {quote.user_id}"
            )

            await self.user_log_service.log_activity(
                self.db,
                user_id=user_id,
                activity_type="LIKE_QUOTE",
                resource_type="quote",
                resource_id=str(quote_id),
                metadata={"quote_owner_id": quote.user_id, "book_id": quote.book_id},
            )
        except Exception:
            # Log but don't fail if logging fails
            pass

        # Metrics
        self.metrics.track_user_activity("like_quote", "registered")

        return {
            "quote_id": quote_id,
            "user_id": user_id,
            "likes_count": quote.likes_count + 1,
            "has_liked": True,
            "created_at": like.created_at,
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="quotes", tags=["quote_details"])
    async def unlike_quote(self, quote_id: int, user_id: int) -> Dict[str, Any]:
        """
        Bỏ thích một trích dẫn.

        Args:
            quote_id: ID của trích dẫn
            user_id: ID của người dùng

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy trích dẫn hoặc lượt thích
        """
        # Kiểm tra trích dẫn tồn tại
        quote = await self.quote_repo.get_by_id(quote_id)
        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID {quote_id}"
            )

        # Kiểm tra lượt thích tồn tại
        like = await self.quote_like_repo.get_by_user_and_quote(user_id, quote_id)
        if not like:
            raise NotFoundException(detail="Bạn chưa thích trích dẫn này")

        # Xóa lượt thích
        await self.quote_like_repo.delete(like.id)

        # Cập nhật số lượt thích của trích dẫn
        new_likes_count = max(0, quote.likes_count - 1)
        await self.quote_repo.update(quote_id, {"likes_count": new_likes_count})

        # Log user activity - unliking a quote
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="UNLIKE_QUOTE",
            resource_type="quote",
            resource_id=str(quote_id),
        )

        # Metrics
        self.metrics.track_user_activity("unlike_quote", "registered")

        return {
            "quote_id": quote_id,
            "user_id": user_id,
            "likes_count": new_likes_count,
            "has_liked": False,
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="quotes", tags=["quote_details"])
    async def increment_share(self, quote_id: int) -> Dict[str, Any]:
        """
        Tăng số lượt chia sẻ của trích dẫn.

        Args:
            quote_id: ID của trích dẫn

        Returns:
            Thông tin số lượt chia sẻ mới

        Raises:
            NotFoundException: Nếu không tìm thấy trích dẫn
        """
        # Kiểm tra trích dẫn tồn tại
        quote = await self.quote_repo.get_by_id(quote_id)
        if not quote:
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID {quote_id}"
            )

        # Cập nhật số lượt chia sẻ
        new_shares_count = quote.shares_count + 1
        updated = await self.quote_repo.update(
            quote_id, {"shares_count": new_shares_count}
        )

        # Metrics
        self.metrics.track_content("quote_shared")

        return {"quote_id": quote_id, "shares_count": updated.shares_count}

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="quotes", tags=["popular_quotes"])
    async def get_popular_quotes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách trích dẫn phổ biến (có nhiều lượt thích nhất).

        Args:
            limit: Số lượng trích dẫn trả về

        Returns:
            Danh sách trích dẫn phổ biến
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("popular_quotes", limit)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy danh sách trích dẫn phổ biến (chỉ công khai)
        quotes = await self.quote_repo.get_popular(limit)

        # Lấy thông tin sách, chương và người dùng
        result = []
        for quote in quotes:
            # Lấy thông tin book
            book = await self.book_repo.get_by_id(quote.book_id)

            # Lấy thông tin chapter nếu có
            chapter = None
            if quote.chapter_id:
                chapter = await self.chapter_repo.get_by_id(quote.chapter_id)

            # Lấy thông tin user
            user = await self.user_repo.get(quote.user_id)

            result.append(
                {
                    "id": quote.id,
                    "content": quote.content,
                    "likes_count": quote.likes_count,
                    "shares_count": quote.shares_count,
                    "created_at": quote.created_at,
                    "book": (
                        {
                            "id": book.id,
                            "title": book.title,
                            "author_name": book.author_name,
                            "cover_image": book.cover_image,
                        }
                        if book
                        else None
                    ),
                    "chapter": (
                        {
                            "id": chapter.id,
                            "title": chapter.title,
                            "number": chapter.number,
                        }
                        if chapter
                        else None
                    ),
                    "user": (
                        {
                            "id": user.id,
                            "username": user.username,
                            "display_name": user.display_name,
                            "avatar": user.avatar,
                        }
                        if user
                        else None
                    ),
                }
            )

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=3600)

        return result
