from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.bookshelf_repo import BookshelfRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    ConflictException,
)
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache


class BookshelfService:
    """Service để quản lý kệ sách (bookshelf) của người dùng."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo service với AsyncSession."""
        self.db = db
        self.bookshelf_repo = BookshelfRepository(db)
        self.book_repo = BookRepository(db)
        self.user_repo = UserRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    @invalidate_cache(namespace="bookshelves", tags=["user_bookshelves"])
    async def create_bookshelf(
        self,
        user_id: int,
        name: str,
        description: Optional[str] = None,
        is_public: bool = False,
        is_default: bool = False,
    ) -> Dict[str, Any]:
        """
        Tạo kệ sách mới cho người dùng.

        Args:
            user_id: ID người dùng
            name: Tên kệ sách
            description: Mô tả kệ sách
            is_public: Có công khai kệ sách không
            is_default: Có đặt làm kệ sách mặc định không

        Returns:
            Thông tin kệ sách đã tạo

        Raises:
            ConflictException: Nếu tên kệ sách đã tồn tại cho người dùng
        """
        # Kiểm tra tên kệ sách đã tồn tại chưa
        existing = await self.bookshelf_repo.get_bookshelf_by_name_and_user(
            name, user_id
        )
        if existing:
            raise ConflictException(detail=f"Bạn đã có kệ sách với tên '{name}'")

        # Tạo kệ sách mới
        bookshelf_data = {
            "user_id": user_id,
            "name": name,
            "description": description,
            "is_public": is_public,
            "is_default": is_default,
        }

        # Track metric
        self.metrics.track_user_activity("bookshelf_created")

        # Tạo bookshelf
        created_bookshelf = await self.bookshelf_repo.create_bookshelf(bookshelf_data)
        return self._format_bookshelf_response(created_bookshelf)

    @cached(ttl=3600, namespace="bookshelves", tags=["bookshelf_details"])
    async def get_bookshelf(
        self, bookshelf_id: int, current_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin chi tiết của một kệ sách.

        Args:
            bookshelf_id: ID kệ sách
            current_user_id: ID người dùng hiện tại (để kiểm tra quyền)

        Returns:
            Thông tin chi tiết kệ sách

        Raises:
            NotFoundException: Nếu không tìm thấy kệ sách
            ForbiddenException: Nếu kệ sách không công khai và không phải chủ sở hữu
        """
        bookshelf = await self.bookshelf_repo.get_bookshelf_by_id(
            bookshelf_id, with_relations=["user", "items", "items.book"]
        )

        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Kiểm tra quyền: nếu không công khai thì chỉ chủ sở hữu mới có quyền xem
        if (
            not bookshelf.is_public
            and current_user_id
            and bookshelf.user_id != current_user_id
        ):
            raise ForbiddenException(detail="Bạn không có quyền xem kệ sách này")

        # Track metric
        self.metrics.track_user_activity("bookshelf_viewed")

        # Đếm số sách trong kệ
        book_count = await self.bookshelf_repo.count_bookshelf_items(bookshelf_id)

        bookshelf_data = self._format_bookshelf_response(bookshelf)
        bookshelf_data["book_count"] = book_count

        return bookshelf_data

    @invalidate_cache(
        namespace="bookshelves", tags=["user_bookshelves", "bookshelf_details"]
    )
    async def update_bookshelf(
        self, bookshelf_id: int, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin kệ sách.

        Args:
            bookshelf_id: ID kệ sách
            user_id: ID người dùng (để kiểm tra quyền)
            data: Dữ liệu cập nhật (name, description, is_public)

        Returns:
            Thông tin kệ sách đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy kệ sách
            ForbiddenException: Nếu không phải chủ sở hữu
            ConflictException: Nếu tên kệ sách mới đã tồn tại
        """
        # Kiểm tra kệ sách tồn tại
        bookshelf = await self.bookshelf_repo.get_bookshelf_by_id(bookshelf_id)
        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Kiểm tra quyền: chỉ chủ sở hữu mới có quyền cập nhật
        if bookshelf.user_id != user_id:
            raise ForbiddenException(detail="Bạn không có quyền cập nhật kệ sách này")

        # Kiểm tra trùng tên nếu có cập nhật tên
        if "name" in data and data["name"] != bookshelf.name:
            existing = await self.bookshelf_repo.get_bookshelf_by_name_and_user(
                data["name"], user_id
            )
            if existing and existing.id != bookshelf_id:
                raise ConflictException(
                    detail=f"Bạn đã có kệ sách khác với tên '{data['name']}'"
                )

        # Lọc dữ liệu hợp lệ
        allowed_fields = {"name", "description", "is_public"}
        update_data = {k: v for k, v in data.items() if k in allowed_fields}

        # Cập nhật kệ sách
        updated_bookshelf = await self.bookshelf_repo.update_bookshelf(
            bookshelf_id, update_data
        )

        # Track metric
        self.metrics.track_user_activity("bookshelf_updated")

        return self._format_bookshelf_response(updated_bookshelf)

    @invalidate_cache(
        namespace="bookshelves", tags=["user_bookshelves", "bookshelf_details"]
    )
    async def delete_bookshelf(self, bookshelf_id: int, user_id: int) -> Dict[str, Any]:
        """
        Xóa kệ sách.

        Args:
            bookshelf_id: ID kệ sách
            user_id: ID người dùng (để kiểm tra quyền)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy kệ sách
            ForbiddenException: Nếu không phải chủ sở hữu
            BadRequestException: Nếu cố gắng xóa kệ mặc định
        """
        # Kiểm tra kệ sách tồn tại
        bookshelf = await self.bookshelf_repo.get_bookshelf_by_id(bookshelf_id)
        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Kiểm tra quyền: chỉ chủ sở hữu mới có quyền xóa
        if bookshelf.user_id != user_id:
            raise ForbiddenException(detail="Bạn không có quyền xóa kệ sách này")

        # Không cho xóa kệ mặc định
        if bookshelf.is_default:
            raise BadRequestException(detail="Không thể xóa kệ sách mặc định")

        # Xóa kệ sách
        success = await self.bookshelf_repo.delete_bookshelf(bookshelf_id)

        # Track metric
        self.metrics.track_user_activity("bookshelf_deleted")

        return {"success": success, "message": "Kệ sách đã được xóa thành công"}

    @cached(
        ttl=1800,
        namespace="bookshelves",
        tags=["user_bookshelves"],
        key_builder=lambda *args, **kwargs: f"user_bookshelves:{kwargs.get('user_id')}:{kwargs.get('skip')}:{kwargs.get('limit')}",
    )
    async def list_user_bookshelves(
        self,
        user_id: int,
        current_user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Liệt kê kệ sách của một người dùng.

        Args:
            user_id: ID người dùng sở hữu kệ sách
            current_user_id: ID người dùng đang xem (để kiểm tra quyền)
            skip: Số mục bỏ qua (phân trang)
            limit: Số mục tối đa trả về

        Returns:
            Danh sách kệ sách và tổng số

        Raises:
            ForbiddenException: Nếu không phải chủ sở hữu và yêu cầu xem kệ riêng tư
        """
        # Không cần kiểm tra người dùng tồn tại, vì nếu không tồn tại thì danh sách sẽ trống

        # Nếu không phải chủ sở hữu, chỉ hiển thị các kệ công khai
        is_owner = current_user_id and current_user_id == user_id

        if not is_owner:
            # Kiểm tra có public bookshelf của người dùng này không
            public_count = await self.bookshelf_repo.count_public_bookshelves_by_user(
                user_id
            )
            if public_count == 0:
                return {"items": [], "total": 0}

        # Lấy danh sách kệ sách
        bookshelves = await self.bookshelf_repo.list_user_bookshelves(
            user_id, skip, limit, with_relations=["user"]
        )

        # Nếu không phải chủ sở hữu, lọc các kệ riêng tư
        if not is_owner:
            bookshelves = [bs for bs in bookshelves if bs.is_public]

        # Đếm tổng số kệ
        total = await self.bookshelf_repo.count_user_bookshelves(user_id)
        if not is_owner:
            total = await self.bookshelf_repo.count_public_bookshelves_by_user(user_id)

        # Track metric
        self.metrics.track_user_activity("bookshelves_listed")

        return {
            "items": [self._format_bookshelf_response(bs) for bs in bookshelves],
            "total": total,
        }

    @cached(
        ttl=1800,
        namespace="bookshelves",
        tags=["public_bookshelves"],
        key_builder=lambda *args, **kwargs: (
            f"public_bookshelves:{kwargs.get('skip')}:{kwargs.get('limit')}:"
            f"{kwargs.get('search_query', '')}"
        ),
    )
    async def list_public_bookshelves(
        self, skip: int = 0, limit: int = 20, search_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Liệt kê kệ sách công khai của tất cả người dùng.

        Args:
            skip: Số mục bỏ qua (phân trang)
            limit: Số mục tối đa trả về
            search_query: Từ khóa tìm kiếm (tùy chọn)

        Returns:
            Danh sách kệ sách công khai và tổng số
        """
        # Lấy danh sách kệ sách công khai
        bookshelves = await self.bookshelf_repo.list_public_bookshelves(
            skip, limit, search_query, with_relations=["user"]
        )

        # Đếm tổng số kệ công khai
        total = await self.bookshelf_repo.count_public_bookshelves(search_query)

        # Track metric
        self.metrics.track_user_activity("public_bookshelves_listed")

        return {
            "items": [self._format_bookshelf_response(bs) for bs in bookshelves],
            "total": total,
        }

    @cached(
        ttl=3600,
        namespace="bookshelves",
        tags=["default_bookshelf"],
        key_builder=lambda *args, **kwargs: f"default_bookshelf:{kwargs.get('user_id')}",
    )
    async def get_default_bookshelf(self, user_id: int) -> Dict[str, Any]:
        """
        Lấy kệ sách mặc định của người dùng.
        Nếu chưa có, sẽ tự động tạo mới.

        Args:
            user_id: ID người dùng

        Returns:
            Thông tin kệ sách mặc định
        """
        # Lấy hoặc tạo kệ mặc định
        default_bookshelf = await self.bookshelf_repo.get_default_bookshelf(user_id)

        # Track metric
        self.metrics.track_user_activity("default_bookshelf_accessed")

        return self._format_bookshelf_response(default_bookshelf)

    @invalidate_cache(
        namespace="bookshelves", tags=["bookshelf_details", "bookshelf_items"]
    )
    async def add_book_to_bookshelf(
        self, bookshelf_id: int, user_id: int, book_id: int, note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Thêm sách vào kệ sách.

        Args:
            bookshelf_id: ID kệ sách
            user_id: ID người dùng (để kiểm tra quyền)
            book_id: ID sách
            note: Ghi chú về sách

        Returns:
            Thông tin mục đã thêm

        Raises:
            NotFoundException: Nếu không tìm thấy kệ sách hoặc sách
            ForbiddenException: Nếu không phải chủ sở hữu kệ
            ConflictException: Nếu sách đã có trong kệ
        """
        # Kiểm tra kệ sách tồn tại
        bookshelf = await self.bookshelf_repo.get_bookshelf_by_id(bookshelf_id)
        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Kiểm tra quyền: chỉ chủ sở hữu mới có quyền thêm sách
        if bookshelf.user_id != user_id:
            raise ForbiddenException(
                detail="Bạn không có quyền thêm sách vào kệ sách này"
            )

        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra sách đã có trong kệ chưa
        existing_item = await self.bookshelf_repo.get_bookshelf_item_by_book(
            bookshelf_id, book_id
        )

        if existing_item:
            # Cập nhật note nếu có thay đổi
            if note is not None and note != existing_item.note:
                updated_item = await self.bookshelf_repo.update_bookshelf_item(
                    existing_item.id, {"note": note}
                )
                return self._format_bookshelf_item_response(updated_item)
            return self._format_bookshelf_item_response(existing_item)

        # Thêm sách vào kệ
        bookshelf_item = await self.bookshelf_repo.add_book_to_bookshelf(
            bookshelf_id, book_id, note
        )

        # Track metric
        self.metrics.track_user_activity("book_added_to_bookshelf")

        return self._format_bookshelf_item_response(bookshelf_item)

    @invalidate_cache(
        namespace="bookshelves", tags=["bookshelf_details", "bookshelf_items"]
    )
    async def remove_book_from_bookshelf(
        self, bookshelf_id: int, user_id: int, book_id: int
    ) -> Dict[str, Any]:
        """
        Xóa sách khỏi kệ sách.

        Args:
            bookshelf_id: ID kệ sách
            user_id: ID người dùng (để kiểm tra quyền)
            book_id: ID sách

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy kệ sách hoặc sách không có trong kệ
            ForbiddenException: Nếu không phải chủ sở hữu kệ
        """
        # Kiểm tra kệ sách tồn tại
        bookshelf = await self.bookshelf_repo.get_bookshelf_by_id(bookshelf_id)
        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Kiểm tra quyền: chỉ chủ sở hữu mới có quyền xóa sách
        if bookshelf.user_id != user_id:
            raise ForbiddenException(
                detail="Bạn không có quyền xóa sách khỏi kệ sách này"
            )

        # Kiểm tra sách có trong kệ không
        bookshelf_item = await self.bookshelf_repo.get_bookshelf_item_by_book(
            bookshelf_id, book_id
        )
        if not bookshelf_item:
            raise NotFoundException(detail=f"Sách không có trong kệ sách này")

        # Xóa sách khỏi kệ
        success = await self.bookshelf_repo.delete_bookshelf_item(bookshelf_item.id)

        # Track metric
        self.metrics.track_user_activity("book_removed_from_bookshelf")

        return {"success": success, "message": "Sách đã được xóa khỏi kệ sách"}

    @invalidate_cache(
        namespace="bookshelves", tags=["bookshelf_details", "bookshelf_items"]
    )
    async def update_bookshelf_item(
        self, bookshelf_id: int, book_id: int, user_id: int, note: str
    ) -> Dict[str, Any]:
        """
        Cập nhật ghi chú cho một sách trong kệ.

        Args:
            bookshelf_id: ID kệ sách
            book_id: ID sách
            user_id: ID người dùng (để kiểm tra quyền)
            note: Ghi chú mới

        Returns:
            Thông tin mục đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy kệ sách hoặc sách không có trong kệ
            ForbiddenException: Nếu không phải chủ sở hữu kệ
        """
        # Kiểm tra kệ sách tồn tại
        bookshelf = await self.bookshelf_repo.get_bookshelf_by_id(bookshelf_id)
        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Kiểm tra quyền: chỉ chủ sở hữu mới có quyền cập nhật
        if bookshelf.user_id != user_id:
            raise ForbiddenException(
                detail="Bạn không có quyền cập nhật ghi chú trong kệ sách này"
            )

        # Kiểm tra sách có trong kệ không
        bookshelf_item = await self.bookshelf_repo.get_bookshelf_item_by_book(
            bookshelf_id, book_id
        )
        if not bookshelf_item:
            raise NotFoundException(detail=f"Sách không có trong kệ sách này")

        # Cập nhật ghi chú
        updated_item = await self.bookshelf_repo.update_bookshelf_item(
            bookshelf_item.id, {"note": note}
        )

        # Track metric
        self.metrics.track_user_activity("bookshelf_item_updated")

        return self._format_bookshelf_item_response(updated_item)

    @cached(
        ttl=1800,
        namespace="bookshelves",
        tags=["bookshelf_items"],
        key_builder=lambda *args, **kwargs: f"bookshelf_items:{kwargs.get('bookshelf_id')}:{kwargs.get('skip')}:{kwargs.get('limit')}",
    )
    async def list_bookshelf_items(
        self,
        bookshelf_id: int,
        current_user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Liệt kê sách trong kệ sách.

        Args:
            bookshelf_id: ID kệ sách
            current_user_id: ID người dùng đang xem (để kiểm tra quyền)
            skip: Số mục bỏ qua (phân trang)
            limit: Số mục tối đa trả về

        Returns:
            Danh sách sách trong kệ và tổng số

        Raises:
            NotFoundException: Nếu không tìm thấy kệ sách
            ForbiddenException: Nếu kệ sách không công khai và không phải chủ sở hữu
        """
        # Kiểm tra kệ sách tồn tại
        bookshelf = await self.bookshelf_repo.get_bookshelf_by_id(bookshelf_id)
        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Kiểm tra quyền: nếu không công khai thì chỉ chủ sở hữu mới có quyền xem
        if (
            not bookshelf.is_public
            and current_user_id
            and bookshelf.user_id != current_user_id
        ):
            raise ForbiddenException(
                detail="Bạn không có quyền xem sách trong kệ sách này"
            )

        # Lấy danh sách sách trong kệ
        items = await self.bookshelf_repo.list_bookshelf_items(
            bookshelf_id, skip, limit, with_relations=["book"]
        )

        # Đếm tổng số sách trong kệ
        total = await self.bookshelf_repo.count_bookshelf_items(bookshelf_id)

        # Track metric
        self.metrics.track_user_activity("bookshelf_items_listed")

        return {
            "items": [self._format_bookshelf_item_response(item) for item in items],
            "total": total,
            "bookshelf": self._format_bookshelf_response(bookshelf),
        }

    @cached(
        ttl=1800,
        namespace="bookshelves",
        tags=["user_book_bookshelves"],
        key_builder=lambda *args, **kwargs: f"user_book_bookshelves:{kwargs.get('user_id')}:{kwargs.get('book_id')}",
    )
    async def check_book_in_user_bookshelves(
        self, user_id: int, book_id: int
    ) -> Dict[str, Any]:
        """
        Kiểm tra một cuốn sách có trong các kệ sách của người dùng không.
        Hữu ích cho UI khi hiển thị trạng thái đã thêm vào kệ hay chưa.

        Args:
            user_id: ID người dùng
            book_id: ID sách

        Returns:
            Danh sách kệ sách chứa cuốn sách và thông tin có nằm trong kệ mặc định không
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy danh sách kệ sách chứa cuốn sách
        bookshelves = await self.bookshelf_repo.get_user_book_bookshelves(
            user_id, book_id
        )

        # Kiểm tra có trong kệ mặc định không
        default_bookshelf = await self.bookshelf_repo.get_default_bookshelf(user_id)
        in_default = (
            any(bs.id == default_bookshelf.id for bs in bookshelves)
            if bookshelves
            else False
        )

        # Track metric
        self.metrics.track_user_activity("book_bookshelf_check")

        return {
            "in_any_bookshelf": len(bookshelves) > 0,
            "in_default_bookshelf": in_default,
            "bookshelves": [self._format_bookshelf_response(bs) for bs in bookshelves],
            "bookshelf_count": len(bookshelves),
        }

    @invalidate_cache(
        namespace="bookshelves",
        tags=["user_bookshelves", "bookshelf_items", "user_book_bookshelves"],
    )
    async def remove_book_from_all_bookshelves(
        self, user_id: int, book_id: int
    ) -> Dict[str, Any]:
        """
        Xóa một cuốn sách khỏi tất cả kệ sách của người dùng.

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

        # Xóa sách khỏi tất cả kệ
        count = await self.bookshelf_repo.remove_book_from_all_bookshelves(
            user_id, book_id
        )

        # Track metric
        self.metrics.track_user_activity("book_removed_from_all_bookshelves")

        return {
            "success": True,
            "message": f"Đã xóa sách khỏi {count} kệ sách",
            "count": count,
        }

    @invalidate_cache(
        namespace="bookshelves",
        tags=["default_bookshelf", "bookshelf_items", "user_book_bookshelves"],
    )
    async def add_book_to_default_bookshelf(
        self, user_id: int, book_id: int, note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Thêm sách vào kệ sách mặc định của người dùng.
        Tiện lợi cho chức năng "Thêm vào kệ sách của tôi".

        Args:
            user_id: ID người dùng
            book_id: ID sách
            note: Ghi chú (tùy chọn)

        Returns:
            Thông tin mục đã thêm
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy hoặc tạo kệ mặc định
        default_bookshelf = await self.bookshelf_repo.get_default_bookshelf(user_id)

        # Thêm sách vào kệ mặc định
        bookshelf_item = await self.bookshelf_repo.add_book_to_bookshelf(
            default_bookshelf.id, book_id, note
        )

        # Track metric
        self.metrics.track_user_activity("book_added_to_default_bookshelf")

        return {
            "bookshelf": self._format_bookshelf_response(default_bookshelf),
            "item": self._format_bookshelf_item_response(bookshelf_item),
        }

    def _format_bookshelf_response(self, bookshelf) -> Dict[str, Any]:
        """
        Chuyển đổi đối tượng bookshelf thành response dict.

        Args:
            bookshelf: Đối tượng Bookshelf từ database

        Returns:
            Dict thông tin bookshelf đã được format
        """
        result = {
            "id": bookshelf.id,
            "user_id": bookshelf.user_id,
            "name": bookshelf.name,
            "description": bookshelf.description,
            "is_public": bookshelf.is_public,
            "is_default": bookshelf.is_default,
            "cover_image": bookshelf.cover_image,
            "created_at": bookshelf.created_at,
            "updated_at": bookshelf.updated_at,
        }

        # Thêm thông tin người dùng nếu đã load
        if hasattr(bookshelf, "user") and bookshelf.user:
            result["user"] = {
                "id": bookshelf.user.id,
                "username": bookshelf.user.username,
                "display_name": bookshelf.user.display_name,
                "avatar_url": bookshelf.user.avatar_url,
            }

        # Thêm thông tin sách nếu đã load
        if hasattr(bookshelf, "items") and bookshelf.items:
            result["items"] = [
                self._format_bookshelf_item_response(item) for item in bookshelf.items
            ]
            result["item_count"] = len(bookshelf.items)

        return result

    def _format_bookshelf_item_response(self, item) -> Dict[str, Any]:
        """
        Chuyển đổi đối tượng bookshelf item thành response dict.

        Args:
            item: Đối tượng BookshelfItem từ database

        Returns:
            Dict thông tin bookshelf item đã được format
        """
        result = {
            "id": item.id,
            "bookshelf_id": item.bookshelf_id,
            "book_id": item.book_id,
            "added_at": item.added_at,
            "notes": item.notes,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

        # Thêm thông tin sách nếu đã load
        if hasattr(item, "book") and item.book:
            result["book"] = {
                "id": item.book.id,
                "title": item.book.title,
                "cover_thumbnail_url": item.book.cover_thumbnail_url,
                "author_names": (
                    [author.name for author in item.book.authors]
                    if hasattr(item.book, "authors") and item.book.authors
                    else []
                ),
            }

        return result
