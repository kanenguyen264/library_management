from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.book_series_repo import BookSeriesRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
)
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import check_permission


class BookSeriesService:
    """Service để quản lý series sách."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo service với AsyncSession."""
        self.db = db
        self.series_repo = BookSeriesRepository(db)
        self.book_repo = BookRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    async def create_series(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tạo bộ truyện mới.

        Args:
            data: Dữ liệu bộ truyện

        Returns:
            Thông tin bộ truyện đã tạo

        Raises:
            BadRequestException: Nếu thiếu thông tin bắt buộc hoặc tên đã tồn tại
        """
        # Kiểm tra các trường bắt buộc
        required_fields = ["name"]
        for field in required_fields:
            if field not in data:
                raise BadRequestException(detail=f"Thiếu trường {field}")

        # Kiểm tra xem bộ truyện đã tồn tại chưa
        existing = await self.series_repo.get_series_by_name(data["name"])
        if existing:
            raise BadRequestException(detail=f"Bộ truyện '{data['name']}' đã tồn tại")

        # Tạo bộ truyện
        series = await self.series_repo.create_series(data)

        # Log admin activity if admin_id is provided
        if "admin_id" in data:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=data["admin_id"],
                        activity_type="CREATE",
                        entity_type="BOOK_SERIES",
                        entity_id=series.id,
                        description=f"Created book series: {series.name}",
                        metadata={
                            "series_name": series.name,
                            "is_completed": series.is_completed,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {
            "id": series.id,
            "name": series.name,
            "description": series.description,
            "cover_image": series.cover_image,
            "total_books": series.total_books,
            "is_completed": series.is_completed,
            "created_at": series.created_at,
            "updated_at": series.updated_at,
        }

    @cached(
        ttl=3600,
        namespace="book_series",
        tags=["book_series_detail"],
        key_builder=lambda *args, **kwargs: f"book_series:{kwargs.get('series_id')}",
    )
    async def get_series(
        self, series_id: int, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin chi tiết của một series sách.

        Args:
            series_id: ID của series
            user_id: ID người dùng (để kiểm tra quyền)

        Returns:
            Thông tin chi tiết của series

        Raises:
            NotFoundException: Nếu không tìm thấy series
            ForbiddenException: Nếu series chưa xuất bản và người dùng không có quyền xem
        """
        with self.profiler.profile("get_series"):
            series = await self.series_repo.get_by_id(series_id)

            if not series:
                raise NotFoundException(
                    detail=f"Không tìm thấy series với ID {series_id}"
                )

            # Kiểm tra quyền truy cập series chưa xuất bản
            if series.status != "published" and (
                not user_id
                or not await check_permission(
                    user_id, "read_unpublished_series", series_id
                )
            ):
                raise ForbiddenException(detail="Bạn không có quyền xem series này")

            # Lấy danh sách sách trong series
            books = await self.series_repo.get_books_in_series(series_id)

            # Format kết quả
            result = {
                "id": series.id,
                "title": series.title,
                "slug": series.slug,
                "description": series.description,
                "cover_image": series.cover_image,
                "status": series.status,
                "created_at": series.created_at,
                "updated_at": series.updated_at,
                "books": [
                    {
                        "id": book.id,
                        "title": book.title,
                        "slug": book.slug,
                        "cover_image": book.cover_image,
                        "order_in_series": book.order_in_series,
                        "status": book.status,
                    }
                    for book in books
                ],
            }

            # Track metric
            self.metrics.track_user_activity("book_series_viewed")

            return result

    @cached(
        ttl=1800,
        namespace="book_series",
        tags=["book_series_list"],
        key_builder=lambda *args, **kwargs: (
            f"book_series_list:{kwargs.get('status', 'published')}:"
            f"{kwargs.get('sort_by', 'created_at')}:"
            f"{kwargs.get('sort_order', 'desc')}:"
            f"{kwargs.get('skip')}:{kwargs.get('limit')}"
        ),
    )
    async def list_series(
        self,
        skip: int = 0,
        limit: int = 20,
        search_term: Optional[str] = None,
        status: str = "published",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách series sách theo các tiêu chí lọc và sắp xếp.

        Args:
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            search_term: Từ khóa tìm kiếm
            status: Trạng thái series (published, draft, etc)
            sort_by: Trường để sắp xếp
            sort_order: Thứ tự sắp xếp (asc, desc)
            user_id: ID người dùng (để kiểm tra quyền)

        Returns:
            Dict chứa danh sách series và tổng số series thỏa mãn điều kiện
        """
        with self.profiler.profile("list_series"):
            # Kiểm tra quyền xem series chưa xuất bản
            if status != "published" and (
                not user_id
                or not await check_permission(user_id, "view_unpublished_series")
            ):
                raise ForbiddenException(
                    detail="Bạn không có quyền xem danh sách series chưa xuất bản"
                )

            # Tìm kiếm series theo các tiêu chí
            series_list = await self.series_repo.list_series(
                skip=skip,
                limit=limit,
                search_term=search_term,
                status=status,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            # Đếm tổng số series thỏa mãn điều kiện
            total = await self.series_repo.count_series(
                search_term=search_term, status=status
            )

            # Format kết quả
            result = {
                "items": [
                    {
                        "id": series.id,
                        "title": series.title,
                        "slug": series.slug,
                        "description": series.description,
                        "cover_image": series.cover_image,
                        "status": series.status,
                        "book_count": (
                            series.book_count if hasattr(series, "book_count") else 0
                        ),
                        "created_at": series.created_at,
                        "updated_at": series.updated_at,
                    }
                    for series in series_list
                ],
                "total": total,
            }

            # Track metric
            self.metrics.track_user_activity("book_series_list_viewed")

            if search_term:
                self.metrics.track_search_term("book_series_search", search_term)

            return result

    @cached(
        ttl=3600,
        namespace="book_series",
        tags=["popular_series"],
        key_builder=lambda *args, **kwargs: f"popular_series:{kwargs.get('limit')}",
    )
    async def get_popular_series(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách series phổ biến.

        Args:
            limit: Số lượng series trả về

        Returns:
            Danh sách series phổ biến
        """
        with self.profiler.profile("get_popular_series"):
            series_list = await self.series_repo.get_popular_series(limit)

            # Track metric
            self.metrics.track_user_activity("popular_series_viewed")

            return [
                {
                    "id": series.id,
                    "title": series.title,
                    "slug": series.slug,
                    "description": series.description,
                    "cover_image": series.cover_image,
                    "book_count": (
                        series.book_count if hasattr(series, "book_count") else 0
                    ),
                    "created_at": series.created_at,
                    "updated_at": series.updated_at,
                }
                for series in series_list
            ]

    @cached(
        ttl=1800,
        namespace="books",
        tags=["series_books"],
        key_builder=lambda *args, **kwargs: (
            f"series_books:{kwargs.get('series_id')}:"
            f"{kwargs.get('skip')}:{kwargs.get('limit')}"
        ),
    )
    async def get_books_in_series(
        self, series_id: int, skip: int = 0, limit: int = 50
    ) -> Dict[str, Any]:
        """
        Lấy danh sách sách trong một series.

        Args:
            series_id: ID của series
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Dict chứa danh sách sách và tổng số

        Raises:
            NotFoundException: Nếu không tìm thấy series
        """
        with self.profiler.profile("get_books_in_series"):
            # Kiểm tra series tồn tại
            series = await self.series_repo.get_by_id(series_id)
            if not series:
                raise NotFoundException(
                    detail=f"Không tìm thấy series với ID {series_id}"
                )

            # Lấy sách trong series
            books = await self.series_repo.get_books_in_series(
                series_id=series_id, skip=skip, limit=limit
            )

            # Đếm tổng số sách trong series
            total = await self.series_repo.count_books_in_series(series_id)

            # Track metric
            self.metrics.track_user_activity("series_books_viewed")

            return {
                "series": {
                    "id": series.id,
                    "title": series.title,
                    "slug": series.slug,
                    "description": series.description,
                    "cover_image": series.cover_image,
                    "status": series.status,
                },
                "books": [
                    {
                        "id": book.id,
                        "title": book.title,
                        "slug": book.slug,
                        "cover_image": book.cover_image,
                        "status": book.status,
                        "order_in_series": book.order_in_series,
                    }
                    for book in books
                ],
                "total": total,
            }

    @cached(
        ttl=1800,
        namespace="book_series",
        tags=["book_in_series"],
        key_builder=lambda *args, **kwargs: f"book_in_series:{kwargs.get('book_id')}",
    )
    async def get_series_for_book(self, book_id: int) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin series mà sách thuộc về.

        Args:
            book_id: ID của sách

        Returns:
            Thông tin series hoặc None nếu sách không thuộc series nào

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        with self.profiler.profile("get_series_for_book"):
            # Kiểm tra sách tồn tại
            book = await self.book_repo.get_by_id(book_id)
            if not book:
                raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

            # Lấy series của sách
            series = await self.series_repo.get_series_by_book(book_id)
            if not series:
                return None

            # Lấy các sách khác trong series
            other_books = await self.series_repo.get_books_in_series(series.id)

            # Track metric
            self.metrics.track_user_activity("book_series_info_viewed")

            return {
                "id": series.id,
                "title": series.title,
                "slug": series.slug,
                "description": series.description,
                "cover_image": series.cover_image,
                "status": series.status,
                "created_at": series.created_at,
                "updated_at": series.updated_at,
                "current_book": {
                    "id": book.id,
                    "title": book.title,
                    "order_in_series": (
                        book.order_in_series
                        if hasattr(book, "order_in_series")
                        else None
                    ),
                },
                "books": [
                    {
                        "id": b.id,
                        "title": b.title,
                        "slug": b.slug,
                        "cover_image": b.cover_image,
                        "order_in_series": b.order_in_series,
                        "is_current": b.id == book_id,
                    }
                    for b in other_books
                ],
            }

    async def update_series(
        self, series_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin bộ truyện.

        Args:
            series_id: ID của bộ truyện
            data: Dữ liệu cập nhật

        Returns:
            Thông tin bộ truyện đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy bộ truyện
            BadRequestException: Nếu tên mới đã tồn tại
        """
        # Kiểm tra bộ truyện tồn tại
        series = await self.series_repo.get_series_by_id(series_id)
        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy bộ truyện với ID {series_id}"
            )

        # Nếu đổi tên, kiểm tra tên mới đã tồn tại chưa
        if "name" in data and data["name"] != series.name:
            existing = await self.series_repo.get_series_by_name(data["name"])
            if existing and existing.id != series_id:
                raise BadRequestException(
                    detail=f"Bộ truyện '{data['name']}' đã tồn tại"
                )

        # Cập nhật
        updated = await self.series_repo.update_series(series_id, data)

        # Log admin activity if admin_id is provided
        if "admin_id" in data:
            try:
                # Track which fields were updated
                updated_fields = list(data.keys())
                (
                    updated_fields.remove("admin_id")
                    if "admin_id" in updated_fields
                    else None
                )

                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=data["admin_id"],
                        activity_type="UPDATE",
                        entity_type="BOOK_SERIES",
                        entity_id=series_id,
                        description=f"Updated book series: {updated.name}",
                        metadata={
                            "series_name": updated.name,
                            "updated_fields": updated_fields,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "cover_image": updated.cover_image,
            "total_books": updated.total_books,
            "is_completed": updated.is_completed,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
        }

    async def delete_series(self, series_id: int) -> Dict[str, Any]:
        """
        Xóa bộ truyện.

        Args:
            series_id: ID của bộ truyện

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy bộ truyện
        """
        # Kiểm tra bộ truyện tồn tại
        series = await self.series_repo.get_series_by_id(series_id)
        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy bộ truyện với ID {series_id}"
            )

        # Xóa bộ truyện
        await self.series_repo.delete_series(series_id)

        # Log admin activity if admin_id is available in context
        if hasattr(self, "admin_id") and self.admin_id:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=self.admin_id,
                        activity_type="DELETE",
                        entity_type="BOOK_SERIES",
                        entity_id=series_id,
                        description=f"Deleted book series: {series.name}",
                        metadata={"series_name": series.name},
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {"message": "Đã xóa bộ truyện thành công"}

    async def add_book_to_series(
        self, series_id: int, book_id: int, position: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Thêm sách vào bộ truyện.

        Args:
            series_id: ID của bộ truyện
            book_id: ID của sách
            position: Vị trí trong bộ truyện (tùy chọn)

        Returns:
            Thông tin mục đã thêm

        Raises:
            NotFoundException: Nếu không tìm thấy bộ truyện
            BadRequestException: Nếu sách đã có trong bộ truyện
        """
        # Kiểm tra bộ truyện tồn tại
        series = await self.series_repo.get_series_by_id(series_id)
        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy bộ truyện với ID {series_id}"
            )

        # Kiểm tra sách đã có trong bộ truyện chưa
        existing_item = await self.series_repo.get_series_item_by_book(
            series_id, book_id
        )
        if existing_item:
            raise BadRequestException(detail="Sách này đã có trong bộ truyện")

        # Nếu không có position, lấy vị trí cuối cùng
        if position is None:
            items_count = await self.series_repo.count_series_items(series_id)
            position = items_count + 1

        # Tạo mục mới
        item_data = {"series_id": series_id, "book_id": book_id, "position": position}

        item = await self.series_repo.create_series_item(item_data)

        # Cập nhật tổng số sách trong series
        await self.series_repo.update_series_total_books(series_id)

        # Log admin activity if admin_id is available in context
        if hasattr(self, "admin_id") and self.admin_id:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=self.admin_id,
                        activity_type="ADD",
                        entity_type="BOOK_TO_SERIES",
                        entity_id=item.id,
                        description=f"Added book to series: {series.name}",
                        metadata={
                            "series_id": series_id,
                            "series_name": series.name,
                            "book_id": book_id,
                            "position": position,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {
            "id": item.id,
            "series_id": item.series_id,
            "book_id": item.book_id,
            "position": item.position,
        }

    async def update_series_item(
        self, item_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin mục trong bộ truyện.

        Args:
            item_id: ID của mục
            data: Dữ liệu cập nhật

        Returns:
            Thông tin mục đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy mục
        """
        # Kiểm tra mục tồn tại
        item = await self.series_repo.get_series_item_by_id(item_id)
        if not item:
            raise NotFoundException(detail=f"Không tìm thấy mục với ID {item_id}")

        # Cập nhật
        updated = await self.series_repo.update_series_item(item_id, data)

        # Log admin activity if admin_id is provided
        if "admin_id" in data:
            try:
                # Get series info for logging
                series = await self.series_repo.get_series_by_id(item.series_id)

                # Track which fields were updated
                updated_fields = list(data.keys())
                (
                    updated_fields.remove("admin_id")
                    if "admin_id" in updated_fields
                    else None
                )

                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=data["admin_id"],
                        activity_type="UPDATE",
                        entity_type="BOOK_SERIES_ITEM",
                        entity_id=item_id,
                        description=f"Updated book position in series: {series.name if series else 'Unknown'}",
                        metadata={
                            "series_id": item.series_id,
                            "series_name": series.name if series else "Unknown",
                            "book_id": item.book_id,
                            "updated_fields": updated_fields,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {
            "id": updated.id,
            "series_id": updated.series_id,
            "book_id": updated.book_id,
            "position": updated.position,
        }

    async def remove_book_from_series(
        self, series_id: int, book_id: int
    ) -> Dict[str, Any]:
        """
        Xóa sách khỏi bộ truyện.

        Args:
            series_id: ID của bộ truyện
            book_id: ID của sách

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy bộ truyện hoặc sách không có trong bộ truyện
        """
        # Kiểm tra bộ truyện tồn tại
        series = await self.series_repo.get_series_by_id(series_id)
        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy bộ truyện với ID {series_id}"
            )

        # Kiểm tra sách có trong bộ truyện không
        item = await self.series_repo.get_series_item_by_book(series_id, book_id)
        if not item:
            raise NotFoundException(detail="Sách này không có trong bộ truyện")

        # Xóa mục
        await self.series_repo.delete_series_item(item.id)

        # Cập nhật tổng số sách trong series
        await self.series_repo.update_series_total_books(series_id)

        # Log admin activity if admin_id is available in context
        if hasattr(self, "admin_id") and self.admin_id:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=self.admin_id,
                        activity_type="REMOVE",
                        entity_type="BOOK_FROM_SERIES",
                        entity_id=item.id,
                        description=f"Removed book from series: {series.name}",
                        metadata={
                            "series_id": series_id,
                            "series_name": series.name,
                            "book_id": book_id,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {"message": "Đã xóa sách khỏi bộ truyện thành công"}

    async def list_series_books(
        self, series_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách sách trong bộ truyện.

        Args:
            series_id: ID của bộ truyện
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách sách và thông tin phân trang

        Raises:
            NotFoundException: Nếu không tìm thấy bộ truyện
        """
        # Kiểm tra bộ truyện tồn tại
        series = await self.series_repo.get_series_by_id(series_id)
        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy bộ truyện với ID {series_id}"
            )

        items = await self.series_repo.list_series_items(series_id, skip, limit)
        total = await self.series_repo.count_series_items(series_id)

        return {
            "items": [
                {
                    "id": item.id,
                    "book_id": item.book_id,
                    "position": item.position,
                    "book": (
                        {
                            "id": item.book.id,
                            "title": item.book.title,
                            "cover_image": item.book.cover_image,
                            "author_names": (
                                item.book.author_names
                                if hasattr(item.book, "author_names")
                                else None
                            ),
                            "avg_rating": item.book.avg_rating,
                            "is_published": item.book.is_published,
                        }
                        if hasattr(item, "book") and item.book
                        else None
                    ),
                }
                for item in items
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
