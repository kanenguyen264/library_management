from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.bookshelf import Bookshelf, BookshelfItem
from app.core.exceptions import NotFoundException


class BookshelfRepository:
    """Repository cho các thao tác với kệ sách (Bookshelf) và các mục sách trên kệ (BookshelfItem)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    # Bookshelf methods

    async def create_bookshelf(self, bookshelf_data: Dict[str, Any]) -> Bookshelf:
        """Tạo một kệ sách mới cho người dùng.

        Args:
            bookshelf_data: Dữ liệu kệ sách (user_id, name, description, is_public, is_default).

        Returns:
            Đối tượng Bookshelf đã được tạo.
        """
        allowed_fields = {"user_id", "name", "description", "is_public", "is_default"}
        filtered_data = {k: v for k, v in bookshelf_data.items() if k in allowed_fields}
        bookshelf = Bookshelf(**filtered_data)
        self.db.add(bookshelf)
        await self.db.commit()
        await self.db.refresh(bookshelf)
        return bookshelf

    async def get_bookshelf_by_id(
        self, bookshelf_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[Bookshelf]:
        """Lấy kệ sách theo ID.

        Args:
            bookshelf_id: ID của kệ sách.
            with_relations: Danh sách quan hệ cần load (ví dụ: ["user", "items", "items.book"]).

        Returns:
            Đối tượng Bookshelf hoặc None.
        """
        query = select(Bookshelf).where(Bookshelf.id == bookshelf_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Bookshelf.user))
            if "items" in with_relations:
                items_option = selectinload(Bookshelf.items)
                if "items.book" in with_relations:
                    items_option = items_option.selectinload(BookshelfItem.book)
                options.append(items_option)
            elif "items.book" in with_relations:
                items_option = selectinload(Bookshelf.items).selectinload(
                    BookshelfItem.book
                )
                options.append(items_option)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_bookshelf_by_name_and_user(
        self, name: str, user_id: int
    ) -> Optional[Bookshelf]:
        """Lấy kệ sách theo tên và người dùng (kiểm tra trùng lặp)."""
        query = select(Bookshelf).where(
            Bookshelf.name == name, Bookshelf.user_id == user_id
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_bookshelf(
        self, bookshelf_id: int, bookshelf_data: Dict[str, Any]
    ) -> Bookshelf:
        """Cập nhật thông tin kệ sách.

        Args:
            bookshelf_id: ID kệ sách cần cập nhật.
            bookshelf_data: Dữ liệu cập nhật (name, description, is_public).

        Returns:
            Đối tượng Bookshelf đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy kệ sách.
        """
        bookshelf = await self.get_bookshelf_by_id(bookshelf_id)
        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Không cho phép cập nhật is_default qua đây, dùng hàm riêng nếu cần
        allowed_fields = {"name", "description", "is_public"}
        for key, value in bookshelf_data.items():
            if key in allowed_fields:
                setattr(bookshelf, key, value)

        await self.db.commit()
        await self.db.refresh(bookshelf)
        return bookshelf

    async def delete_bookshelf(self, bookshelf_id: int) -> bool:
        """Xóa kệ sách. Lưu ý: Cần xử lý các BookshelfItem liên quan.

        Args:
            bookshelf_id: ID kệ sách cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.

        Raises:
            IntegrityError: Nếu không thể xóa do còn dependencies (nếu không dùng cascade).
        """
        bookshelf = await self.get_bookshelf_by_id(bookshelf_id)
        if not bookshelf:
            return False

        # Không cho xóa kệ mặc định?
        if bookshelf.is_default:
            raise IntegrityError(
                f"Không thể xóa kệ sách mặc định ID {bookshelf_id}",
                params=None,
                orig=None,
            )

        try:
            # Cân nhắc xóa items trước nếu không có cascade
            await self.db.execute(
                delete(BookshelfItem).where(BookshelfItem.bookshelf_id == bookshelf_id)
            )
            await self.db.delete(bookshelf)
            await self.db.commit()
            return True
        except IntegrityError as e:
            await self.db.rollback()
            print(f"IntegrityError deleting bookshelf {bookshelf_id}: {e}")
            raise IntegrityError(
                "Không thể xóa kệ sách do còn dữ liệu liên quan.", orig=e, params=None
            )

    async def list_user_bookshelves(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "name",
        sort_desc: bool = False,
        with_relations: Optional[List[str]] = ["user"],
    ) -> List[Bookshelf]:
        """Liệt kê kệ sách của một người dùng.

        Args:
            user_id: ID người dùng.
            skip, limit: Phân trang.
            sort_by, sort_desc: Sắp xếp.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách Bookshelf.
        """
        query = select(Bookshelf).where(Bookshelf.user_id == user_id)

        sort_attr = getattr(Bookshelf, sort_by, Bookshelf.name)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Bookshelf.user))
            if "items" in with_relations:
                items_option = selectinload(Bookshelf.items)
                if "items.book" in with_relations:
                    items_option = items_option.selectinload(BookshelfItem.book)
                options.append(items_option)
            elif "items.book" in with_relations:
                items_option = selectinload(Bookshelf.items).selectinload(
                    BookshelfItem.book
                )
                options.append(items_option)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def list_public_bookshelves(
        self,
        skip: int = 0,
        limit: int = 20,
        search_query: Optional[str] = None,
        sort_by: str = "name",
        sort_desc: bool = False,
        with_relations: Optional[List[str]] = ["user"],
    ) -> List[Bookshelf]:
        """Liệt kê kệ sách công khai.

        Args:
            skip, limit: Phân trang.
            search_query: Tìm kiếm (name, description).
            sort_by, sort_desc: Sắp xếp.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách Bookshelf công khai.
        """
        query = select(Bookshelf).where(Bookshelf.is_public == True)

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    Bookshelf.name.ilike(search_pattern),
                    Bookshelf.description.ilike(search_pattern),
                )
            )

        sort_attr = getattr(Bookshelf, sort_by, Bookshelf.name)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Bookshelf.user))
            if "items" in with_relations:
                items_option = selectinload(Bookshelf.items)
                if "items.book" in with_relations:
                    items_option = items_option.selectinload(BookshelfItem.book)
                options.append(items_option)
            elif "items.book" in with_relations:
                items_option = selectinload(Bookshelf.items).selectinload(
                    BookshelfItem.book
                )
                options.append(items_option)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_user_bookshelves(self, user_id: int) -> int:
        """Đếm số lượng kệ sách của một người dùng."""
        query = select(func.count(Bookshelf.id)).where(Bookshelf.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def count_public_bookshelves(self, search_query: Optional[str] = None) -> int:
        """Đếm số lượng kệ sách công khai."""
        query = select(func.count(Bookshelf.id)).where(Bookshelf.is_public == True)

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    Bookshelf.name.ilike(search_pattern),
                    Bookshelf.description.ilike(search_pattern),
                )
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    # BookshelfItem methods

    async def create_bookshelf_item(self, item_data: Dict[str, Any]) -> BookshelfItem:
        """Thêm sách vào kệ sách.

        Args:
            item_data: Dữ liệu mục (bookshelf_id, book_id, note).

        Returns:
            Đối tượng BookshelfItem đã tạo.
        """
        allowed_fields = {"bookshelf_id", "book_id", "note"}
        filtered_data = {k: v for k, v in item_data.items() if k in allowed_fields}
        item = BookshelfItem(**filtered_data)
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def get_bookshelf_item_by_id(
        self, item_id: int, with_relations: Optional[List[str]] = ["book", "bookshelf"]
    ) -> Optional[BookshelfItem]:
        """Lấy mục kệ sách theo ID.

        Args:
            item_id: ID của mục.
            with_relations: Quan hệ cần load.

        Returns:
            Đối tượng BookshelfItem hoặc None.
        """
        query = select(BookshelfItem).where(BookshelfItem.id == item_id)
        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(BookshelfItem.book))
            if "bookshelf" in with_relations:
                options.append(selectinload(BookshelfItem.bookshelf))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_bookshelf_item_by_book(
        self,
        bookshelf_id: int,
        book_id: int,
        with_relations: Optional[List[str]] = ["book"],
    ) -> Optional[BookshelfItem]:
        """Lấy mục kệ sách theo bookshelf_id và book_id.

        Args:
            bookshelf_id: ID kệ sách.
            book_id: ID sách.
            with_relations: Quan hệ cần load.

        Returns:
            Đối tượng BookshelfItem hoặc None.
        """
        query = select(BookshelfItem).where(
            BookshelfItem.bookshelf_id == bookshelf_id, BookshelfItem.book_id == book_id
        )
        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(BookshelfItem.book))
            if "bookshelf" in with_relations:
                options.append(selectinload(BookshelfItem.bookshelf))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_bookshelf_item(
        self, item_id: int, item_data: Dict[str, Any]
    ) -> BookshelfItem:
        """Cập nhật thông tin mục kệ sách (chỉ note).

        Args:
            item_id: ID mục cần cập nhật.
            item_data: Dữ liệu cập nhật (chỉ chấp nhận 'note').

        Returns:
            Đối tượng BookshelfItem đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy mục.
        """
        item = await self.get_bookshelf_item_by_id(item_id)
        if not item:
            raise NotFoundException(
                detail=f"Không tìm thấy mục kệ sách với ID {item_id}"
            )

        allowed_fields = {"note"}
        updated = False
        for key, value in item_data.items():
            if key in allowed_fields and getattr(item, key) != value:
                setattr(item, key, value)
                updated = True

        if updated:
            await self.db.commit()
            await self.db.refresh(item)
        return item

    async def delete_bookshelf_item(self, item_id: int) -> bool:
        """Xóa mục khỏi kệ sách.

        Args:
            item_id: ID mục cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        item = await self.get_bookshelf_item_by_id(item_id)
        if not item:
            return False

        await self.db.delete(item)
        await self.db.commit()
        return True

    async def list_bookshelf_items(
        self,
        bookshelf_id: int,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        with_relations: Optional[List[str]] = ["book"],
    ) -> List[BookshelfItem]:
        """Liệt kê sách trong kệ sách.

        Args:
            bookshelf_id: ID kệ sách.
            skip, limit: Phân trang.
            sort_by, sort_desc: Sắp xếp.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách BookshelfItem.
        """
        query = select(BookshelfItem).where(BookshelfItem.bookshelf_id == bookshelf_id)

        sort_attr = getattr(BookshelfItem, sort_by, BookshelfItem.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(BookshelfItem.book))
            if "bookshelf" in with_relations:
                options.append(selectinload(BookshelfItem.bookshelf))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_bookshelf_items(self, bookshelf_id: int) -> int:
        """Đếm số lượng sách trong kệ sách."""
        query = select(func.count(BookshelfItem.id)).where(
            BookshelfItem.bookshelf_id == bookshelf_id
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_default_bookshelf(self, user_id: int) -> Bookshelf:
        """Lấy kệ sách mặc định của người dùng, tạo mới nếu chưa có.

        Args:
            user_id: ID người dùng.

        Returns:
            Đối tượng Bookshelf mặc định.
        """
        query = select(Bookshelf).where(
            Bookshelf.user_id == user_id, Bookshelf.is_default == True
        )
        result = await self.db.execute(query)
        bookshelf = result.scalars().first()

        if not bookshelf:
            bookshelf_data = {
                "user_id": user_id,
                "name": "Kệ sách của tôi",  # Hoặc tên mặc định khác
                "description": "Kệ sách mặc định",
                "is_default": True,
                "is_public": False,
            }
            bookshelf = await self.create_bookshelf(bookshelf_data)

        return bookshelf

    async def add_book_to_bookshelf(
        self, bookshelf_id: int, book_id: int, note: Optional[str] = None
    ) -> BookshelfItem:
        """Thêm sách vào kệ sách, nếu đã tồn tại thì cập nhật ghi chú.

        Args:
            bookshelf_id: ID kệ sách.
            book_id: ID sách.
            note: Ghi chú (tùy chọn).

        Returns:
            Đối tượng BookshelfItem đã được thêm hoặc cập nhật.
        """
        item = await self.get_bookshelf_item_by_book(bookshelf_id, book_id)

        if item:
            # Cập nhật note nếu có và khác note cũ
            if note is not None and note != item.note:
                item = await self.update_bookshelf_item(item.id, {"note": note})
            return item

        # Tạo mới nếu chưa có
        item_data = {"bookshelf_id": bookshelf_id, "book_id": book_id}
        if note:
            item_data["note"] = note

        # Lọc lại item_data trước khi tạo (dù chỉ có note là tùy chọn)
        allowed_fields = {"bookshelf_id", "book_id", "note"}
        filtered_data = {k: v for k, v in item_data.items() if k in allowed_fields}
        return await self.create_bookshelf_item(filtered_data)

    async def get_user_book_bookshelves(
        self, user_id: int, book_id: int
    ) -> List[Bookshelf]:
        """Lấy danh sách kệ sách của user có chứa một cuốn sách cụ thể."""
        query = (
            select(Bookshelf)
            .join(BookshelfItem)
            .where(Bookshelf.user_id == user_id, BookshelfItem.book_id == book_id)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def remove_book_from_all_bookshelves(self, user_id: int, book_id: int) -> int:
        """Xóa sách khỏi tất cả kệ sách của một người dùng.

        Args:
            user_id: ID người dùng.
            book_id: ID sách.

        Returns:
            Số lượng mục đã xóa.
        """
        # Không cần lấy danh sách trước, chỉ cần thực hiện delete
        query = delete(BookshelfItem).where(
            BookshelfItem.book_id == book_id,
            # Join để lọc theo user_id của bookshelf
            BookshelfItem.bookshelf_id.in_(
                select(Bookshelf.id).where(Bookshelf.user_id == user_id)
            ),
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount
