from typing import Optional, List, Dict, Any, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, not_, func, desc, asc, text
import re
from datetime import datetime, timezone, timedelta
import time

from app.cache.decorators import cached
from app.user_site.repositories.tag_repo import TagRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.book_tag_repo import BookTagRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ConflictException,
    ValidationException,
    ForbiddenException,
)
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.user_site.models.tag import Tag
from app.cache.decorators import invalidate_cache
from app.security.input_validation.sanitizers import sanitize_text
from app.logging.setup import get_logger
from app.monitoring.metrics.business_metrics import business_metrics

logger = get_logger(__name__)


# Hàm trợ giúp để thay thế track_tag_activity
def track_tag_activity(action_type: str):
    """
    Ghi nhận hoạt động liên quan đến thẻ

    Args:
        action_type: Loại hành động (create, update, delete, add_to_book, remove_from_book)
    """
    business_metrics.track_social_action(action_type, "tag")


async def log_data_operation(
    db: AsyncSession,
    user_id: int,
    operation: str,
    entity_type: str,
    entity_id: int,
    metadata: Dict[str, Any],
) -> None:
    """
    Ghi nhận hoạt động liên quan đến dữ liệu

    Args:
        db: Database session
        user_id: ID người dùng thực hiện hành động
        operation: Loại hành động (create, update, delete)
        entity_type: Loại đối tượng (tag, book, etc.)
        entity_id: ID của đối tượng
        metadata: Thông tin bổ sung
    """
    activity_type = f"{operation.upper()}_{entity_type.upper()}"
    await create_user_activity_log(
        db,
        UserActivityLogCreate(
            user_id=user_id,
            activity_type=activity_type,
            resource_type=entity_type,
            resource_id=str(entity_id),
            metadata=metadata,
        ),
    )


class TagService:
    def __init__(self, db: AsyncSession):
        """
        Khởi tạo dịch vụ tag

        Args:
            db: Phiên làm việc cơ sở dữ liệu không đồng bộ
        """
        self.db = db
        self.tag_repo = TagRepository(db)
        self.book_repo = BookRepository(db)
        self.book_tag_repo = BookTagRepository(db)

    @cached(ttl=3600, namespace="tags", key_prefix="all", tags=["tags"])
    async def get_all_tags(self, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
        """
        Lấy danh sách tất cả các tag

        Args:
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách các tag và thông tin phân trang
        """
        tags = await self.tag_repo.get_all(skip, limit)
        total = await self.tag_repo.count_all()

        result = []
        for tag in tags:
            result.append(
                {
                    "id": tag.id,
                    "name": tag.name,
                    "slug": tag.slug,
                    "description": tag.description,
                    "color": tag.color,
                    "is_active": tag.is_active,
                    "books_count": await self.tag_repo.count_books_by_tag(tag.id),
                    "created_at": tag.created_at,
                    "updated_at": tag.updated_at,
                }
            )

        return {"items": result, "total": total, "skip": skip, "limit": limit}

    @cached(ttl=3600, namespace="tags", key_prefix="detail", tags=["tags"])
    async def get_tag(self, tag_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin chi tiết của tag theo ID.

        Args:
            tag_id: ID của tag

        Returns:
            Thông tin tag bao gồm số lượng sách liên quan

        Raises:
            NotFoundException: Nếu không tìm thấy tag
        """
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(f"Không tìm thấy tag với ID {tag_id}")

        # Format kết quả
        result = {
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "description": tag.description,
            "color": tag.color,
            "books_count": await self.tag_repo.count_books_by_tag(tag.id),
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
        }

        return result

    @cached(ttl=3600, namespace="tags", key_prefix="slug", tags=["tags"])
    async def get_tag_by_slug(self, slug: str) -> Dict[str, Any]:
        """
        Lấy thông tin tag theo slug

        Args:
            slug: Slug của tag

        Returns:
            Thông tin tag

        Raises:
            NotFoundException: Nếu không tìm thấy tag
        """
        tag = await self.tag_repo.get_by_slug(slug)
        if not tag:
            raise NotFoundException(f"Không tìm thấy tag với slug {slug}")

        books_count = await self.tag_repo.count_books_by_tag(tag.id)

        return {
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "description": tag.description,
            "color": tag.color,
            "is_active": tag.is_active,
            "books_count": books_count,
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
        }

    @cached(ttl=3600, namespace="tags", key_prefix="popular", tags=["tags"])
    async def get_popular_tags(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các tag phổ biến

        Args:
            limit: Số lượng tag tối đa trả về

        Returns:
            Danh sách các tag phổ biến
        """
        popular_tags = await self.tag_repo.get_popular_tags(limit)

        result = []
        for tag, books_count in popular_tags:
            result.append(
                {
                    "id": tag.id,
                    "name": tag.name,
                    "slug": tag.slug,
                    "description": tag.description,
                    "color": tag.color,
                    "books_count": books_count,
                }
            )

        return result

    @cached(ttl=3600, namespace="tags", key_prefix="books", tags=["tags", "books"])
    async def get_books_by_tag(
        self, tag_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách sách có tag nhất định.

        Args:
            tag_id: ID của tag
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi lấy

        Returns:
            Danh sách sách và tổng số lượng

        Raises:
            NotFoundException: Nếu không tìm thấy tag
        """
        # Kiểm tra tag tồn tại
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(f"Không tìm thấy tag với ID {tag_id}")

        # Lấy danh sách sách
        books = await self.tag_repo.get_books_by_tag(tag_id, skip, limit)
        total = await self.tag_repo.count_books_by_tag(tag_id)

        # Format kết quả
        result = []
        for book in books:
            result.append(
                {
                    "id": book.id,
                    "title": book.title,
                    "slug": book.slug,
                    "author_name": book.author_name,
                    "cover_url": book.cover_url,
                    "avg_rating": book.avg_rating,
                    "ratings_count": book.ratings_count,
                    "is_published": book.is_published,
                    "published_date": book.published_date,
                }
            )

        return {"items": result, "total": total}

    async def create_tag(self, data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """
        Tạo tag mới

        Args:
            data: Dữ liệu tag
            user_id: ID người dùng thực hiện hành động

        Returns:
            Thông tin tag đã tạo

        Raises:
            ValidationException: Nếu dữ liệu không hợp lệ
            ConflictException: Nếu tên tag đã tồn tại
        """
        # Kiểm tra dữ liệu
        if "name" not in data or not data["name"]:
            raise ValidationException("Tên tag không được để trống")

        # Làm sạch dữ liệu
        cleaned_name = sanitize_text(data["name"].strip())
        if "description" in data and data["description"]:
            data["description"] = sanitize_text(data["description"])

        # Kiểm tra tag đã tồn tại chưa
        existing_tag = await self.tag_repo.get_by_name(cleaned_name)
        if existing_tag:
            raise ConflictException(f"Tag với tên '{cleaned_name}' đã tồn tại")

        # Tạo slug tự động nếu không cung cấp
        if "slug" not in data or not data["slug"]:
            from slugify import slugify

            data["slug"] = slugify(cleaned_name)

        # Kiểm tra slug đã tồn tại chưa
        existing_slug = await self.tag_repo.get_by_slug(data["slug"])
        if existing_slug:
            raise ConflictException(f"Slug '{data['slug']}' đã tồn tại")

        # Tạo tag mới
        data["name"] = cleaned_name
        data["created_by"] = user_id

        tag = await self.tag_repo.create(data)

        # Ghi log và theo dõi số liệu
        await log_data_operation(
            self.db,
            user_id=user_id,
            operation="create",
            entity_type="tag",
            entity_id=tag.id,
            metadata={"name": tag.name, "slug": tag.slug},
        )

        track_tag_activity("create")

        # Vô hiệu hóa cache
        await self._invalidate_tag_cache()

        return {
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "description": tag.description,
            "color": tag.color,
            "is_active": tag.is_active,
            "created_at": tag.created_at,
            "created_by": tag.created_by,
        }

    async def update_tag(
        self, tag_id: int, data: Dict[str, Any], user_id: int
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin tag

        Args:
            tag_id: ID của tag
            data: Dữ liệu cập nhật
            user_id: ID người dùng thực hiện hành động

        Returns:
            Thông tin tag đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy tag
            ValidationException: Nếu dữ liệu không hợp lệ
            ConflictException: Nếu tên tag hoặc slug đã tồn tại
        """
        # Kiểm tra tag tồn tại
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(f"Không tìm thấy tag với ID {tag_id}")

        # Làm sạch dữ liệu
        if "name" in data and data["name"]:
            data["name"] = sanitize_text(data["name"].strip())

            # Kiểm tra tên đã tồn tại chưa
            existing_tag = await self.tag_repo.get_by_name(data["name"])
            if existing_tag and existing_tag.id != tag_id:
                raise ConflictException(f"Tag với tên '{data['name']}' đã tồn tại")

        if "description" in data and data["description"]:
            data["description"] = sanitize_text(data["description"])

        # Kiểm tra slug nếu có cập nhật
        if "slug" in data and data["slug"]:
            existing_slug = await self.tag_repo.get_by_slug(data["slug"])
            if existing_slug and existing_slug.id != tag_id:
                raise ConflictException(f"Slug '{data['slug']}' đã tồn tại")

        # Tạo slug tự động nếu cập nhật tên nhưng không cập nhật slug
        if "name" in data and "slug" not in data:
            from slugify import slugify

            new_slug = slugify(data["name"])

            # Kiểm tra slug mới đã tồn tại chưa
            existing_slug = await self.tag_repo.get_by_slug(new_slug)
            if existing_slug and existing_slug.id != tag_id:
                # Thêm ID vào slug để đảm bảo duy nhất
                new_slug = f"{new_slug}-{tag_id}"

            data["slug"] = new_slug

        # Cập nhật tag
        data["updated_by"] = user_id
        data["updated_at"] = datetime.now(timezone.utc)

        updated_tag = await self.tag_repo.update(tag_id, data)

        # Ghi log và theo dõi số liệu
        await log_data_operation(
            self.db,
            user_id=user_id,
            operation="update",
            entity_type="tag",
            entity_id=tag_id,
            metadata={
                "name": updated_tag.name,
                "slug": updated_tag.slug,
                "updated_fields": list(data.keys()),
            },
        )

        track_tag_activity("update")

        # Vô hiệu hóa cache
        await self._invalidate_tag_cache()

        # Trả về kết quả
        return {
            "id": updated_tag.id,
            "name": updated_tag.name,
            "slug": updated_tag.slug,
            "description": updated_tag.description,
            "color": updated_tag.color,
            "is_active": updated_tag.is_active,
            "updated_at": updated_tag.updated_at,
        }

    async def delete_tag(self, tag_id: int, user_id: int) -> Dict[str, Any]:
        """
        Xóa tag

        Args:
            tag_id: ID của tag
            user_id: ID người dùng thực hiện hành động

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy tag
            ConflictException: Nếu tag đang được sử dụng bởi sách
        """
        # Kiểm tra tag tồn tại
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(f"Không tìm thấy tag với ID {tag_id}")

        # Kiểm tra tag đang được sử dụng không
        books_count = await self.tag_repo.count_books_by_tag(tag_id)
        if books_count > 0:
            raise ConflictException(
                f"Không thể xóa tag đang được sử dụng bởi {books_count} sách"
            )

        # Xóa tag
        await self.tag_repo.delete(tag_id)

        # Ghi log và theo dõi số liệu
        await log_data_operation(
            self.db,
            user_id=user_id,
            operation="delete",
            entity_type="tag",
            entity_id=tag_id,
            metadata={"name": tag.name, "slug": tag.slug},
        )

        track_tag_activity("delete")

        # Vô hiệu hóa cache
        await self._invalidate_tag_cache()

        return {"success": True, "message": f"Đã xóa tag '{tag.name}' thành công"}

    async def add_tag_to_book(
        self, book_id: int, tag_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Thêm tag cho sách.

        Args:
            book_id: ID của sách
            tag_id: ID của tag
            user_id: ID của người dùng thêm tag

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy sách hoặc tag
            BadRequestException: Nếu sách đã có tag này
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra tag tồn tại
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(f"Không tìm thấy tag với ID {tag_id}")

        # Kiểm tra sách đã có tag này chưa
        has_tag = await self.tag_repo.add_book_tag(book_id, tag_id)
        if not has_tag:
            # Tag đã tồn tại cho sách
            raise BadRequestException(f"Sách '{book.title}' đã có tag '{tag.name}'")

        # Log hoạt động
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="ADD_TAG",
                resource_type="book",
                resource_id=str(book_id),
                metadata={"tag_id": tag_id, "tag_name": tag.name},
            ),
        )

        # Track metrics
        track_tag_activity("add_to_book")

        # Invalidate cache liên quan
        await self._invalidate_tag_cache(tag_id=tag_id, book_id=book_id)

        return {
            "message": f"Đã thêm tag '{tag.name}' cho sách '{book.title}'",
            "tag_id": tag_id,
            "book_id": book_id,
        }

    async def remove_tag_from_book(
        self, book_id: int, tag_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Xóa tag khỏi sách.

        Args:
            book_id: ID của sách
            tag_id: ID của tag
            user_id: ID của người dùng xóa tag

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy sách hoặc tag
            BadRequestException: Nếu sách không có tag này
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra tag tồn tại
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(f"Không tìm thấy tag với ID {tag_id}")

        # Kiểm tra sách có tag này không
        result = await self.tag_repo.remove_book_tag(book_id, tag_id)
        if not result:
            # Tag không tồn tại cho sách
            raise BadRequestException(f"Sách '{book.title}' không có tag '{tag.name}'")

        # Log hoạt động
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="REMOVE_TAG",
                resource_type="book",
                resource_id=str(book_id),
                metadata={"tag_id": tag_id, "tag_name": tag.name},
            ),
        )

        # Track metrics
        track_tag_activity("remove_from_book")

        # Invalidate cache liên quan
        await self._invalidate_tag_cache(tag_id=tag_id, book_id=book_id)

        return {
            "message": f"Đã xóa tag '{tag.name}' khỏi sách '{book.title}'",
            "tag_id": tag_id,
            "book_id": book_id,
        }

    @cached(ttl=3600, namespace="tags", key_prefix="book", tags=["tags", "books"])
    async def get_tags_by_book(self, book_id: int) -> List[Dict[str, Any]]:
        """
        Lấy danh sách tag của sách.

        Args:
            book_id: ID của sách

        Returns:
            Danh sách tag của sách

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách với ID {book_id}")

        # Lấy danh sách tag
        tags = await self.tag_repo.get_tags_by_book(book_id)

        # Format kết quả
        result = []
        for tag in tags:
            result.append(
                {
                    "id": tag.id,
                    "name": tag.name,
                    "slug": tag.slug,
                    "color": tag.color,
                    "books_count": await self.tag_repo.count_books_by_tag(tag.id),
                }
            )

        return result

    async def search_tags(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Tìm kiếm tag

        Args:
            query: Từ khóa tìm kiếm
            limit: Số lượng kết quả tối đa

        Returns:
            Danh sách tag phù hợp
        """
        if not query:
            return []

        # Làm sạch từ khóa
        cleaned_query = sanitize_text(query.strip())

        # Tìm kiếm tag
        tags = await self.tag_repo.search(cleaned_query, limit)

        # Format kết quả
        result = []
        for tag in tags:
            result.append(
                {
                    "id": tag.id,
                    "name": tag.name,
                    "slug": tag.slug,
                    "color": tag.color,
                    "books_count": await self.tag_repo.count_books_by_tag(tag.id),
                }
            )

        return result

    # --- Helper methods --- #

    async def _invalidate_tag_cache(
        self, tag_id: Optional[int] = None, book_id: Optional[int] = None
    ) -> None:
        """
        Vô hiệu hóa cache liên quan đến tag

        Args:
            tag_id: ID của tag (tùy chọn)
            book_id: ID của sách (tùy chọn)
        """
        # Giả sử đã thiết lập cache_manager từ app/cache/manager.py
        from app.cache.manager import cache_manager

        # Tạo danh sách tag cần vô hiệu hóa
        tags_to_invalidate = ["tags"]

        if tag_id:
            tags_to_invalidate.append(f"tag:{tag_id}")

        if book_id:
            tags_to_invalidate.append(f"book:{book_id}")

        # Vô hiệu hóa cache
        await cache_manager.invalidate_by_tags(tags_to_invalidate)
