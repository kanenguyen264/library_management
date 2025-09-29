from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.user_site.repositories.book_list_repo import BookListRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.user_repo import UserRepository
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
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import check_permission
from app.logs_manager.services.user_activity_log_service import log_user_activity


class BookListService:
    """Service để quản lý danh sách sách của người dùng."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo service với AsyncSession."""
        self.db = db
        self.book_list_repo = BookListRepository(db)
        self.book_repo = BookRepository(db)
        self.user_repo = UserRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    async def create_book_list(
        self, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Tạo danh sách sách mới cho người dùng.

        Args:
            user_id: ID của người dùng
            data: Dữ liệu danh sách sách cần tạo (title, description, is_public)

        Returns:
            Thông tin danh sách sách vừa tạo

        Raises:
            BadRequestException: Nếu tên danh sách không hợp lệ
            ForbiddenException: Nếu người dùng không có quyền tạo danh sách
        """
        with self.profiler.profile("create_book_list"):
            # Kiểm tra người dùng tồn tại
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {user_id}"
                )

            # Làm sạch dữ liệu
            if "title" in data:
                data["title"] = sanitize_html(data["title"])
            if "description" in data:
                data["description"] = sanitize_html(data["description"])

            # Kiểm tra tên danh sách
            if not data.get("title") or len(data["title"]) < 3:
                raise BadRequestException(
                    detail="Tên danh sách phải có ít nhất 3 ký tự"
                )

            # Đếm số lượng danh sách hiện tại của người dùng
            current_lists_count = await self.book_list_repo.count_user_lists(user_id)

            # Kiểm tra giới hạn số lượng danh sách
            if current_lists_count >= 50:  # Giới hạn 50 danh sách/người dùng
                raise BadRequestException(
                    detail="Bạn đã đạt đến giới hạn số lượng danh sách sách"
                )

            # Tạo danh sách mới
            list_data = {
                "user_id": user_id,
                "title": data["title"],
                "description": data.get("description", ""),
                "is_public": data.get("is_public", False),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }

            book_list = await self.book_list_repo.create(list_data)

            # Ghi nhật ký hoạt động người dùng
            await log_user_activity(
                user_id=user_id,
                activity_type="created_book_list",
                activity_details={
                    "book_list_id": book_list.id,
                    "title": book_list.title,
                },
            )

            # Theo dõi số liệu
            self.metrics.track_user_activity("book_list_created")

            # Invalidate cache
            await invalidate_cache(
                namespace="book_lists",
                tags=[f"user:{user_id}:lists", "user_book_lists"],
            )

            return {
                "id": book_list.id,
                "title": book_list.title,
                "description": book_list.description,
                "is_public": book_list.is_public,
                "book_count": 0,
                "created_at": book_list.created_at,
                "updated_at": book_list.updated_at,
            }

    @cached(
        ttl=1800,
        namespace="book_lists",
        tags=["book_list_detail"],
        key_builder=lambda *args, **kwargs: f"book_list:{kwargs.get('list_id')}",
    )
    async def get_book_list(
        self, list_id: int, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin chi tiết của một danh sách sách.

        Args:
            list_id: ID của danh sách
            user_id: ID của người dùng đang xem (để kiểm tra quyền)

        Returns:
            Thông tin chi tiết của danh sách sách

        Raises:
            NotFoundException: Nếu không tìm thấy danh sách
            ForbiddenException: Nếu người dùng không có quyền xem
        """
        with self.profiler.profile("get_book_list"):
            # Lấy thông tin danh sách
            book_list = await self.book_list_repo.get_by_id(list_id)
            if not book_list:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh sách sách với ID {list_id}"
                )

            # Kiểm tra quyền xem danh sách private
            if not book_list.is_public and (
                not user_id or user_id != book_list.user_id
            ):
                raise ForbiddenException(detail="Bạn không có quyền xem danh sách này")

            # Lấy số sách trong danh sách
            book_count = await self.book_list_repo.count_books_in_list(list_id)

            # Lấy thông tin người tạo danh sách
            owner = await self.user_repo.get_by_id(book_list.user_id)

            # Track metrics
            self.metrics.track_user_activity("book_list_viewed")
            if user_id:
                await log_user_activity(
                    user_id=user_id,
                    activity_type="viewed_book_list",
                    activity_details={"book_list_id": list_id},
                )

            return {
                "id": book_list.id,
                "title": book_list.title,
                "description": book_list.description,
                "is_public": book_list.is_public,
                "book_count": book_count,
                "created_at": book_list.created_at,
                "updated_at": book_list.updated_at,
                "owner": (
                    {
                        "id": owner.id,
                        "username": owner.username,
                        "display_name": owner.display_name,
                        "avatar": owner.avatar,
                    }
                    if owner
                    else None
                ),
            }

    @cached(
        ttl=1800,
        namespace="book_lists",
        tags=["user_book_lists"],
        key_builder=lambda *args, **kwargs: (
            f"user:{kwargs.get('user_id')}:lists:"
            f"{kwargs.get('skip')}:{kwargs.get('limit')}"
        ),
    )
    async def get_user_lists(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        current_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách các danh sách sách của người dùng.

        Args:
            user_id: ID của người dùng sở hữu danh sách
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            current_user_id: ID của người dùng đang xem (để kiểm tra quyền)

        Returns:
            Dict chứa danh sách các danh sách sách và tổng số

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        with self.profiler.profile("get_user_lists"):
            # Kiểm tra người dùng tồn tại
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {user_id}"
                )

            # Xác định xem có hiển thị danh sách private không
            show_private = current_user_id == user_id

            # Lấy danh sách
            lists = await self.book_list_repo.get_user_lists(
                user_id=user_id, skip=skip, limit=limit, include_private=show_private
            )

            # Đếm tổng số
            total = await self.book_list_repo.count_user_lists(
                user_id=user_id, include_private=show_private
            )

            # Lấy số lượng sách trong mỗi danh sách
            result_lists = []
            for book_list in lists:
                book_count = await self.book_list_repo.count_books_in_list(book_list.id)
                result_lists.append(
                    {
                        "id": book_list.id,
                        "title": book_list.title,
                        "description": book_list.description,
                        "is_public": book_list.is_public,
                        "book_count": book_count,
                        "created_at": book_list.created_at,
                        "updated_at": book_list.updated_at,
                    }
                )

            # Track metrics
            self.metrics.track_user_activity("user_book_lists_viewed")

            return {"items": result_lists, "total": total}

    @cached(
        ttl=1800,
        namespace="book_lists",
        tags=["popular_book_lists"],
        key_builder=lambda *args, **kwargs: f"popular_book_lists:{kwargs.get('limit')}",
    )
    async def get_popular_lists(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các danh sách sách phổ biến.

        Args:
            limit: Số lượng danh sách trả về

        Returns:
            Danh sách các danh sách sách phổ biến
        """
        with self.profiler.profile("get_popular_lists"):
            popular_lists = await self.book_list_repo.get_popular_lists(limit)

            result = []
            for book_list in popular_lists:
                # Lấy thông tin người tạo danh sách
                owner = await self.user_repo.get_by_id(book_list.user_id)

                result.append(
                    {
                        "id": book_list.id,
                        "title": book_list.title,
                        "description": book_list.description,
                        "book_count": (
                            book_list.book_count
                            if hasattr(book_list, "book_count")
                            else 0
                        ),
                        "created_at": book_list.created_at,
                        "updated_at": book_list.updated_at,
                        "owner": (
                            {
                                "id": owner.id,
                                "username": owner.username,
                                "display_name": owner.display_name,
                                "avatar": owner.avatar,
                            }
                            if owner
                            else None
                        ),
                    }
                )

            # Track metrics
            self.metrics.track_user_activity("popular_book_lists_viewed")

            return result

    @invalidate_cache(
        namespace="book_lists",
        tags=lambda *args, **kwargs: [
            f"book_list:{kwargs.get('list_id')}",
            f"user:{kwargs.get('user_id')}:lists",
            "user_book_lists",
        ],
    )
    async def update_book_list(
        self, list_id: int, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin danh sách sách.

        Args:
            list_id: ID của danh sách
            user_id: ID của người dùng
            data: Dữ liệu cập nhật

        Returns:
            Thông tin danh sách sau khi cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy danh sách
            ForbiddenException: Nếu người dùng không phải chủ sở hữu
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        with self.profiler.profile("update_book_list"):
            # Kiểm tra danh sách tồn tại
            book_list = await self.book_list_repo.get_by_id(list_id)
            if not book_list:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh sách sách với ID {list_id}"
                )

            # Kiểm tra quyền chỉnh sửa
            if book_list.user_id != user_id:
                raise ForbiddenException(
                    detail="Bạn không có quyền chỉnh sửa danh sách này"
                )

            # Làm sạch dữ liệu
            update_data = {}
            if "title" in data:
                if not data["title"] or len(data["title"]) < 3:
                    raise BadRequestException(
                        detail="Tên danh sách phải có ít nhất 3 ký tự"
                    )
                update_data["title"] = sanitize_html(data["title"])

            if "description" in data:
                update_data["description"] = sanitize_html(data["description"])

            if "is_public" in data:
                update_data["is_public"] = bool(data["is_public"])

            if not update_data:
                raise BadRequestException(detail="Không có thông tin nào được cập nhật")

            # Cập nhật thời gian sửa đổi
            update_data["updated_at"] = datetime.now(timezone.utc)

            # Cập nhật danh sách
            updated_list = await self.book_list_repo.update(list_id, update_data)

            # Ghi nhật ký hoạt động
            await log_user_activity(
                user_id=user_id,
                activity_type="updated_book_list",
                activity_details={
                    "book_list_id": list_id,
                    "updated_fields": list(update_data.keys()),
                },
            )

            # Track metrics
            self.metrics.track_user_activity("book_list_updated")

            return {
                "id": updated_list.id,
                "title": updated_list.title,
                "description": updated_list.description,
                "is_public": updated_list.is_public,
                "updated_at": updated_list.updated_at,
            }

    @invalidate_cache(
        namespace="book_lists",
        tags=lambda *args, **kwargs: [
            f"book_list:{kwargs.get('list_id')}",
            f"user:{kwargs.get('user_id')}:lists",
            "user_book_lists",
            "books_in_list",
            "book_lists_for_book",
            "popular_book_lists",
        ],
    )
    async def delete_book_list(self, list_id: int, user_id: int) -> Dict[str, Any]:
        """
        Xóa danh sách sách.

        Args:
            list_id: ID của danh sách
            user_id: ID của người dùng

        Returns:
            Thông báo xóa thành công

        Raises:
            NotFoundException: Nếu không tìm thấy danh sách
            ForbiddenException: Nếu người dùng không phải chủ sở hữu
        """
        with self.profiler.profile("delete_book_list"):
            # Kiểm tra danh sách tồn tại
            book_list = await self.book_list_repo.get_by_id(list_id)
            if not book_list:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh sách sách với ID {list_id}"
                )

            # Kiểm tra quyền xóa
            if book_list.user_id != user_id:
                raise ForbiddenException(detail="Bạn không có quyền xóa danh sách này")

            # Xóa tất cả sách khỏi danh sách trước
            await self.book_list_repo.remove_all_books(list_id)

            # Xóa danh sách
            await self.book_list_repo.delete(list_id)

            # Ghi nhật ký hoạt động
            await log_user_activity(
                user_id=user_id,
                activity_type="deleted_book_list",
                activity_details={"book_list_id": list_id, "title": book_list.title},
            )

            # Track metrics
            self.metrics.track_user_activity("book_list_deleted")

            return {"message": "Đã xóa danh sách sách thành công"}

    @invalidate_cache(
        namespace="book_lists",
        tags=lambda *args, **kwargs: [
            f"book_list:{kwargs.get('list_id')}",
            f"books_in_list:{kwargs.get('list_id')}",
            f"book_lists_for_book:{kwargs.get('book_id')}",
        ],
    )
    async def add_book_to_list(
        self, list_id: int, book_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Thêm sách vào danh sách.

        Args:
            list_id: ID của danh sách
            book_id: ID của sách
            user_id: ID của người dùng

        Returns:
            Thông báo thêm thành công

        Raises:
            NotFoundException: Nếu không tìm thấy danh sách hoặc sách
            ForbiddenException: Nếu người dùng không phải chủ sở hữu
            BadRequestException: Nếu sách đã có trong danh sách
        """
        with self.profiler.profile("add_book_to_list"):
            # Kiểm tra danh sách tồn tại
            book_list = await self.book_list_repo.get_by_id(list_id)
            if not book_list:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh sách sách với ID {list_id}"
                )

            # Kiểm tra quyền chỉnh sửa
            if book_list.user_id != user_id:
                raise ForbiddenException(
                    detail="Bạn không có quyền chỉnh sửa danh sách này"
                )

            # Kiểm tra sách tồn tại
            book = await self.book_repo.get_by_id(book_id)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Kiểm tra sách đã có trong danh sách chưa
            if await self.book_list_repo.is_book_in_list(list_id, book_id):
                raise BadRequestException(detail="Sách này đã có trong danh sách")

            # Đếm số sách hiện tại trong danh sách
            current_book_count = await self.book_list_repo.count_books_in_list(list_id)

            # Kiểm tra giới hạn số lượng sách trong danh sách
            if current_book_count >= 100:  # Giới hạn 100 sách/danh sách
                raise BadRequestException(
                    detail="Danh sách đã đạt đến giới hạn số lượng sách"
                )

            # Thêm sách vào danh sách
            await self.book_list_repo.add_book(list_id, book_id)

            # Cập nhật thời gian sửa đổi của danh sách
            await self.book_list_repo.update(list_id, {"updated_at": datetime.now(timezone.utc)})

            # Ghi nhật ký hoạt động
            await log_user_activity(
                user_id=user_id,
                activity_type="added_book_to_list",
                activity_details={"book_list_id": list_id, "book_id": book_id},
            )

            # Track metrics
            self.metrics.track_user_activity("book_added_to_list")

            return {
                "message": "Đã thêm sách vào danh sách thành công",
                "book_id": book_id,
                "book_list_id": list_id,
            }

    @invalidate_cache(
        namespace="book_lists",
        tags=lambda *args, **kwargs: [
            f"book_list:{kwargs.get('list_id')}",
            f"books_in_list:{kwargs.get('list_id')}",
            f"book_lists_for_book:{kwargs.get('book_id')}",
        ],
    )
    async def remove_book_from_list(
        self, list_id: int, book_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Xóa sách khỏi danh sách.

        Args:
            list_id: ID của danh sách
            book_id: ID của sách
            user_id: ID của người dùng

        Returns:
            Thông báo xóa thành công

        Raises:
            NotFoundException: Nếu không tìm thấy danh sách hoặc sách không có trong danh sách
            ForbiddenException: Nếu người dùng không phải chủ sở hữu
        """
        with self.profiler.profile("remove_book_from_list"):
            # Kiểm tra danh sách tồn tại
            book_list = await self.book_list_repo.get_by_id(list_id)
            if not book_list:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh sách sách với ID {list_id}"
                )

            # Kiểm tra quyền chỉnh sửa
            if book_list.user_id != user_id:
                raise ForbiddenException(
                    detail="Bạn không có quyền chỉnh sửa danh sách này"
                )

            # Kiểm tra sách có trong danh sách không
            if not await self.book_list_repo.is_book_in_list(list_id, book_id):
                raise NotFoundException(detail="Sách này không có trong danh sách")

            # Xóa sách khỏi danh sách
            await self.book_list_repo.remove_book(list_id, book_id)

            # Cập nhật thời gian sửa đổi của danh sách
            await self.book_list_repo.update(list_id, {"updated_at": datetime.now(timezone.utc)})

            # Ghi nhật ký hoạt động
            await log_user_activity(
                user_id=user_id,
                activity_type="removed_book_from_list",
                activity_details={"book_list_id": list_id, "book_id": book_id},
            )

            # Track metrics
            self.metrics.track_user_activity("book_removed_from_list")

            return {
                "message": "Đã xóa sách khỏi danh sách thành công",
                "book_id": book_id,
                "book_list_id": list_id,
            }

    @cached(
        ttl=1800,
        namespace="book_lists",
        tags=["books_in_list"],
        key_builder=lambda *args, **kwargs: (
            f"books_in_list:{kwargs.get('list_id')}:"
            f"{kwargs.get('skip')}:{kwargs.get('limit')}"
        ),
    )
    async def get_books_in_list(
        self,
        list_id: int,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách sách trong một danh sách.

        Args:
            list_id: ID của danh sách
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            user_id: ID của người dùng đang xem (để kiểm tra quyền)

        Returns:
            Dict chứa thông tin danh sách và các sách trong đó

        Raises:
            NotFoundException: Nếu không tìm thấy danh sách
            ForbiddenException: Nếu người dùng không có quyền xem
        """
        with self.profiler.profile("get_books_in_list"):
            # Kiểm tra danh sách tồn tại
            book_list = await self.book_list_repo.get_by_id(list_id)
            if not book_list:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh sách sách với ID {list_id}"
                )

            # Kiểm tra quyền xem danh sách private
            if not book_list.is_public and (
                not user_id or user_id != book_list.user_id
            ):
                raise ForbiddenException(detail="Bạn không có quyền xem danh sách này")

            # Lấy thông tin người tạo danh sách
            owner = await self.user_repo.get_by_id(book_list.user_id)

            # Lấy sách trong danh sách
            books = await self.book_list_repo.get_books_in_list(list_id, skip, limit)

            # Đếm tổng số sách trong danh sách
            total = await self.book_list_repo.count_books_in_list(list_id)

            # Track metrics
            self.metrics.track_user_activity("books_in_list_viewed")

            return {
                "list": {
                    "id": book_list.id,
                    "title": book_list.title,
                    "description": book_list.description,
                    "is_public": book_list.is_public,
                    "created_at": book_list.created_at,
                    "updated_at": book_list.updated_at,
                    "owner": (
                        {
                            "id": owner.id,
                            "username": owner.username,
                            "display_name": owner.display_name,
                            "avatar": owner.avatar,
                        }
                        if owner
                        else None
                    ),
                },
                "books": [
                    {
                        "id": book.id,
                        "title": book.title,
                        "slug": book.slug,
                        "cover_image": book.cover_image,
                        "author_name": (
                            book.author_name if hasattr(book, "author_name") else None
                        ),
                        "avg_rating": (
                            book.avg_rating if hasattr(book, "avg_rating") else None
                        ),
                        "added_at": (
                            book.added_at if hasattr(book, "added_at") else None
                        ),
                    }
                    for book in books
                ],
                "total": total,
            }

    @cached(
        ttl=1800,
        namespace="book_lists",
        tags=["book_lists_for_book"],
        key_builder=lambda *args, **kwargs: (
            f"book_lists_for_book:{kwargs.get('book_id')}:"
            f"{kwargs.get('user_id', 'public')}"
        ),
    )
    async def get_lists_containing_book(
        self, book_id: int, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các danh sách chứa một sách cụ thể.

        Args:
            book_id: ID của sách
            user_id: ID của người dùng đang xem (để bao gồm danh sách private)

        Returns:
            Danh sách các danh sách chứa sách

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        with self.profiler.profile("get_lists_containing_book"):
            # Kiểm tra sách tồn tại
            book = await self.book_repo.get_by_id(book_id)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Lấy các danh sách chứa sách
            lists = await self.book_list_repo.get_lists_containing_book(
                book_id, user_id
            )

            # Track metrics
            self.metrics.track_user_activity("book_lists_for_book_viewed")

            result = []
            for book_list in lists:
                # Lấy thông tin người tạo danh sách
                owner = await self.user_repo.get_by_id(book_list.user_id)

                result.append(
                    {
                        "id": book_list.id,
                        "title": book_list.title,
                        "description": book_list.description,
                        "is_public": book_list.is_public,
                        "book_count": (
                            book_list.book_count
                            if hasattr(book_list, "book_count")
                            else 0
                        ),
                        "owner": (
                            {
                                "id": owner.id,
                                "username": owner.username,
                                "display_name": owner.display_name,
                                "avatar": owner.avatar,
                            }
                            if owner
                            else None
                        ),
                    }
                )

            return result
