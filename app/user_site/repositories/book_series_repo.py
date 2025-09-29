from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.book_series import BookSeries, BookSeriesItem
from app.core.exceptions import NotFoundException


class BookSeriesRepository:
    """Repository cho các thao tác với series sách (BookSeries) và các mục trong series (BookSeriesItem)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    # --- BookSeries methods --- #

    async def create_series(self, series_data: Dict[str, Any]) -> BookSeries:
        """Tạo một series sách mới.

        Args:
            series_data: Dữ liệu series (name, description, cover_image_url, total_books).

        Returns:
            Đối tượng BookSeries đã được tạo.
        """
        allowed_fields = {
            "name",
            "description",
            "cover_image_url",
            "total_books",
        }  # total_books thường được tính tự động
        filtered_data = {k: v for k, v in series_data.items() if k in allowed_fields}
        series = BookSeries(**filtered_data)
        self.db.add(series)
        await self.db.commit()
        await self.db.refresh(series)
        return series

    async def get_series_by_id(
        self, series_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[BookSeries]:
        """Lấy series sách theo ID.

        Args:
            series_id: ID của series.
            with_relations: Danh sách quan hệ cần load (ví dụ: ["items", "items.book"]).

        Returns:
            Đối tượng BookSeries hoặc None.
        """
        query = select(BookSeries).where(BookSeries.id == series_id)

        if with_relations:
            options = []
            if "items" in with_relations:
                items_option = selectinload(BookSeries.items)
                if "items.book" in with_relations:
                    items_option = items_option.selectinload(BookSeriesItem.book)
                options.append(items_option)
            elif "items.book" in with_relations:
                items_option = selectinload(BookSeries.items).selectinload(
                    BookSeriesItem.book
                )
                options.append(items_option)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_series_by_name(self, name: str) -> Optional[BookSeries]:
        """Lấy series sách theo tên (phân biệt chữ hoa/thường)."""
        query = select(BookSeries).where(BookSeries.name == name)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_series(
        self, series_id: int, series_data: Dict[str, Any]
    ) -> BookSeries:
        """Cập nhật thông tin series sách.

        Args:
            series_id: ID của series cần cập nhật.
            series_data: Dữ liệu cập nhật (name, description, cover_image_url).

        Returns:
            Đối tượng BookSeries đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy series.
        """
        series = await self.get_series_by_id(series_id)
        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy series sách với ID {series_id}"
            )

        allowed_fields = {"name", "description", "cover_image_url"}
        for key, value in series_data.items():
            if key in allowed_fields:
                setattr(series, key, value)

        await self.db.commit()
        await self.db.refresh(series)
        return series

    async def delete_series(self, series_id: int) -> bool:
        """Xóa series sách. Lưu ý: Cần xử lý các BookSeriesItem liên quan.

        Args:
            series_id: ID của series cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        series = await self.get_series_by_id(series_id)
        if not series:
            return False

        # Cân nhắc xóa các item liên quan nếu không có cascade
        # await self.db.execute(delete(BookSeriesItem).where(BookSeriesItem.series_id == series_id))

        await self.db.delete(series)
        await self.db.commit()
        return True

    async def list_series(
        self,
        skip: int = 0,
        limit: int = 20,
        search_query: Optional[str] = None,
        sort_by: str = "name",
        sort_desc: bool = False,
        with_relations: Optional[List[str]] = None,
    ) -> List[BookSeries]:
        """Liệt kê danh sách series sách với tìm kiếm, sắp xếp, phân trang.

        Args:
            skip, limit: Phân trang.
            search_query: Từ khóa tìm kiếm (name, description).
            sort_by, sort_desc: Sắp xếp.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách các đối tượng BookSeries.
        """
        query = select(BookSeries)

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    BookSeries.name.ilike(search_pattern),
                    BookSeries.description.ilike(search_pattern),
                )
            )

        sort_attr = getattr(BookSeries, sort_by, BookSeries.name)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "items" in with_relations:
                items_option = selectinload(BookSeries.items)
                if "items.book" in with_relations:
                    items_option = items_option.selectinload(BookSeriesItem.book)
                options.append(items_option)
            elif "items.book" in with_relations:
                items_option = selectinload(BookSeries.items).selectinload(
                    BookSeriesItem.book
                )
                options.append(items_option)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_series(self, search_query: Optional[str] = None) -> int:
        """Đếm số lượng series sách, có thể lọc theo tìm kiếm."""
        query = select(func.count(BookSeries.id))

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    BookSeries.name.ilike(search_pattern),
                    BookSeries.description.ilike(search_pattern),
                )
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    # --- BookSeriesItem methods --- #

    async def create_series_item(self, item_data: Dict[str, Any]) -> BookSeriesItem:
        """Thêm một sách vào series.

        Args:
            item_data: Dữ liệu mục (series_id, book_id, position).

        Returns:
            Đối tượng BookSeriesItem đã được tạo.
        """
        allowed_fields = {"series_id", "book_id", "position"}
        filtered_data = {k: v for k, v in item_data.items() if k in allowed_fields}
        item = BookSeriesItem(**filtered_data)
        self.db.add(item)
        # Cập nhật total_books sau khi commit item thành công
        try:
            await self.db.commit()
            await self.db.refresh(item)
            await self.update_series_total_books(
                item.series_id
            )  # Gọi hàm cập nhật count
            return item
        except IntegrityError:
            await self.db.rollback()
            raise  # Ném lại lỗi nếu có vấn đề (ví dụ: book_id không tồn tại)

    async def get_series_item_by_id(
        self, item_id: int, with_relations: Optional[List[str]] = ["book", "series"]
    ) -> Optional[BookSeriesItem]:
        """Lấy mục series theo ID.

        Args:
            item_id: ID của mục.
            with_relations: Quan hệ cần load.

        Returns:
            Đối tượng BookSeriesItem hoặc None.
        """
        query = select(BookSeriesItem).where(BookSeriesItem.id == item_id)
        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(BookSeriesItem.book))
            if "series" in with_relations:
                options.append(selectinload(BookSeriesItem.series))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_series_item_by_book(
        self,
        series_id: int,
        book_id: int,
        with_relations: Optional[List[str]] = ["book"],
    ) -> Optional[BookSeriesItem]:
        """Lấy mục series theo series_id và book_id.

        Args:
            series_id: ID của series.
            book_id: ID của sách.
            with_relations: Quan hệ cần load.

        Returns:
            Đối tượng BookSeriesItem hoặc None.
        """
        query = select(BookSeriesItem).where(
            BookSeriesItem.series_id == series_id, BookSeriesItem.book_id == book_id
        )
        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(BookSeriesItem.book))
            if "series" in with_relations:
                options.append(selectinload(BookSeriesItem.series))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_series_item(
        self, item_id: int, item_data: Dict[str, Any]
    ) -> BookSeriesItem:
        """Cập nhật thông tin mục series (ví dụ: position).

        Args:
            item_id: ID của mục cần cập nhật.
            item_data: Dữ liệu cập nhật (chỉ position được phép).

        Returns:
            Đối tượng BookSeriesItem đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy mục.
        """
        item = await self.get_series_item_by_id(item_id)
        if not item:
            raise NotFoundException(
                detail=f"Không tìm thấy mục series với ID {item_id}"
            )

        allowed_fields = {"position"}
        for key, value in item_data.items():
            if key in allowed_fields:
                setattr(item, key, value)

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete_series_item(self, item_id: int) -> bool:
        """Xóa mục khỏi series.

        Args:
            item_id: ID của mục cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        item = await self.get_series_item_by_id(item_id)
        if not item:
            return False

        series_id_to_update = item.series_id  # Lưu lại ID để cập nhật count
        await self.db.delete(item)
        await self.db.commit()
        await self.update_series_total_books(
            series_id_to_update
        )  # Cập nhật count sau khi xóa
        return True

    async def list_series_items(
        self,
        series_id: int,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "position",
        sort_desc: bool = False,
        with_relations: Optional[List[str]] = ["book"],
    ) -> List[BookSeriesItem]:
        """Liệt kê các sách trong một series, sắp xếp theo vị trí.

        Args:
            series_id: ID của series.
            skip, limit: Phân trang.
            sort_by, sort_desc: Sắp xếp.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách các đối tượng BookSeriesItem.
        """
        query = select(BookSeriesItem).where(BookSeriesItem.series_id == series_id)

        sort_attr = getattr(BookSeriesItem, sort_by, BookSeriesItem.position)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(BookSeriesItem.book))
            if "series" in with_relations:
                options.append(selectinload(BookSeriesItem.series))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_series_items(self, series_id: int) -> int:
        """Đếm số lượng sách trong series."""
        query = select(func.count(BookSeriesItem.id)).where(
            BookSeriesItem.series_id == series_id
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update_series_total_books(self, series_id: int) -> Optional[BookSeries]:
        """Cập nhật số lượng sách thực tế trong series và lưu vào DB.

        Args:
            series_id: ID của series.

        Returns:
            Đối tượng BookSeries đã cập nhật hoặc None nếu series không tồn tại.
        """
        series = await self.get_series_by_id(series_id)
        if not series:
            # raise NotFoundException(detail=f"Không tìm thấy series sách với ID {series_id}")
            print(
                f"Cảnh báo: Không tìm thấy series {series_id} để cập nhật total_books."
            )
            return None  # Trả về None nếu không tìm thấy series
        # Đếm lại số lượng items
        current_count = await self.count_series_items(series_id)

        if series.total_books != current_count:
            series.total_books = current_count
            await self.db.commit()
            await self.db.refresh(series)
        return series
