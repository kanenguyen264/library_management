from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import re
import uuid

from app.cache.decorators import cached
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.author_repo import AuthorRepository
from app.user_site.repositories.publisher_repo import PublisherRepository
from app.user_site.repositories.category_repo import CategoryRepository
from app.user_site.repositories.tag_repo import TagRepository
from app.user_site.repositories.user_repo import UserRepository
from app.logs_manager.services import create_search_log
from app.logs_manager.schemas.search_log import SearchLogCreate
from app.core.exceptions import ValidationException
from app.monitoring.metrics.business_metrics import track_search
from app.logging.setup import get_logger

logger = get_logger(__name__)


class SearchService:
    def __init__(self, db: AsyncSession):
        """
        Khởi tạo dịch vụ tìm kiếm

        Args:
            db: Phiên làm việc cơ sở dữ liệu không đồng bộ
        """
        self.db = db
        self.book_repo = BookRepository(db)
        self.author_repo = AuthorRepository(db)
        self.publisher_repo = PublisherRepository(db)
        self.category_repo = CategoryRepository(db)
        self.tag_repo = TagRepository(db)
        self.user_repo = UserRepository(db)

    @cached(ttl=1800, namespace="search", key_prefix="books", tags=["search", "books"])
    async def search_books(
        self,
        query: str,
        category_id: Optional[int] = None,
        author_id: Optional[int] = None,
        publisher_id: Optional[int] = None,
        min_rating: Optional[float] = None,
        max_rating: Optional[float] = None,
        tag_ids: Optional[List[int]] = None,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Tìm kiếm sách theo các tiêu chí

        Args:
            query: Từ khóa tìm kiếm
            category_id: Lọc theo thể loại
            author_id: Lọc theo tác giả
            publisher_id: Lọc theo nhà xuất bản
            min_rating: Điểm đánh giá tối thiểu
            max_rating: Điểm đánh giá tối đa
            tag_ids: Danh sách ID tag
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            user_id: ID người dùng (để ghi log)
            session_id: ID phiên (để ghi log)

        Returns:
            Dict chứa kết quả tìm kiếm
        """
        # Kiểm tra query
        if not query or len(query.strip()) < 2:
            raise ValidationException("Từ khóa tìm kiếm phải có ít nhất 2 ký tự")

        # Chuẩn hóa query
        normalized_query = self._normalize_query(query)

        # Tìm kiếm sách
        start_time = datetime.now()
        results = await self.book_repo.search(
            query=normalized_query,
            category_id=category_id,
            author_id=author_id,
            publisher_id=publisher_id,
            min_rating=min_rating,
            max_rating=max_rating,
            tag_ids=tag_ids,
            skip=skip,
            limit=limit,
            with_relations=["authors", "categories"],
        )

        # Đếm tổng số kết quả để phân trang
        total_count = await self.book_repo.count_search_results(
            query=normalized_query,
            category_id=category_id,
            author_id=author_id,
            publisher_id=publisher_id,
            min_rating=min_rating,
            max_rating=max_rating,
            tag_ids=tag_ids,
        )

        # Tính thời gian tìm kiếm
        search_duration = (
            datetime.now() - start_time
        ).total_seconds() * 1000  # Convert to milliseconds

        # Format kết quả
        formatted_results = []
        for book in results:
            book_data = {
                "id": book.id,
                "title": book.title,
                "cover_image_url": book.cover_image_url,
                "cover_thumbnail_url": book.cover_thumbnail_url,
                "avg_rating": book.avg_rating,
                "review_count": book.review_count,
                "publication_date": book.publication_date,
            }

            # Thêm thông tin tác giả
            if hasattr(book, "authors") and book.authors:
                book_data["authors"] = [
                    {"id": author.id, "name": author.name} for author in book.authors
                ]

            # Thêm thông tin thể loại
            if hasattr(book, "categories") and book.categories:
                book_data["categories"] = [
                    {"id": category.id, "name": category.name}
                    for category in book.categories
                ]

            formatted_results.append(book_data)

        # Ghi log tìm kiếm
        if user_id or session_id:
            await self._log_search(
                query=query,
                category="books",
                results_count=total_count,
                search_duration=search_duration,
                user_id=user_id,
                session_id=session_id,
                filters={
                    "category_id": category_id,
                    "author_id": author_id,
                    "publisher_id": publisher_id,
                    "min_rating": min_rating,
                    "max_rating": max_rating,
                    "tag_ids": tag_ids,
                },
            )

        # Theo dõi số liệu
        track_search("books", total_count, search_duration)

        return {
            "items": formatted_results,
            "total": total_count,
            "page": skip // limit + 1,
            "size": limit,
            "query": query,
            "search_time_ms": round(search_duration, 2),
        }

    @cached(
        ttl=1800, namespace="search", key_prefix="authors", tags=["search", "authors"]
    )
    async def search_authors(
        self,
        query: str,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Tìm kiếm tác giả theo tên

        Args:
            query: Từ khóa tìm kiếm
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            user_id: ID người dùng (để ghi log)
            session_id: ID phiên (để ghi log)

        Returns:
            Dict chứa kết quả tìm kiếm
        """
        # Kiểm tra query
        if not query or len(query.strip()) < 2:
            raise ValidationException("Từ khóa tìm kiếm phải có ít nhất 2 ký tự")

        # Chuẩn hóa query
        normalized_query = self._normalize_query(query)

        # Tìm kiếm tác giả
        start_time = datetime.now()
        results = await self.author_repo.search(
            query=normalized_query, skip=skip, limit=limit
        )

        # Đếm tổng số kết quả để phân trang
        total_count = await self.author_repo.count_search_results(
            query=normalized_query
        )

        # Tính thời gian tìm kiếm
        search_duration = (
            datetime.now() - start_time
        ).total_seconds() * 1000  # Convert to milliseconds

        # Format kết quả
        formatted_results = []
        for author in results:
            author_data = {
                "id": author.id,
                "name": author.name,
                "bio": author.bio,
                "avatar_url": author.avatar_url,
                "books_count": getattr(author, "books_count", 0),
            }
            formatted_results.append(author_data)

        # Ghi log tìm kiếm
        if user_id or session_id:
            await self._log_search(
                query=query,
                category="authors",
                results_count=total_count,
                search_duration=search_duration,
                user_id=user_id,
                session_id=session_id,
            )

        # Theo dõi số liệu
        track_search("authors", total_count, search_duration)

        return {
            "items": formatted_results,
            "total": total_count,
            "page": skip // limit + 1,
            "size": limit,
            "query": query,
            "search_time_ms": round(search_duration, 2),
        }

    @cached(
        ttl=7200,
        namespace="search",
        key_prefix="categories",
        tags=["search", "categories"],
    )
    async def search_categories(
        self, query: str, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Tìm kiếm thể loại

        Args:
            query: Từ khóa tìm kiếm
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa

        Returns:
            Dict chứa kết quả tìm kiếm
        """
        # Kiểm tra query
        if not query or len(query.strip()) < 2:
            raise ValidationException("Từ khóa tìm kiếm phải có ít nhất 2 ký tự")

        # Chuẩn hóa query
        normalized_query = self._normalize_query(query)

        # Tìm kiếm thể loại
        start_time = datetime.now()
        results = await self.category_repo.search(
            query=normalized_query, skip=skip, limit=limit
        )

        # Đếm tổng số kết quả để phân trang
        total_count = await self.category_repo.count_search_results(
            query=normalized_query
        )

        # Tính thời gian tìm kiếm
        search_duration = (
            datetime.now() - start_time
        ).total_seconds() * 1000  # Convert to milliseconds

        # Format kết quả
        formatted_results = []
        for category in results:
            category_data = {
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "books_count": getattr(category, "books_count", 0),
            }
            formatted_results.append(category_data)

        # Theo dõi số liệu
        track_search("categories", total_count, search_duration)

        return {
            "items": formatted_results,
            "total": total_count,
            "page": skip // limit + 1,
            "size": limit,
            "query": query,
            "search_time_ms": round(search_duration, 2),
        }

    @cached(ttl=7200, namespace="search", key_prefix="tags", tags=["search", "tags"])
    async def search_tags(
        self, query: str, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Tìm kiếm tag

        Args:
            query: Từ khóa tìm kiếm
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa

        Returns:
            Dict chứa kết quả tìm kiếm
        """
        # Kiểm tra query
        if not query or len(query.strip()) < 2:
            raise ValidationException("Từ khóa tìm kiếm phải có ít nhất 2 ký tự")

        # Chuẩn hóa query
        normalized_query = self._normalize_query(query)

        # Tìm kiếm tag
        start_time = datetime.now()
        results = await self.tag_repo.search(
            query=normalized_query, skip=skip, limit=limit
        )

        # Đếm tổng số kết quả để phân trang
        total_count = await self.tag_repo.count_search_results(query=normalized_query)

        # Tính thời gian tìm kiếm
        search_duration = (
            datetime.now() - start_time
        ).total_seconds() * 1000  # Convert to milliseconds

        # Format kết quả
        formatted_results = []
        for tag in results:
            tag_data = {
                "id": tag.id,
                "name": tag.name,
                "slug": tag.slug,
                "color": tag.color,
                "books_count": getattr(tag, "books_count", 0),
            }
            formatted_results.append(tag_data)

        # Theo dõi số liệu
        track_search("tags", total_count, search_duration)

        return {
            "items": formatted_results,
            "total": total_count,
            "page": skip // limit + 1,
            "size": limit,
            "query": query,
            "search_time_ms": round(search_duration, 2),
        }

    @cached(
        ttl=7200,
        namespace="search",
        key_prefix="publishers",
        tags=["search", "publishers"],
    )
    async def search_publishers(
        self, query: str, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Tìm kiếm nhà xuất bản

        Args:
            query: Từ khóa tìm kiếm
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa

        Returns:
            Dict chứa kết quả tìm kiếm
        """
        # Kiểm tra query
        if not query or len(query.strip()) < 2:
            raise ValidationException("Từ khóa tìm kiếm phải có ít nhất 2 ký tự")

        # Chuẩn hóa query
        normalized_query = self._normalize_query(query)

        # Tìm kiếm nhà xuất bản
        start_time = datetime.now()
        results = await self.publisher_repo.search(
            query=normalized_query, skip=skip, limit=limit
        )

        # Đếm tổng số kết quả để phân trang
        total_count = await self.publisher_repo.count_search_results(
            query=normalized_query
        )

        # Tính thời gian tìm kiếm
        search_duration = (
            datetime.now() - start_time
        ).total_seconds() * 1000  # Convert to milliseconds

        # Format kết quả
        formatted_results = []
        for publisher in results:
            publisher_data = {
                "id": publisher.id,
                "name": publisher.name,
                "description": publisher.description,
                "website": publisher.website,
                "logo_url": publisher.logo_url,
                "books_count": getattr(publisher, "books_count", 0),
            }
            formatted_results.append(publisher_data)

        # Theo dõi số liệu
        track_search("publishers", total_count, search_duration)

        return {
            "items": formatted_results,
            "total": total_count,
            "page": skip // limit + 1,
            "size": limit,
            "query": query,
            "search_time_ms": round(search_duration, 2),
        }

    @cached(ttl=3600, namespace="search", key_prefix="users", tags=["search", "users"])
    async def search_users(
        self, query: str, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Tìm kiếm người dùng

        Args:
            query: Từ khóa tìm kiếm
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa

        Returns:
            Dict chứa kết quả tìm kiếm
        """
        # Kiểm tra query
        if not query or len(query.strip()) < 2:
            raise ValidationException("Từ khóa tìm kiếm phải có ít nhất 2 ký tự")

        # Chuẩn hóa query
        normalized_query = self._normalize_query(query)

        # Tìm kiếm người dùng
        start_time = datetime.now()
        results = await self.user_repo.search(
            query=normalized_query, skip=skip, limit=limit
        )

        # Đếm tổng số kết quả để phân trang
        total_count = await self.user_repo.count_search_results(query=normalized_query)

        # Tính thời gian tìm kiếm
        search_duration = (
            datetime.now() - start_time
        ).total_seconds() * 1000  # Convert to milliseconds

        # Format kết quả (chỉ trả về thông tin công khai)
        formatted_results = []
        for user in results:
            user_data = {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url,
                "bio": user.bio,
            }
            formatted_results.append(user_data)

        # Theo dõi số liệu
        track_search("users", total_count, search_duration)

        return {
            "items": formatted_results,
            "total": total_count,
            "page": skip // limit + 1,
            "size": limit,
            "query": query,
            "search_time_ms": round(search_duration, 2),
        }

    @cached(ttl=1800, namespace="search", key_prefix="all", tags=["search"])
    async def search_all(
        self,
        query: str,
        limit: int = 10,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Tìm kiếm tổng hợp trên tất cả các loại dữ liệu

        Args:
            query: Từ khóa tìm kiếm
            limit: Số lượng kết quả tối đa cho mỗi loại
            user_id: ID người dùng (để ghi log)
            session_id: ID phiên (để ghi log)

        Returns:
            Dict chứa kết quả tìm kiếm tổng hợp
        """
        # Kiểm tra query
        if not query or len(query.strip()) < 2:
            raise ValidationException("Từ khóa tìm kiếm phải có ít nhất 2 ký tự")

        # Chuẩn hóa query
        normalized_query = self._normalize_query(query)

        # Tìm kiếm đồng thời trên tất cả các loại dữ liệu
        start_time = datetime.now()

        # Tìm kiếm sách
        books_results = await self.book_repo.search(
            query=normalized_query,
            limit=limit,
            with_relations=["authors", "categories"],
        )

        # Tìm kiếm tác giả
        authors_results = await self.author_repo.search(
            query=normalized_query, limit=limit
        )

        # Tìm kiếm thể loại
        categories_results = await self.category_repo.search(
            query=normalized_query, limit=limit
        )

        # Tìm kiếm tag
        tags_results = await self.tag_repo.search(query=normalized_query, limit=limit)

        # Tìm kiếm nhà xuất bản
        publishers_results = await self.publisher_repo.search(
            query=normalized_query, limit=limit
        )

        # Tìm kiếm người dùng
        users_results = await self.user_repo.search(query=normalized_query, limit=limit)

        # Tính thời gian tìm kiếm
        search_duration = (
            datetime.now() - start_time
        ).total_seconds() * 1000  # Convert to milliseconds

        # Format kết quả
        # Sách
        formatted_books = []
        for book in books_results:
            book_data = {
                "id": book.id,
                "title": book.title,
                "cover_thumbnail_url": book.cover_thumbnail_url,
            }

            # Thêm thông tin tác giả
            if hasattr(book, "authors") and book.authors:
                book_data["authors"] = [
                    {"id": author.id, "name": author.name} for author in book.authors
                ]

            formatted_books.append(book_data)

        # Tác giả
        formatted_authors = []
        for author in authors_results:
            author_data = {
                "id": author.id,
                "name": author.name,
                "avatar_url": author.avatar_url,
            }
            formatted_authors.append(author_data)

        # Thể loại
        formatted_categories = []
        for category in categories_results:
            category_data = {
                "id": category.id,
                "name": category.name,
            }
            formatted_categories.append(category_data)

        # Tag
        formatted_tags = []
        for tag in tags_results:
            tag_data = {
                "id": tag.id,
                "name": tag.name,
                "color": tag.color,
            }
            formatted_tags.append(tag_data)

        # Nhà xuất bản
        formatted_publishers = []
        for publisher in publishers_results:
            publisher_data = {
                "id": publisher.id,
                "name": publisher.name,
                "logo_url": publisher.logo_url,
            }
            formatted_publishers.append(publisher_data)

        # Người dùng
        formatted_users = []
        for user in users_results:
            user_data = {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url,
            }
            formatted_users.append(user_data)

        # Đếm tổng số kết quả
        total_count = (
            len(books_results)
            + len(authors_results)
            + len(categories_results)
            + len(tags_results)
            + len(publishers_results)
            + len(users_results)
        )

        # Ghi log tìm kiếm
        if user_id or session_id:
            await self._log_search(
                query=query,
                category="all",
                results_count=total_count,
                search_duration=search_duration,
                user_id=user_id,
                session_id=session_id,
            )

        # Theo dõi số liệu
        track_search("all", total_count, search_duration)

        return {
            "books": formatted_books,
            "authors": formatted_authors,
            "categories": formatted_categories,
            "tags": formatted_tags,
            "publishers": formatted_publishers,
            "users": formatted_users,
            "total_items": total_count,
            "query": query,
            "search_time_ms": round(search_duration, 2),
        }

    @cached(ttl=1800, namespace="search", key_prefix="suggestions", tags=["search"])
    async def get_search_suggestions(
        self, query: str, limit: int = 10
    ) -> Dict[str, Any]:
        """
        Lấy gợi ý tìm kiếm dựa trên từ khóa

        Args:
            query: Từ khóa tìm kiếm
            limit: Số lượng gợi ý tối đa

        Returns:
            Dict chứa danh sách gợi ý
        """
        # Kiểm tra query
        if not query or len(query.strip()) < 2:
            raise ValidationException("Từ khóa tìm kiếm phải có ít nhất 2 ký tự")

        # Chuẩn hóa query
        normalized_query = self._normalize_query(query)

        # Lấy gợi ý từ sách (tiêu đề)
        books_suggestions = await self.book_repo.get_title_suggestions(
            query=normalized_query, limit=limit
        )

        # Lấy gợi ý từ tác giả (tên)
        authors_suggestions = await self.author_repo.get_name_suggestions(
            query=normalized_query, limit=limit // 2
        )

        # Lấy gợi ý từ thể loại
        categories_suggestions = await self.category_repo.get_name_suggestions(
            query=normalized_query, limit=limit // 2
        )

        # Lấy gợi ý từ tag
        tags_suggestions = await self.tag_repo.get_name_suggestions(
            query=normalized_query, limit=limit // 2
        )

        # Kết hợp và loại bỏ trùng lặp
        all_suggestions = []

        # Thêm tiêu đề sách
        for title in books_suggestions:
            all_suggestions.append({"text": title, "type": "book"})

        # Thêm tên tác giả
        for name in authors_suggestions:
            all_suggestions.append({"text": name, "type": "author"})

        # Thêm tên thể loại
        for name in categories_suggestions:
            all_suggestions.append({"text": name, "type": "category"})

        # Thêm tên tag
        for name in tags_suggestions:
            all_suggestions.append({"text": name, "type": "tag"})

        # Giới hạn số lượng
        all_suggestions = all_suggestions[:limit]

        return {"suggestions": all_suggestions, "query": query}

    async def get_advanced_search_filters(self) -> Dict[str, Any]:
        """
        Lấy các bộ lọc cho tìm kiếm nâng cao

        Returns:
            Dict chứa các bộ lọc
        """
        # Lấy danh sách thể loại
        categories = await self.category_repo.list_all()

        # Lấy danh sách tác giả (chỉ lấy các tác giả phổ biến)
        popular_authors = await self.author_repo.find_popular_authors(limit=20)

        # Lấy danh sách nhà xuất bản (chỉ lấy các nhà xuất bản phổ biến)
        popular_publishers = await self.publisher_repo.find_popular_publishers(limit=20)

        # Lấy danh sách tag phổ biến
        popular_tags = await self.tag_repo.find_popular_tags(limit=50)

        # Format kết quả
        result = {
            "categories": [
                {"id": category.id, "name": category.name} for category in categories
            ],
            "authors": [
                {"id": author.id, "name": author.name} for author in popular_authors
            ],
            "publishers": [
                {"id": publisher.id, "name": publisher.name}
                for publisher in popular_publishers
            ],
            "tags": [{"id": tag.id, "name": tag.name} for tag in popular_tags],
            "ratings": [
                {"value": 5, "label": "5 sao"},
                {"value": 4, "label": "4 sao trở lên"},
                {"value": 3, "label": "3 sao trở lên"},
                {"value": 2, "label": "2 sao trở lên"},
                {"value": 1, "label": "1 sao trở lên"},
            ],
        }

        return result

    # --- Helper methods --- #

    def _normalize_query(self, query: str) -> str:
        """
        Chuẩn hóa query để tìm kiếm

        Args:
            query: Từ khóa tìm kiếm

        Returns:
            Query đã chuẩn hóa
        """
        if not query:
            return ""

        # Loại bỏ khoảng trắng thừa
        normalized = query.strip()

        # Loại bỏ các ký tự đặc biệt không cần thiết
        normalized = re.sub(r"[^\w\s]", " ", normalized)

        # Thay thế nhiều khoảng trắng bằng một khoảng trắng
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized

    async def _log_search(
        self,
        query: str,
        category: str,
        results_count: int,
        search_duration: float,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Ghi log tìm kiếm

        Args:
            query: Từ khóa tìm kiếm
            category: Loại tìm kiếm
            results_count: Số lượng kết quả
            search_duration: Thời gian tìm kiếm (ms)
            user_id: ID người dùng
            session_id: ID phiên
            filters: Bộ lọc tìm kiếm
        """
        try:
            # Đảm bảo có session_id
            if not session_id:
                session_id = str(uuid.uuid4())

            # Tạo log
            log_data = SearchLogCreate(
                query=query,
                category=category,
                results_count=results_count,
                user_id=user_id,
                session_id=session_id,
                filters=filters,
                search_duration=search_duration,
            )

            # Lưu log vào cơ sở dữ liệu
            await create_search_log(self.db, log_data)
        except Exception as e:
            logger.error(f"Lỗi khi ghi log tìm kiếm: {str(e)}")
