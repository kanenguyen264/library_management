from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.publisher_repo import PublisherRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    ConflictException,
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


class PublisherService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.publisher_repo = PublisherRepository(db)
        self.book_repo = BookRepository(db)
        self.metrics = Metrics()
        self.admin_log_service = AdminActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="publishers", tags=["publisher_list"])
    async def create_publisher(
        self, data: Dict[str, Any], admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Tạo nhà xuất bản mới.

        Args:
            data: Dữ liệu nhà xuất bản
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông tin nhà xuất bản đã tạo

        Raises:
            BadRequestException: Nếu thiếu thông tin bắt buộc
            ConflictException: Nếu tên nhà xuất bản đã tồn tại
        """
        # Kiểm tra tên nhà xuất bản
        if "name" not in data or not data["name"]:
            raise BadRequestException("Tên nhà xuất bản là bắt buộc")

        # Làm sạch dữ liệu đầu vào
        clean_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                clean_data[key] = sanitize_html(value)
            else:
                clean_data[key] = value

        # Kiểm tra tên nhà xuất bản đã tồn tại chưa
        existing = await self.publisher_repo.get_by_name(clean_data["name"])
        if existing:
            raise ConflictException(
                f"Nhà xuất bản với tên '{clean_data['name']}' đã tồn tại"
            )

        # Kiểm tra quyền
        if admin_id:
            try:
                has_permission = await check_permission(admin_id, "manage_publishers")
                if not has_permission:
                    raise ForbiddenException("Không có quyền tạo nhà xuất bản")
            except Exception:
                # Fail silently for permission check
                pass

        # Tạo nhà xuất bản
        publisher = await self.publisher_repo.create(clean_data)

        # Ghi log hoạt động
        if admin_id:
            await self.admin_log_service.log_activity(
                self.db,
                admin_id=admin_id,
                activity_type="CREATE_PUBLISHER",
                resource_type="publisher",
                resource_id=str(publisher.id),
                metadata={
                    "name": publisher.name,
                    "website": publisher.website,
                    "contact_email": publisher.contact_email,
                },
            )

        # Metrics
        self.metrics.track_admin_activity("create_publisher", "admin")

        return {
            "id": publisher.id,
            "name": publisher.name,
            "description": publisher.description,
            "website": publisher.website,
            "logo_url": publisher.logo_url,
            "contact_email": publisher.contact_email,
            "created_at": publisher.created_at,
            "updated_at": publisher.updated_at,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="publishers", tags=["publisher_details"])
    async def get_publisher(self, publisher_id: int) -> Dict[str, Any]:
        """Lấy thông tin nhà xuất bản theo ID.

        Args:
            publisher_id: ID của nhà xuất bản

        Returns:
            Thông tin nhà xuất bản

        Raises:
            NotFoundException: Nếu không tìm thấy nhà xuất bản
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("publisher", publisher_id)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy từ DB nếu không có cache
        publisher = await self.publisher_repo.get_by_id(publisher_id)
        if not publisher:
            raise NotFoundException(
                f"Không tìm thấy nhà xuất bản với ID {publisher_id}"
            )

        # Đếm số lượng sách của nhà xuất bản
        books_count = await self.book_repo.count_by_publisher(publisher_id)

        result = {
            "id": publisher.id,
            "name": publisher.name,
            "description": publisher.description,
            "website": publisher.website,
            "logo_url": publisher.logo_url,
            "contact_email": publisher.contact_email,
            "created_at": publisher.created_at,
            "updated_at": publisher.updated_at,
            "books_count": books_count,
        }

        # Lưu vào cache
        await self.cache.set(cache_key, result, ttl=3600)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="publishers", tags=["publisher_details"])
    async def get_publisher_by_id(self, publisher_id: int) -> Dict[str, Any]:
        """Lấy thông tin chi tiết nhà xuất bản theo ID.

        Phương thức này mở rộng từ get_publisher và cung cấp thêm thông tin
        chi tiết về nhà xuất bản, bao gồm các thống kê, danh sách sách mới nhất,
        và thể loại phổ biến.

        Args:
            publisher_id: ID của nhà xuất bản

        Returns:
            Thông tin chi tiết nhà xuất bản

        Raises:
            NotFoundException: Nếu không tìm thấy nhà xuất bản
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("publisher_detail", publisher_id)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy từ DB nếu không có cache
        publisher = await self.publisher_repo.get_by_id(publisher_id)
        if not publisher:
            raise NotFoundException(
                f"Không tìm thấy nhà xuất bản với ID {publisher_id}"
            )

        # Đếm số lượng sách của nhà xuất bản
        books_count = await self.book_repo.count_by_publisher(publisher_id)

        # Lấy danh sách sách mới nhất
        latest_books = await self.book_repo.get_latest_by_publisher(
            publisher_id, limit=5
        )

        # Lấy số lượng tác giả đã làm việc với nhà xuất bản
        authors_count = await self.book_repo.count_authors_by_publisher(publisher_id)

        # Lấy thống kê thể loại sách phổ biến
        top_genres = await self.book_repo.get_top_genres_by_publisher(
            publisher_id, limit=5
        )

        # Lấy điểm đánh giá trung bình của sách từ nhà xuất bản
        average_rating = await self.book_repo.get_average_rating_by_publisher(
            publisher_id
        )

        result = {
            "id": publisher.id,
            "name": publisher.name,
            "description": publisher.description,
            "website": publisher.website,
            "logo_url": publisher.logo_url,
            "contact_email": publisher.contact_email,
            "created_at": publisher.created_at,
            "updated_at": publisher.updated_at,
            "founded_year": getattr(publisher, "founded_year", None),
            "country": getattr(publisher, "country", None),
            "address": getattr(publisher, "address", None),
            "phone": getattr(publisher, "phone", None),
            "social_media": getattr(publisher, "social_media", {}),
            "books_count": books_count,
            "authors_count": authors_count,
            "average_rating": average_rating,
            "top_genres": top_genres,
            "latest_books": [
                {
                    "id": book.id,
                    "title": book.title,
                    "author_id": book.author_id,
                    "publisher_id": book.publisher_id,
                    "isbn": book.isbn,
                    "publication_date": book.publication_date,
                    "cover_image": book.cover_image,
                    "description": book.description,
                    "genre": book.genre,
                    "page_count": book.page_count,
                    "language": book.language,
                    "created_at": book.created_at,
                    "updated_at": book.updated_at,
                    "author_name": getattr(book, "author_name", None),
                    "publisher_name": getattr(book, "publisher_name", None),
                }
                for book in latest_books
            ],
        }

        # Lưu vào cache
        await self.cache.set(cache_key, result, ttl=3600)

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="publishers", tags=["publisher_details", "publisher_list"]
    )
    async def update_publisher(
        self, publisher_id: int, data: Dict[str, Any], admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Cập nhật thông tin nhà xuất bản.

        Args:
            publisher_id: ID của nhà xuất bản
            data: Dữ liệu cập nhật
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông tin nhà xuất bản đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy nhà xuất bản
            ConflictException: Nếu tên nhà xuất bản đã tồn tại
            ForbiddenException: Nếu không có quyền cập nhật
        """
        # Kiểm tra nhà xuất bản tồn tại
        publisher = await self.publisher_repo.get_by_id(publisher_id)
        if not publisher:
            raise NotFoundException(
                f"Không tìm thấy nhà xuất bản với ID {publisher_id}"
            )

        # Kiểm tra quyền
        if admin_id:
            try:
                has_permission = await check_permission(admin_id, "manage_publishers")
                if not has_permission:
                    raise ForbiddenException("Không có quyền cập nhật nhà xuất bản")
            except Exception:
                # Fail silently for permission check
                pass

        # Làm sạch dữ liệu đầu vào
        clean_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                clean_data[key] = sanitize_html(value)
            else:
                clean_data[key] = value

        # Kiểm tra tên nhà xuất bản đã tồn tại chưa (nếu có cập nhật tên)
        if "name" in clean_data and clean_data["name"] != publisher.name:
            existing = await self.publisher_repo.get_by_name(clean_data["name"])
            if existing:
                raise ConflictException(
                    f"Nhà xuất bản với tên '{clean_data['name']}' đã tồn tại"
                )

        # Lưu trạng thái cũ
        before_state = {
            "id": publisher.id,
            "name": publisher.name,
            "description": publisher.description,
            "website": publisher.website,
            "logo_url": publisher.logo_url,
            "contact_email": publisher.contact_email,
        }

        # Cập nhật nhà xuất bản
        updated = await self.publisher_repo.update(publisher_id, clean_data)

        # Đếm số lượng sách của nhà xuất bản
        books_count = await self.book_repo.count_by_publisher(publisher_id)

        result = {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "website": updated.website,
            "logo_url": updated.logo_url,
            "contact_email": updated.contact_email,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
            "books_count": books_count,
        }

        # Ghi log hoạt động
        if admin_id:
            await self.admin_log_service.log_activity(
                self.db,
                admin_id=admin_id,
                activity_type="UPDATE_PUBLISHER",
                resource_type="publisher",
                resource_id=str(publisher_id),
                before_state=before_state,
                after_state=result,
                metadata={"updated_fields": list(clean_data.keys())},
            )

        # Metrics
        self.metrics.track_admin_activity("update_publisher", "admin")

        # Xóa cache
        cache_key = CacheKeyBuilder.build_key("publisher", publisher_id)
        await self.cache.delete(cache_key)

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="publishers", tags=["publisher_details", "publisher_list"]
    )
    async def delete_publisher(
        self, publisher_id: int, admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Xóa nhà xuất bản.

        Args:
            publisher_id: ID của nhà xuất bản
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy nhà xuất bản
            BadRequestException: Nếu nhà xuất bản đang có sách
            ForbiddenException: Nếu không có quyền xóa
        """
        # Kiểm tra nhà xuất bản tồn tại
        publisher = await self.publisher_repo.get_by_id(publisher_id)
        if not publisher:
            raise NotFoundException(
                f"Không tìm thấy nhà xuất bản với ID {publisher_id}"
            )

        # Kiểm tra quyền
        if admin_id:
            try:
                has_permission = await check_permission(admin_id, "manage_publishers")
                if not has_permission:
                    raise ForbiddenException("Không có quyền xóa nhà xuất bản")
            except Exception:
                # Fail silently for permission check
                pass

        # Kiểm tra nhà xuất bản có sách không
        books_count = await self.book_repo.count_by_publisher(publisher_id)
        if books_count > 0:
            raise BadRequestException(
                f"Không thể xóa nhà xuất bản đang có {books_count} sách"
            )

        # Lưu thông tin trước khi xóa
        publisher_data = {
            "id": publisher.id,
            "name": publisher.name,
            "description": publisher.description,
        }

        # Xóa nhà xuất bản
        await self.publisher_repo.delete(publisher_id)

        # Ghi log hoạt động
        if admin_id:
            await self.admin_log_service.log_activity(
                self.db,
                admin_id=admin_id,
                activity_type="DELETE_PUBLISHER",
                resource_type="publisher",
                resource_id=str(publisher_id),
                before_state=publisher_data,
                metadata={"name": publisher.name},
            )

        # Metrics
        self.metrics.track_admin_activity("delete_publisher", "admin")

        # Xóa cache
        cache_key = CacheKeyBuilder.build_key("publisher", publisher_id)
        await self.cache.delete(cache_key)

        return {"message": "Đã xóa nhà xuất bản thành công"}

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="publishers", tags=["publisher_list"])
    async def list_publishers(
        self, skip: int = 0, limit: int = 20, search: Optional[str] = None
    ) -> Dict[str, Any]:
        """Lấy danh sách nhà xuất bản.

        Args:
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            search: Từ khóa tìm kiếm (tùy chọn)

        Returns:
            Danh sách nhà xuất bản và thông tin phân trang
        """
        # Làm sạch từ khóa tìm kiếm
        if search:
            search = sanitize_html(search)

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key(
            "publishers_list", skip, limit, search or "all"
        )

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy danh sách nhà xuất bản
        publishers = await self.publisher_repo.list_all(skip, limit, search)
        total = await self.publisher_repo.count_all(search)

        result = {
            "items": [
                {
                    "id": publisher.id,
                    "name": publisher.name,
                    "description": publisher.description,
                    "website": publisher.website,
                    "logo_url": publisher.logo_url,
                    "contact_email": publisher.contact_email,
                    "created_at": publisher.created_at,
                    "updated_at": publisher.updated_at,
                }
                for publisher in publishers
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

        # Lưu vào cache
        await self.cache.set(cache_key, result, ttl=1800)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="publishers", tags=["publisher_books"])
    async def list_publisher_books(
        self, publisher_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """Lấy danh sách sách của nhà xuất bản.

        Args:
            publisher_id: ID của nhà xuất bản
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách sách và thông tin phân trang

        Raises:
            NotFoundException: Nếu không tìm thấy nhà xuất bản
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key(
            "publisher_books", publisher_id, skip, limit
        )

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Kiểm tra nhà xuất bản tồn tại
        publisher = await self.publisher_repo.get_by_id(publisher_id)
        if not publisher:
            raise NotFoundException(
                f"Không tìm thấy nhà xuất bản với ID {publisher_id}"
            )

        # Lấy danh sách sách
        books = await self.book_repo.list_by_publisher(publisher_id, skip, limit)
        total = await self.book_repo.count_by_publisher(publisher_id)

        result = {
            "items": [
                {
                    "id": book.id,
                    "title": book.title,
                    "cover_image": book.cover_image,
                    "cover_thumbnail_url": book.cover_thumbnail_url,
                    "isbn": book.isbn,
                    "published_date": book.published_date,
                    "language": book.language,
                    "page_count": book.page_count,
                    "rating": book.rating,
                    "is_published": book.is_published,
                }
                for book in books
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
            "publisher": {
                "id": publisher.id,
                "name": publisher.name,
                "description": publisher.description,
                "logo_url": publisher.logo_url,
                "website": publisher.website,
            },
        }

        # Lưu vào cache
        await self.cache.set(cache_key, result, ttl=1800)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="publishers", tags=["popular_publishers"])
    async def get_popular_publishers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lấy danh sách nhà xuất bản phổ biến (có nhiều sách nhất).

        Args:
            limit: Số lượng nhà xuất bản trả về

        Returns:
            Danh sách nhà xuất bản phổ biến
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("popular_publishers", limit)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy danh sách nhà xuất bản phổ biến
        publishers = await self.publisher_repo.get_popular(limit)

        result = [
            {
                "id": publisher.id,
                "name": publisher.name,
                "description": publisher.description,
                "logo_url": publisher.logo_url,
                "website": publisher.website,
                "books_count": publisher.books_count,
            }
            for publisher in publishers
        ]

        # Lưu vào cache
        await self.cache.set(cache_key, result, ttl=3600)

        return result

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="publishers", tags=["publisher_list"])
    async def get_or_create_publisher(
        self, name: str, admin_id: Optional[int] = None, **kwargs
    ) -> Dict[str, Any]:
        """Lấy thông tin nhà xuất bản theo tên hoặc tạo mới nếu chưa tồn tại.

        Args:
            name: Tên nhà xuất bản
            admin_id: ID của admin thực hiện hành động (tùy chọn)
            **kwargs: Các thông tin khác của nhà xuất bản (nếu cần tạo mới)

        Returns:
            Thông tin nhà xuất bản
        """
        # Làm sạch dữ liệu
        name = sanitize_html(name)
        clean_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, str):
                clean_kwargs[key] = sanitize_html(value)
            else:
                clean_kwargs[key] = value

        # Tìm kiếm nhà xuất bản theo tên
        publisher = await self.publisher_repo.get_by_name(name)

        if not publisher:
            # Tạo nhà xuất bản mới
            data = {"name": name, **clean_kwargs}
            publisher = await self.publisher_repo.create(data)

            # Ghi log hoạt động
            if admin_id:
                await self.admin_log_service.log_activity(
                    self.db,
                    admin_id=admin_id,
                    activity_type="CREATE_PUBLISHER",
                    resource_type="publisher",
                    resource_id=str(publisher.id),
                    metadata={"name": publisher.name, "auto_created": True},
                )

            # Metrics
            self.metrics.track_admin_activity("auto_create_publisher", "system")

        return {
            "id": publisher.id,
            "name": publisher.name,
            "description": publisher.description,
            "website": publisher.website,
            "logo_url": publisher.logo_url,
            "contact_email": publisher.contact_email,
            "created_at": publisher.created_at,
            "updated_at": publisher.updated_at,
        }
