from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.author_repo import AuthorRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
)
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache
from app.cache.keys import CacheKeyBuilder
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import check_permission
from app.logs_manager.services.admin_activity_log_service import AdminActivityLogService
from app.core.config import get_settings

settings = get_settings()


class AuthorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.author_repo = AuthorRepository(db)
        self.book_repo = BookRepository(db)
        self.metrics = Metrics()
        self.admin_log_service = AdminActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time(threshold=0.5)
    @invalidate_cache(namespace="authors", tags=["author_details", "author_list"])
    async def create_author(
        self, data: Dict[str, Any], admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Tạo tác giả mới.

        Args:
            data: Thông tin tác giả
            admin_id: ID của admin tạo (nếu có)

        Returns:
            Thông tin tác giả đã tạo

        Raises:
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra dữ liệu
        if not data.get("name"):
            raise BadRequestException("Tên tác giả không được để trống")

        # Làm sạch dữ liệu
        if "bio" in data and data["bio"]:
            data["bio"] = sanitize_html(data["bio"])

        if "website" in data and data["website"]:
            if not data["website"].startswith(("http://", "https://")):
                data["website"] = f"https://{data['website']}"

        # Kiểm tra trùng lặp
        existing = await self.author_repo.get_by_name(data["name"])
        if existing:
            raise BadRequestException(f"Tác giả '{data['name']}' đã tồn tại")

        # Tạo slug nếu chưa có
        if not data.get("slug"):
            from slugify import slugify

            data["slug"] = slugify(data["name"])

            # Kiểm tra slug đã tồn tại chưa
            existing_slug = await self.author_repo.get_by_slug(data["slug"])
            if existing_slug:
                data["slug"] = f"{data['slug']}-{str(datetime.now().timestamp())[:10]}"

        # Tạo tác giả
        author = await self.author_repo.create(data)

        # Ghi log hoạt động nếu là admin
        if admin_id:
            await self.admin_log_service.log_activity(
                self.db,
                admin_id=admin_id,
                activity_type="CREATE",
                action="create_author",
                resource_type="author",
                resource_id=str(author["id"]),
                details={"author_name": author["name"]},
            )

        # Metrics
        self.metrics.track_user_activity(
            "create_author", "admin" if admin_id else "system"
        )

        return author

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="authors", tags=["author_details"])
    async def get_author(self, author_id: int) -> Dict[str, Any]:
        """Lấy thông tin tác giả theo ID.

        Args:
            author_id: ID của tác giả

        Returns:
            Thông tin tác giả

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả
        """
        author = await self.author_repo.get(author_id)
        if not author:
            raise NotFoundException(f"Không tìm thấy tác giả với ID {author_id}")

        # Lấy số lượng sách
        book_count = await self.book_repo.count_by_author(author_id)
        author["book_count"] = book_count

        return author

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="authors", tags=["author_details"])
    async def get_author_by_slug(self, slug: str) -> Dict[str, Any]:
        """Lấy thông tin tác giả theo slug.

        Args:
            slug: Slug của tác giả

        Returns:
            Thông tin tác giả

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả
        """
        author = await self.author_repo.get_by_slug(slug)
        if not author:
            raise NotFoundException(f"Không tìm thấy tác giả với slug {slug}")

        # Lấy số lượng sách
        book_count = await self.book_repo.count_by_author(author["id"])
        author["book_count"] = book_count

        return author

    @CodeProfiler.profile_time(threshold=0.5)
    @invalidate_cache(namespace="authors", tags=["author_details", "author_list"])
    async def update_author(
        self, author_id: int, data: Dict[str, Any], admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Cập nhật thông tin tác giả.

        Args:
            author_id: ID của tác giả
            data: Thông tin cập nhật
            admin_id: ID của admin thực hiện (nếu có)

        Returns:
            Thông tin tác giả đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra tác giả tồn tại
        author = await self.author_repo.get(author_id)
        if not author:
            raise NotFoundException(f"Không tìm thấy tác giả với ID {author_id}")

        # Lưu trạng thái trước khi cập nhật
        before_state = dict(author)

        # Làm sạch dữ liệu
        if "bio" in data and data["bio"]:
            data["bio"] = sanitize_html(data["bio"])

        if "website" in data and data["website"]:
            if not data["website"].startswith(("http://", "https://")):
                data["website"] = f"https://{data['website']}"

        # Cập nhật slug nếu có thay đổi tên
        if "name" in data and data["name"] != author["name"]:
            if not data.get("slug"):
                from slugify import slugify

                data["slug"] = slugify(data["name"])

                # Kiểm tra slug đã tồn tại chưa
                existing_slug = await self.author_repo.get_by_slug(data["slug"])
                if existing_slug and existing_slug["id"] != author_id:
                    data["slug"] = (
                        f"{data['slug']}-{str(datetime.now().timestamp())[:10]}"
                    )

        # Cập nhật
        updated_author = await self.author_repo.update(author_id, data)

        # Ghi log hoạt động nếu là admin
        if admin_id:
            await self.admin_log_service.log_activity(
                self.db,
                admin_id=admin_id,
                activity_type="UPDATE",
                action="update_author",
                resource_type="author",
                resource_id=str(author_id),
                before_state=before_state,
                after_state=dict(updated_author),
                details={"author_name": updated_author["name"]},
            )

        # Metrics
        self.metrics.track_user_activity(
            "update_author", "admin" if admin_id else "system"
        )

        return updated_author

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="authors", tags=["author_details", "author_list"])
    async def delete_author(
        self, author_id: int, admin_id: Optional[int] = None
    ) -> bool:
        """Xóa tác giả.

        Args:
            author_id: ID của tác giả
            admin_id: ID của admin thực hiện (nếu có)

        Returns:
            True nếu xóa thành công

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả
            ForbiddenException: Nếu tác giả có sách liên kết
        """
        # Kiểm tra tác giả tồn tại
        author = await self.author_repo.get(author_id)
        if not author:
            raise NotFoundException(f"Không tìm thấy tác giả với ID {author_id}")

        # Kiểm tra tác giả có sách không
        book_count = await self.book_repo.count_by_author(author_id)
        if book_count > 0:
            raise ForbiddenException(
                f"Không thể xóa tác giả '{author['name']}' vì có {book_count} sách liên kết"
            )

        # Xóa tác giả
        result = await self.author_repo.delete(author_id)

        # Ghi log hoạt động nếu là admin
        if result and admin_id:
            await self.admin_log_service.log_activity(
                self.db,
                admin_id=admin_id,
                activity_type="DELETE",
                action="delete_author",
                resource_type="author",
                resource_id=str(author_id),
                before_state=dict(author),
                details={"author_name": author["name"]},
            )

        # Metrics
        self.metrics.track_user_activity(
            "delete_author", "admin" if admin_id else "system"
        )

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="authors", tags=["author_list"])
    async def list_authors(
        self, skip: int = 0, limit: int = 100, search: Optional[str] = None
    ) -> Dict[str, Any]:
        """Lấy danh sách tác giả.

        Args:
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi lấy
            search: Từ khóa tìm kiếm

        Returns:
            Danh sách tác giả và tổng số lượng
        """
        filters = {}
        if search:
            filters["search"] = search

        # Lấy danh sách
        authors = await self.author_repo.get_multi(skip=skip, limit=limit, **filters)

        # Lấy tổng số lượng
        total = await self.author_repo.count(**filters)

        # Lấy số lượng sách cho mỗi tác giả
        for author in authors:
            book_count = await self.book_repo.count_by_author(author["id"])
            author["book_count"] = book_count

        return {"items": authors, "total": total, "skip": skip, "limit": limit}

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="authors", tags=["author_books"])
    async def get_author_books(
        self,
        author_id: int,
        skip: int = 0,
        limit: int = 20,
        only_published: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách sách của tác giả.

        Args:
            author_id: ID của tác giả
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi lấy
            only_published: Chỉ lấy sách đã xuất bản

        Returns:
            Danh sách sách và tổng số lượng

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả
        """
        # Kiểm tra tác giả tồn tại
        author = await self.author_repo.get(author_id)
        if not author:
            raise NotFoundException(f"Không tìm thấy tác giả với ID {author_id}")

        # Lấy danh sách sách
        filters = {"author_id": author_id}
        if only_published:
            filters["status"] = "published"

        books = await self.book_repo.get_multi(skip=skip, limit=limit, **filters)

        # Lấy tổng số lượng
        total = await self.book_repo.count(**filters)

        return {
            "items": books,
            "total": total,
            "author": author,
            "skip": skip,
            "limit": limit,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="authors", tags=["featured_authors"])
    async def get_featured_authors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lấy danh sách tác giả nổi bật.

        Args:
            limit: Số lượng tác giả lấy

        Returns:
            Danh sách tác giả nổi bật
        """
        # Lấy danh sách tác giả có nhiều sách nhất
        featured_authors = await self.author_repo.get_featured(limit=limit)

        for author in featured_authors:
            book_count = await self.book_repo.count_by_author(author["id"])
            author["book_count"] = book_count

        return featured_authors

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="authors", tags=["popular_authors"])
    async def get_popular_authors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lấy danh sách tác giả phổ biến.

        Args:
            limit: Số lượng tác giả lấy

        Returns:
            Danh sách tác giả phổ biến dựa trên số lượt đọc
        """
        # Lấy danh sách tác giả có sách được đọc nhiều nhất
        popular_authors = await self.author_repo.get_popular(limit=limit)

        for author in popular_authors:
            book_count = await self.book_repo.count_by_author(author["id"])
            author["book_count"] = book_count

        return popular_authors

    @CodeProfiler.profile_time()
    async def search_authors(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Tìm kiếm tác giả.

        Args:
            query: Từ khóa tìm kiếm
            limit: Số lượng kết quả trả về

        Returns:
            Danh sách tác giả phù hợp
        """
        if not query or len(query) < 2:
            return []

        authors = await self.author_repo.search(query, limit=limit)

        for author in authors:
            book_count = await self.book_repo.count_by_author(author["id"])
            author["book_count"] = book_count

        return authors

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="authors", tags=["author_details"])
    async def update_book_count(self, author_id: int) -> Dict[str, Any]:
        """Cập nhật số lượng sách của tác giả.

        Args:
            author_id: ID của tác giả

        Returns:
            Thông tin tác giả đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả
        """
        # Kiểm tra tác giả tồn tại
        author = await self.author_repo.get(author_id)
        if not author:
            raise NotFoundException(f"Không tìm thấy tác giả với ID {author_id}")

        # Lấy số lượng sách
        book_count = await self.book_repo.count_by_author(author_id)

        # Cập nhật
        updated_author = await self.author_repo.update(
            author_id, {"book_count": book_count}
        )

        return updated_author

    @CodeProfiler.profile_time()
    async def get_or_create_author(self, name: str, **kwargs) -> Dict[str, Any]:
        """Lấy hoặc tạo tác giả.

        Args:
            name: Tên tác giả
            **kwargs: Thông tin bổ sung

        Returns:
            Thông tin tác giả
        """
        # Kiểm tra tác giả đã tồn tại
        author = await self.author_repo.get_by_name(name)

        if author:
            return author

        # Tạo tác giả mới
        data = {"name": name, **kwargs}

        # Tạo slug nếu chưa có
        if not data.get("slug"):
            from slugify import slugify

            data["slug"] = slugify(name)

            # Kiểm tra slug đã tồn tại chưa
            existing_slug = await self.author_repo.get_by_slug(data["slug"])
            if existing_slug:
                data["slug"] = f"{data['slug']}-{str(datetime.now().timestamp())[:10]}"

        return await self.author_repo.create(data)
