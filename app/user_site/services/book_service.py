from typing import Optional, List, Dict, Any, Union
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from datetime import datetime

from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.author_repo import AuthorRepository
from app.user_site.repositories.category_repo import CategoryRepository
from app.user_site.repositories.tag_repo import TagRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.user_site.repositories.review_repo import ReviewRepository
from app.user_site.repositories.book_rating_repo import BookRatingRepository
from app.user_site.repositories.bookshelf_repo import BookshelfRepository
from app.user_site.repositories.reading_history_repo import ReadingHistoryRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.logs_manager.services import (
    create_admin_activity_log,
    create_user_activity_log,
)
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.cache.decorators import cached, invalidate_cache, cache_model, cache_list
from app.cache import get_cache
from app.cache.keys import create_api_response_key, generate_cache_key
from app.monitoring.metrics import Metrics
from app.performance.profiling.code_profiler import CodeProfiler
from app.security.input_validation.sanitizers import sanitize_html, sanitize_text
from app.security.access_control.rbac import check_permission


class BookService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.book_repo = BookRepository(db)
        self.author_repo = AuthorRepository(db)
        self.category_repo = CategoryRepository(db)
        self.tag_repo = TagRepository(db)
        self.chapter_repo = ChapterRepository(db)
        self.review_repo = ReviewRepository(db)
        self.rating_repo = BookRatingRepository(db)
        self.bookshelf_repo = BookshelfRepository(db)
        self.reading_history_repo = ReadingHistoryRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    @invalidate_cache(
        namespace="books", tags=["books", "featured_books", "trending_books"]
    )
    async def create_book(
        self, data: Dict[str, Any], admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Tạo sách mới.

        Args:
            data: Dữ liệu sách
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông tin sách đã tạo

        Raises:
            BadRequestException: Nếu thiếu thông tin bắt buộc
        """
        with self.metrics.time_request("POST", "/books"):
            # Kiểm tra các trường bắt buộc
            required_fields = ["title"]
            for field in required_fields:
                if field not in data:
                    raise BadRequestException(detail=f"Thiếu trường {field}")

            # Sanitize input data
            if "title" in data:
                data["title"] = sanitize_text(data["title"])

            if "description" in data and data["description"]:
                data["description"] = sanitize_html(data["description"])

            # Xử lý các mối quan hệ
            author_ids = data.pop("author_ids", []) if "author_ids" in data else []
            category_ids = (
                data.pop("category_ids", []) if "category_ids" in data else []
            )
            tag_ids = data.pop("tag_ids", []) if "tag_ids" in data else []

            # Tạo sách
            book = await self.book_repo.create(data)

            # Thêm các mối quan hệ
            if author_ids:
                await self.book_repo.add_authors(book.id, author_ids)

            if category_ids:
                await self.book_repo.add_categories(book.id, category_ids)

            if tag_ids:
                await self.book_repo.add_tags(book.id, tag_ids)

            # Log the book creation if admin_id is provided
            if admin_id:
                try:
                    await create_admin_activity_log(
                        self.db,
                        AdminActivityLogCreate(
                            admin_id=admin_id,
                            activity_type="CREATE",
                            entity_type="BOOK",
                            entity_id=book.id,
                            description=f"Created book: {book.title}",
                            metadata={
                                "title": book.title,
                                "isbn": book.isbn if hasattr(book, "isbn") else None,
                                "is_published": (
                                    book.is_published
                                    if hasattr(book, "is_published")
                                    else None
                                ),
                                "author_ids": author_ids,
                                "category_ids": category_ids,
                                "tag_ids": tag_ids,
                            },
                        ),
                    )
                except Exception:
                    # Log but don't fail if logging fails
                    pass

            # Invalidate related caches
            await self._invalidate_related_caches(
                book_id=book.id,
                author_ids=author_ids,
                category_ids=category_ids,
                tag_ids=tag_ids,
            )

            # Lấy sách với các mối quan hệ
            created_book = await self.book_repo.get_by_id(book.id, with_relations=True)

            # Track metrics
            self.metrics.track_book_activity("create", str(book.id), "admin")

            return self._format_book_response(created_book)

    @cached(
        ttl=3600,
        namespace="books",
        tags=["book_details"],
        key_builder=lambda *args, **kwargs: f"book:{kwargs.get('book_id')}",
    )
    async def get_book(
        self, book_id: int, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin chi tiết của một cuốn sách.

        Args:
            book_id: ID của sách
            user_id: ID người dùng (để lấy thông tin tương tác)

        Returns:
            Thông tin chi tiết của sách

        Raises:
            NotFoundException: Nếu không tìm thấy sách
            ForbiddenException: Nếu sách chưa xuất bản và người dùng không có quyền xem
        """
        with self.profiler.profile("get_book"):
            book = await self.book_repo.get_by_id(
                book_id, with_relations=["categories", "authors"]
            )

            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Kiểm tra quyền truy cập sách chưa xuất bản
            if book.status != "published" and (
                not user_id
                or not await check_permission(user_id, "read_unpublished_book", book_id)
            ):
                raise ForbiddenException(detail="Bạn không có quyền xem sách này")

            # Format kết quả
            result = self._format_book_response(book)

            # Thêm thông tin đánh giá
            rating_stats = await self.rating_repo.get_book_rating_stats(book_id)
            result["rating"] = {
                "average": rating_stats.get("average", 0),
                "count": rating_stats.get("count", 0),
                "distribution": rating_stats.get("distribution", {}),
            }

            # Thêm thông tin về tương tác của người dùng với sách
            if user_id:
                result["user_interaction"] = await self._get_user_book_interaction(
                    user_id, book_id
                )

            # Track metric
            self.metrics.track_user_activity("book_details_viewed")

            return result

    @cached(
        ttl=3600,
        namespace="books",
        tags=["book_details"],
        key_builder=lambda *args, **kwargs: f"book_isbn:{kwargs.get('isbn')}",
    )
    async def get_book_by_isbn(self, isbn: str) -> Dict[str, Any]:
        """
        Lấy thông tin sách theo ISBN.

        Args:
            isbn: Mã ISBN của sách

        Returns:
            Thông tin sách

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        with self.profiler.profile_time(name="get_book_by_isbn"):
            book = await self.book_repo.get_by_isbn(isbn)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ISBN {isbn}")

            # Track ISBN lookup metrics
            self.metrics.track_book_activity("isbn_lookup", str(book.id), "registered")

            return self._format_book_response(book)

    @invalidate_cache(
        namespace="books",
        tags=["book_details", "books", "featured_books", "trending_books"],
    )
    async def update_book(
        self, book_id: int, data: Dict[str, Any], admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin sách.

        Args:
            book_id: ID của sách
            data: Dữ liệu cập nhật
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông tin sách đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        with self.metrics.time_request("PUT", f"/books/{book_id}"):
            # Kiểm tra sách tồn tại
            book = await self.book_repo.get_by_id(book_id)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Sanitize input data
            if "title" in data:
                data["title"] = sanitize_text(data["title"])

            if "description" in data and data["description"]:
                data["description"] = sanitize_html(data["description"])

            # Xử lý các mối quan hệ
            author_ids = data.pop("author_ids", None)
            category_ids = data.pop("category_ids", None)
            tag_ids = data.pop("tag_ids", None)

            # Cập nhật sách
            updated = await self.book_repo.update(book_id, data)

            # Cập nhật các mối quan hệ nếu được cung cấp
            if author_ids is not None:
                await self.book_repo._update_authors(book_id, author_ids)

            if category_ids is not None:
                await self.book_repo._update_categories(book_id, category_ids)

            if tag_ids is not None:
                await self.book_repo._update_tags(book_id, tag_ids)

            # Log the book update if admin_id is provided
            if admin_id:
                try:
                    # Track which fields were updated
                    updated_fields = list(data.keys())
                    if author_ids is not None:
                        updated_fields.append("author_ids")
                    if category_ids is not None:
                        updated_fields.append("category_ids")
                    if tag_ids is not None:
                        updated_fields.append("tag_ids")

                    await create_admin_activity_log(
                        self.db,
                        AdminActivityLogCreate(
                            admin_id=admin_id,
                            activity_type="UPDATE",
                            entity_type="BOOK",
                            entity_id=book_id,
                            description=f"Updated book: {book.title}",
                            metadata={
                                "title": book.title,
                                "updated_fields": updated_fields,
                                "author_ids": author_ids,
                                "category_ids": category_ids,
                                "tag_ids": tag_ids,
                            },
                        ),
                    )
                except Exception:
                    # Log but don't fail if logging fails
                    pass

            # Invalidate related caches
            await self._invalidate_related_caches(
                book_id=book_id,
                author_ids=author_ids,
                category_ids=category_ids,
                tag_ids=tag_ids,
            )

            # Track metrics
            self.metrics.track_book_activity("update", str(book_id), "admin")

            # Lấy sách với các mối quan hệ
            updated_book = await self.book_repo.get_by_id(book_id, with_relations=True)

            return self._format_book_response(updated_book)

    @invalidate_cache(
        namespace="books",
        tags=["book_details", "books", "featured_books", "trending_books"],
    )
    async def delete_book(
        self, book_id: int, admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Xóa sách.

        Args:
            book_id: ID của sách
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        with self.metrics.time_request("DELETE", f"/books/{book_id}"):
            # Get book info for logging before deletion
            book = await self.book_repo.get_by_id(book_id, with_relations=True)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Lưu thông tin về mối quan hệ để vô hiệu hóa cache
            author_ids = [author.id for author in book.authors] if book.authors else []
            category_ids = (
                [category.id for category in book.categories] if book.categories else []
            )
            tag_ids = [tag.id for tag in book.tags] if book.tags else []

            success = await self.book_repo.delete(book_id)
            if not success:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Log the book deletion if admin_id is provided
            if admin_id:
                try:
                    await create_admin_activity_log(
                        self.db,
                        AdminActivityLogCreate(
                            admin_id=admin_id,
                            activity_type="DELETE",
                            entity_type="BOOK",
                            entity_id=book_id,
                            description=f"Deleted book: {book.title}",
                            metadata={
                                "title": book.title,
                                "isbn": book.isbn if hasattr(book, "isbn") else None,
                            },
                        ),
                    )
                except Exception:
                    # Log but don't fail if logging fails
                    pass

            # Invalidate related caches
            await self._invalidate_related_caches(
                book_id=book_id,
                author_ids=author_ids,
                category_ids=category_ids,
                tag_ids=tag_ids,
            )

            # Explicitly delete specific cache keys
            await self.cache.delete(f"book:{book_id}")
            if hasattr(book, "isbn") and book.isbn:
                await self.cache.delete(f"book_isbn:{book.isbn}")

            # Track metrics
            self.metrics.track_book_activity("delete", str(book_id), "admin")

            return {"message": "Đã xóa sách thành công"}

    @cache_list(
        ttl=1800,
        namespace="books",
        key_builder=lambda *args, **kwargs: f"books:{kwargs.get('skip')}:{kwargs.get('limit')}:"
        f"{kwargs.get('only_published')}:{kwargs.get('sort_by')}:{kwargs.get('sort_desc')}:"
        f"{kwargs.get('category_id')}:{kwargs.get('author_id')}:{kwargs.get('tag_id')}:"
        f"{kwargs.get('search_query')}",
    )
    async def list_books(
        self,
        skip: int = 0,
        limit: int = 100,
        only_published: bool = True,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        category_id: Optional[int] = None,
        author_id: Optional[int] = None,
        tag_id: Optional[int] = None,
        search_query: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách sách.

        Args:
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            only_published: Chỉ lấy sách đã xuất bản
            sort_by: Sắp xếp theo trường
            sort_desc: Sắp xếp giảm dần
            category_id: Lọc theo danh mục (tùy chọn)
            author_id: Lọc theo tác giả (tùy chọn)
            tag_id: Lọc theo thẻ (tùy chọn)
            search_query: Từ khóa tìm kiếm (tùy chọn)
            user_id: ID người dùng thực hiện tìm kiếm (tùy chọn)

        Returns:
            Danh sách sách và thông tin phân trang
        """
        with self.metrics.time_request("GET", "/books"):
            with self.profiler.profile_time(name="list_books", threshold=0.5):
                books, total = await self.book_repo.list_books(
                    skip=skip,
                    limit=limit,
                    only_published=only_published,
                    sort_by=sort_by,
                    sort_desc=sort_desc,
                    category_id=category_id,
                    author_id=author_id,
                    tag_id=tag_id,
                    search_query=search_query,
                )

                # Log the search if user_id is provided and there's a search query
                if user_id and search_query:
                    try:
                        await create_user_activity_log(
                            self.db,
                            UserActivityLogCreate(
                                user_id=user_id,
                                activity_type="SEARCH",
                                entity_type="BOOKS",
                                entity_id=0,  # No specific entity ID for search
                                description=f"Searched for books: {search_query}",
                                metadata={
                                    "query": search_query,
                                    "category_id": category_id,
                                    "author_id": author_id,
                                    "tag_id": tag_id,
                                    "results_count": total,
                                },
                            ),
                        )

                        # Track search metrics
                        self.metrics.track_search(
                            "book_search",
                            total,
                            metadata={
                                "query": search_query,
                                "has_filters": bool(category_id or author_id or tag_id),
                            },
                        )
                    except Exception:
                        # Log but don't fail if logging fails
                        pass

                return {
                    "items": [self._format_book_list_item(book) for book in books],
                    "total": total,
                    "skip": skip,
                    "limit": limit,
                }

    @cached(
        ttl=1800,
        namespace="books",
        tags=["book_chapters"],
        key_builder=lambda *args, **kwargs: f"book_chapters:{kwargs.get('book_id')}:{kwargs.get('is_published')}",
    )
    async def get_book_chapters(
        self, book_id: int, is_published: Optional[bool] = True
    ) -> Dict[str, Any]:
        """
        Lấy danh sách chương của sách.

        Args:
            book_id: ID của sách
            is_published: Lọc theo trạng thái xuất bản (tùy chọn)

        Returns:
            Danh sách chương

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        with self.profiler.profile_time(name="get_book_chapters"):
            # Kiểm tra sách tồn tại
            book = await self.book_repo.get_by_id(book_id)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            chapters = await self.chapter_repo.list_by_book(book_id, is_published)
            chapter_count = await self.chapter_repo.count_chapters_by_book(
                book_id, is_published
            )

            # Track chapters access
            self.metrics.track_book_activity(
                "view_chapters", str(book_id), "registered"
            )

            return {
                "items": [
                    {
                        "id": chapter.id,
                        "book_id": chapter.book_id,
                        "title": chapter.title,
                        "number": chapter.number,
                        "word_count": chapter.word_count,
                        "view_count": chapter.view_count,
                        "is_published": chapter.is_published,
                        "created_at": chapter.created_at,
                        "updated_at": chapter.updated_at,
                    }
                    for chapter in chapters
                ],
                "total": chapter_count,
            }

    @cached(ttl=3600, namespace="books", tags=["featured_books"])
    async def get_featured_books(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách sách nổi bật.

        Args:
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách sách nổi bật
        """
        with self.profiler.profile_time(name="get_featured_books"):
            books = await self.book_repo.get_featured_books(limit)

            # Track featured books access
            self.metrics.track_user_activity("view_featured_books")

            return [self._format_book_list_item(book) for book in books]

    @cached(ttl=1800, namespace="books", tags=["trending_books"])
    async def get_trending_books(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách sách thịnh hành.

        Args:
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách sách thịnh hành
        """
        with self.profiler.profile_time(name="get_trending_books"):
            books = await self.book_repo.get_trending_books(limit)

            # Track trending books access
            self.metrics.track_user_activity("view_trending_books")

            return [self._format_book_list_item(book) for book in books]

    @cached(
        ttl=3600,
        namespace="books",
        tags=["similar_books"],
        key_builder=lambda *args, **kwargs: f"similar_books:{kwargs.get('book_id')}:{kwargs.get('limit')}",
    )
    async def get_similar_books(
        self, book_id: int, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách sách tương tự.

        Args:
            book_id: ID của sách
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách sách tương tự

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        with self.profiler.profile_time(name="get_similar_books"):
            # Kiểm tra sách tồn tại
            book = await self.book_repo.get_by_id(book_id)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            similar_books = await self.book_repo.get_similar_books(book_id, limit)

            # Track similar books access
            self.metrics.track_book_activity("view_similar", str(book_id), "registered")

            return [self._format_book_list_item(book) for book in similar_books]

    @invalidate_cache(namespace="books", tags=["book_details"])
    async def update_book_rating(self, book_id: int) -> Dict[str, Any]:
        """
        Cập nhật đánh giá của sách dựa trên các đánh giá hiện có.

        Args:
            book_id: ID của sách

        Returns:
            Thông tin đánh giá đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Tính trung bình đánh giá
        avg_rating, review_count = await self.review_repo.get_average_rating_by_book(
            book_id
        )

        # Cập nhật sách
        updated = await self.book_repo.update_rating(book_id, avg_rating, review_count)

        # Invalidate specific caches
        await self.cache.delete(f"book:{book_id}")

        # Track rating update
        self.metrics.track_book_activity(
            "update_rating", str(book_id), user_type="system", rating=int(avg_rating)
        )

        return {
            "book_id": updated.id,
            "avg_rating": updated.avg_rating,
            "review_count": updated.review_count,
        }

    @invalidate_cache(namespace="books", tags=["book_details"])
    async def add_book_authors(
        self, book_id: int, author_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Thêm tác giả cho sách.

        Args:
            book_id: ID của sách
            author_ids: Danh sách ID của tác giả

        Returns:
            Danh sách tác giả đã thêm

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        book = await self.book_repo.add_authors(book_id, author_ids)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy sách với các mối quan hệ
        updated_book = await self.book_repo.get_by_id(book_id, with_relations=True)

        # Invalidate related caches
        await self._invalidate_related_caches(book_id=book_id, author_ids=author_ids)

        return {
            "book_id": book_id,
            "authors": [
                {"id": author.id, "name": author.name, "slug": author.slug}
                for author in updated_book.authors
            ],
        }

    @invalidate_cache(namespace="books", tags=["book_details"])
    async def remove_book_authors(
        self, book_id: int, author_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Xóa tác giả khỏi sách.

        Args:
            book_id: ID của sách
            author_ids: Danh sách ID của tác giả

        Returns:
            Danh sách tác giả còn lại

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        book = await self.book_repo.remove_authors(book_id, author_ids)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy sách với các mối quan hệ
        updated_book = await self.book_repo.get_by_id(book_id, with_relations=True)

        # Invalidate related caches
        await self._invalidate_related_caches(book_id=book_id, author_ids=author_ids)

        return {
            "book_id": book_id,
            "authors": [
                {"id": author.id, "name": author.name, "slug": author.slug}
                for author in updated_book.authors
            ],
        }

    @invalidate_cache(namespace="books", tags=["book_details"])
    async def add_book_categories(
        self, book_id: int, category_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Thêm danh mục cho sách.

        Args:
            book_id: ID của sách
            category_ids: Danh sách ID của danh mục

        Returns:
            Danh sách danh mục đã thêm

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        book = await self.book_repo.add_categories(book_id, category_ids)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy sách với các mối quan hệ
        updated_book = await self.book_repo.get_by_id(book_id, with_relations=True)

        # Invalidate related caches
        await self._invalidate_related_caches(
            book_id=book_id, category_ids=category_ids
        )

        return {
            "book_id": book_id,
            "categories": [
                {"id": category.id, "name": category.name, "slug": category.slug}
                for category in updated_book.categories
            ],
        }

    @invalidate_cache(namespace="books", tags=["book_details"])
    async def remove_book_categories(
        self, book_id: int, category_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Xóa danh mục khỏi sách.

        Args:
            book_id: ID của sách
            category_ids: Danh sách ID của danh mục

        Returns:
            Danh sách danh mục còn lại

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        book = await self.book_repo.remove_categories(book_id, category_ids)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy sách với các mối quan hệ
        updated_book = await self.book_repo.get_by_id(book_id, with_relations=True)

        # Invalidate related caches
        await self._invalidate_related_caches(
            book_id=book_id, category_ids=category_ids
        )

        return {
            "book_id": book_id,
            "categories": [
                {"id": category.id, "name": category.name, "slug": category.slug}
                for category in updated_book.categories
            ],
        }

    @invalidate_cache(namespace="books", tags=["book_details"])
    async def add_book_tags(self, book_id: int, tag_ids: List[int]) -> Dict[str, Any]:
        """
        Thêm thẻ cho sách.

        Args:
            book_id: ID của sách
            tag_ids: Danh sách ID của thẻ

        Returns:
            Danh sách thẻ đã thêm

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        book = await self.book_repo.add_tags(book_id, tag_ids)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy sách với các mối quan hệ
        updated_book = await self.book_repo.get_by_id(book_id, with_relations=True)

        # Invalidate related caches
        await self._invalidate_related_caches(book_id=book_id, tag_ids=tag_ids)

        return {
            "book_id": book_id,
            "tags": [
                {"id": tag.id, "name": tag.name, "slug": tag.slug}
                for tag in updated_book.tags
            ],
        }

    @invalidate_cache(namespace="books", tags=["book_details"])
    async def remove_book_tags(
        self, book_id: int, tag_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Xóa thẻ khỏi sách.

        Args:
            book_id: ID của sách
            tag_ids: Danh sách ID của thẻ

        Returns:
            Danh sách thẻ còn lại

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        book = await self.book_repo.remove_tags(book_id, tag_ids)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy sách với các mối quan hệ
        updated_book = await self.book_repo.get_by_id(book_id, with_relations=True)

        # Invalidate related caches
        await self._invalidate_related_caches(book_id=book_id, tag_ids=tag_ids)

        return {
            "book_id": book_id,
            "tags": [
                {"id": tag.id, "name": tag.name, "slug": tag.slug}
                for tag in updated_book.tags
            ],
        }

    async def _invalidate_related_caches(
        self,
        book_id: int,
        author_ids: Optional[List[int]] = None,
        category_ids: Optional[List[int]] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> None:
        """
        Vô hiệu hóa các cache liên quan đến sách, tác giả, danh mục, và thẻ.

        Args:
            book_id: ID của sách
            author_ids: Danh sách ID của tác giả (tùy chọn)
            category_ids: Danh sách ID của danh mục (tùy chọn)
            tag_ids: Danh sách ID của thẻ (tùy chọn)
        """
        # Vô hiệu hóa cache sách
        tasks = [self.cache.delete(f"book:{book_id}")]

        # Vô hiệu hóa cache chapters
        tasks.append(self.cache.clear(pattern=f"book_chapters:{book_id}:*"))

        # Vô hiệu hóa cache similar books
        tasks.append(self.cache.clear(pattern=f"similar_books:{book_id}:*"))

        # Vô hiệu hóa cache liên quan đến tác giả
        if author_ids:
            for author_id in author_ids:
                # Vô hiệu hóa cache danh sách sách của tác giả
                tasks.append(
                    self.cache.clear(pattern=f"books:*:*:*:*:*:{author_id}:*:*")
                )
                # Vô hiệu hóa cache chi tiết tác giả
                tasks.append(self.cache.delete(f"author:{author_id}"))

        # Vô hiệu hóa cache liên quan đến danh mục
        if category_ids:
            for category_id in category_ids:
                # Vô hiệu hóa cache danh sách sách của danh mục
                tasks.append(
                    self.cache.clear(pattern=f"books:*:*:*:*:*:*:{category_id}:*:*")
                )
                # Vô hiệu hóa cache chi tiết danh mục
                tasks.append(self.cache.delete(f"category:{category_id}"))

        # Vô hiệu hóa cache liên quan đến thẻ
        if tag_ids:
            for tag_id in tag_ids:
                # Vô hiệu hóa cache danh sách sách của thẻ
                tasks.append(
                    self.cache.clear(pattern=f"books:*:*:*:*:*:*:*:{tag_id}:*")
                )
                # Vô hiệu hóa cache chi tiết thẻ
                tasks.append(self.cache.delete(f"tag:{tag_id}"))

        # Vô hiệu hóa cache danh sách
        tasks.append(
            self.cache.invalidate_by_tags(["books", "featured_books", "trending_books"])
        )

        # Thực hiện các task vô hiệu hóa cache
        await asyncio.gather(*tasks)

    def _format_book_response(self, book) -> Dict[str, Any]:
        """
        Định dạng thông tin sách đầy đủ.

        Args:
            book: Đối tượng sách

        Returns:
            Thông tin sách dạng dict
        """
        result = {
            "id": book.id,
            "title": book.title,
            "description": book.description,
            "cover_image": book.cover_image,
            "is_featured": book.is_featured,
            "is_published": book.is_published,
            "published_date": book.published_date,
            "isbn": book.isbn,
            "language": book.language,
            "page_count": book.page_count,
            "word_count": book.word_count,
            "avg_rating": book.avg_rating,
            "review_count": book.review_count,
            "publisher_id": book.publisher_id,
            "slug": book.slug,
            "price": book.price,
            "discount_percent": book.discount_percent,
            "is_free": book.is_free,
            "created_at": book.created_at,
            "updated_at": book.updated_at,
        }

        # Thêm thông tin quan hệ nếu có
        if hasattr(book, "authors") and book.authors:
            result["authors"] = [
                {
                    "id": author.id,
                    "name": author.name,
                    "slug": author.slug,
                    "photo_url": author.photo_url,
                }
                for author in book.authors
            ]

        if hasattr(book, "categories") and book.categories:
            result["categories"] = [
                {"id": category.id, "name": category.name, "slug": category.slug}
                for category in book.categories
            ]

        if hasattr(book, "tags") and book.tags:
            result["tags"] = [
                {"id": tag.id, "name": tag.name, "slug": tag.slug} for tag in book.tags
            ]

        if hasattr(book, "publisher") and book.publisher:
            result["publisher"] = {
                "id": book.publisher.id,
                "name": book.publisher.name,
                "logo_url": book.publisher.logo_url,
            }

        return result

    def _format_book_list_item(self, book) -> Dict[str, Any]:
        """
        Định dạng thông tin sách ngắn gọn cho danh sách.

        Args:
            book: Đối tượng sách

        Returns:
            Thông tin sách dạng dict
        """
        result = {
            "id": book.id,
            "title": book.title,
            "cover_image": book.cover_image,
            "is_featured": book.is_featured,
            "is_published": book.is_published,
            "published_date": book.published_date,
            "language": book.language,
            "avg_rating": book.avg_rating,
            "review_count": book.review_count,
            "slug": book.slug,
            "price": book.price,
            "discount_percent": book.discount_percent,
            "is_free": book.is_free,
        }

        # Thêm thông tin quan hệ nếu có
        if hasattr(book, "authors") and book.authors:
            result["author_names"] = [author.name for author in book.authors]

        if hasattr(book, "categories") and book.categories:
            result["category_names"] = [category.name for category in book.categories]

        return result

    @cached(ttl=1800, namespace="books", tags=["new_releases"])
    async def get_new_releases(
        self, limit: int = 10, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách sách mới xuất bản.

        Args:
            limit: Số lượng bản ghi tối đa trả về
            days: Số ngày gần đây để xem là sách mới

        Returns:
            Danh sách sách mới xuất bản
        """
        with self.profiler.profile_time(name="get_new_releases"):
            books = await self.book_repo.get_new_releases(days, limit)

            # Track new releases access
            self.metrics.track_user_activity("view_new_releases")

            return [self._format_book_list_item(book) for book in books]

    @cached(ttl=86400, namespace="books", tags=["book_stats"])
    async def get_book_stats(self, book_id: int) -> Dict[str, Any]:
        """
        Lấy thống kê về sách.

        Args:
            book_id: ID của sách

        Returns:
            Thống kê sách

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy các thống kê song song
        chapter_count, review_count, rating_stats = await asyncio.gather(
            self.chapter_repo.count_chapters_by_book(book_id, True),
            self.review_repo.count_by_book(book_id),
            self.review_repo.get_rating_stats(book_id),
        )

        # Track stats access
        self.metrics.track_book_activity("view_stats", str(book_id), "registered")

        return {
            "book_id": book_id,
            "title": book.title,
            "chapter_count": chapter_count,
            "review_count": review_count,
            "avg_rating": book.avg_rating,
            "rating_distribution": rating_stats,
            "word_count": book.word_count,
            "page_count": book.page_count,
            "published_date": book.published_date,
        }

    @invalidate_cache(namespace="books", tags=["book_details", "book_stats"])
    async def increment_view_count(
        self, book_id: int, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Tăng lượt xem cho sách.

        Args:
            book_id: ID của sách
            user_id: ID người dùng xem sách (tùy chọn)

        Returns:
            Thông tin lượt xem

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Tăng lượt xem
        updated = await self.book_repo.increment_view_count(book_id)

        # Log activity nếu có user_id
        if user_id:
            try:
                await create_user_activity_log(
                    self.db,
                    UserActivityLogCreate(
                        user_id=user_id,
                        activity_type="VIEW",
                        entity_type="BOOK",
                        entity_id=book_id,
                        description=f"Viewed book: {book.title}",
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        # Track metrics
        self.metrics.track_book_activity(
            "view", str(book_id), "registered" if user_id else "anonymous"
        )

        return {"book_id": book_id, "view_count": updated.view_count}

    async def _get_user_book_interaction(
        self, user_id: int, book_id: int
    ) -> Dict[str, Any]:
        """
        Lấy thông tin tương tác của người dùng với sách.

        Args:
            user_id: ID người dùng
            book_id: ID sách

        Returns:
            Dict chứa thông tin tương tác
        """
        # Lấy đánh giá của người dùng cho sách
        user_rating = await self.rating_repo.get_by_user_and_book(user_id, book_id)

        # Kiểm tra sách có trong kệ sách nào của người dùng không
        bookshelves = await self.bookshelf_repo.list_bookshelves_containing_book(
            user_id, book_id
        )

        # Lấy tiến độ đọc
        reading_history = await self.reading_history_repo.get_by_user_and_book(
            user_id, book_id
        )

        result = {
            "has_rated": user_rating is not None,
            "rating": user_rating.rating if user_rating else None,
            "review": user_rating.review if user_rating else None,
            "bookshelves": (
                [{"id": shelf.id, "name": shelf.name} for shelf in bookshelves]
                if bookshelves
                else []
            ),
            "reading_progress": None,
        }

        # Thêm thông tin tiến độ đọc nếu có
        if reading_history:
            if (
                hasattr(reading_history, "last_chapter")
                and reading_history.last_chapter
            ):
                result["reading_progress"] = {
                    "last_read_at": reading_history.updated_at,
                    "chapter": (
                        {
                            "id": reading_history.last_chapter.id,
                            "title": reading_history.last_chapter.title,
                            "number": reading_history.last_chapter.number,
                        }
                        if reading_history.last_chapter
                        else None
                    ),
                }

        return result
