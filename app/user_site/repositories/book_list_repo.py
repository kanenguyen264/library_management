from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.user_site.models.book_list import UserBookList, UserBookListItem
from app.core.exceptions import NotFoundException


class BookListRepository:
    """Repository cho các thao tác với danh sách sách (UserBookList) và các mục trong danh sách (UserBookListItem)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    # UserBookList methods

    async def create_list(self, list_data: Dict[str, Any]) -> UserBookList:
        """Tạo một danh sách sách mới cho người dùng.

        Args:
            list_data: Dữ liệu danh sách (user_id, title, description, is_public).

        Returns:
            Đối tượng UserBookList đã được tạo.
        """
        allowed_fields = {"user_id", "title", "description", "is_public"}
        filtered_data = {k: v for k, v in list_data.items() if k in allowed_fields}
        book_list = UserBookList(**filtered_data)
        self.db.add(book_list)
        await self.db.commit()
        await self.db.refresh(book_list)
        return book_list

    async def get_list_by_id(
        self, list_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[UserBookList]:
        """Lấy danh sách sách theo ID.

        Args:
            list_id: ID của danh sách.
            with_relations: Danh sách các mối quan hệ cần load (ví dụ: ["user", "items", "items.book"]).

        Returns:
            Đối tượng UserBookList hoặc None nếu không tìm thấy.
        """
        query = select(UserBookList).where(UserBookList.id == list_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(UserBookList.user))
            if "items" in with_relations:
                items_option = selectinload(UserBookList.items)
                if "items.book" in with_relations:
                    items_option = items_option.selectinload(UserBookListItem.book)
                options.append(items_option)
            elif "items.book" in with_relations:
                items_option = selectinload(UserBookList.items).selectinload(
                    UserBookListItem.book
                )
                options.append(items_option)

            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_list_by_title_and_user(
        self, title: str, user_id: int
    ) -> Optional[UserBookList]:
        """Lấy danh sách sách theo tiêu đề và người dùng (kiểm tra trùng lặp)."""
        query = select(UserBookList).where(
            and_(UserBookList.title == title, UserBookList.user_id == user_id)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_list(
        self, list_id: int, list_data: Dict[str, Any]
    ) -> UserBookList:
        """Cập nhật thông tin danh sách sách.

        Args:
            list_id: ID của danh sách cần cập nhật.
            list_data: Dữ liệu cập nhật (title, description, is_public).

        Returns:
            Đối tượng UserBookList đã được cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy danh sách.
        """
        book_list = await self.get_list_by_id(list_id)
        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID {list_id}"
            )

        allowed_fields = {"title", "description", "is_public"}
        for key, value in list_data.items():
            if key in allowed_fields:
                setattr(book_list, key, value)

        await self.db.commit()
        await self.db.refresh(book_list)
        return book_list

    async def delete_list(self, list_id: int) -> bool:
        """Xóa danh sách sách. Lưu ý: Cần xử lý các UserBookListItem liên quan.

        Args:
            list_id: ID của danh sách cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        book_list = await self.get_list_by_id(list_id)
        if not book_list:
            return False

        await self.db.delete(book_list)
        await self.db.commit()
        return True

    async def list_user_book_lists(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "title",
        sort_desc: bool = False,
        with_relations: Optional[List[str]] = ["user"],
    ) -> List[UserBookList]:
        """Liệt kê danh sách sách của một người dùng.

        Args:
            user_id: ID của người dùng.
            skip: Số lượng bỏ qua.
            limit: Số lượng tối đa.
            sort_by: Trường sắp xếp.
            sort_desc: Sắp xếp giảm dần.
            with_relations: Danh sách quan hệ cần load.

        Returns:
            Danh sách các đối tượng UserBookList.
        """
        query = select(UserBookList).where(UserBookList.user_id == user_id)

        sort_attr = getattr(UserBookList, sort_by, UserBookList.title)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(UserBookList.user))
            if "items" in with_relations:
                items_option = selectinload(UserBookList.items)
                if "items.book" in with_relations:
                    items_option = items_option.selectinload(UserBookListItem.book)
                options.append(items_option)
            elif "items.book" in with_relations:
                items_option = selectinload(UserBookList.items).selectinload(
                    UserBookListItem.book
                )
                options.append(items_option)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def list_public_book_lists(
        self,
        skip: int = 0,
        limit: int = 20,
        search_query: Optional[str] = None,
        sort_by: str = "title",
        sort_desc: bool = False,
        with_relations: Optional[List[str]] = ["user"],
    ) -> List[UserBookList]:
        """Liệt kê danh sách sách công khai với tìm kiếm, sắp xếp, phân trang.

        Args:
            skip, limit: Phân trang.
            search_query: Từ khóa tìm kiếm (title, description).
            sort_by, sort_desc: Sắp xếp.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách UserBookList công khai.
        """
        query = select(UserBookList).where(UserBookList.is_public == True)

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    UserBookList.title.ilike(search_pattern),
                    UserBookList.description.ilike(search_pattern),
                )
            )

        sort_attr = getattr(UserBookList, sort_by, UserBookList.title)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(UserBookList.user))
            if "items" in with_relations:
                items_option = selectinload(UserBookList.items)
                if "items.book" in with_relations:
                    items_option = items_option.selectinload(UserBookListItem.book)
                options.append(items_option)
            elif "items.book" in with_relations:
                items_option = selectinload(UserBookList.items).selectinload(
                    UserBookListItem.book
                )
                options.append(items_option)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_user_book_lists(self, user_id: int) -> int:
        """Đếm số lượng danh sách sách của một người dùng."""
        query = select(func.count(UserBookList.id)).where(
            UserBookList.user_id == user_id
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def count_public_book_lists(self, search_query: Optional[str] = None) -> int:
        """Đếm số lượng danh sách sách công khai, có thể lọc theo tìm kiếm."""
        query = select(func.count(UserBookList.id)).where(
            UserBookList.is_public == True
        )

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    UserBookList.title.ilike(search_pattern),
                    UserBookList.description.ilike(search_pattern),
                )
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    # UserBookListItem methods

    async def create_list_item(self, item_data: Dict[str, Any]) -> UserBookListItem:
        """Thêm một sách vào danh sách sách.

        Args:
            item_data: Dữ liệu mục (list_id, book_id, position, note).

        Returns:
            Đối tượng UserBookListItem đã được tạo.
        """
        allowed_fields = {"list_id", "book_id", "position", "note"}
        filtered_data = {k: v for k, v in item_data.items() if k in allowed_fields}
        item = UserBookListItem(**filtered_data)
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def get_list_item_by_id(
        self, item_id: int, with_relations: Optional[List[str]] = ["book", "list"]
    ) -> Optional[UserBookListItem]:
        """Lấy mục danh sách sách theo ID.

        Args:
            item_id: ID của mục.
            with_relations: Quan hệ cần load (mặc định: book, list).

        Returns:
            Đối tượng UserBookListItem hoặc None.
        """
        query = select(UserBookListItem).where(UserBookListItem.id == item_id)

        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(UserBookListItem.book))
            if "list" in with_relations:
                options.append(selectinload(UserBookListItem.list))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_list_item_by_book(
        self, list_id: int, book_id: int, with_relations: Optional[List[str]] = ["book"]
    ) -> Optional[UserBookListItem]:
        """Lấy mục danh sách sách theo list_id và book_id.

        Args:
            list_id: ID của danh sách.
            book_id: ID của sách.
            with_relations: Quan hệ cần load (mặc định: book).

        Returns:
            Đối tượng UserBookListItem hoặc None.
        """
        query = select(UserBookListItem).where(
            and_(
                UserBookListItem.list_id == list_id, UserBookListItem.book_id == book_id
            )
        )

        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(UserBookListItem.book))
            if "list" in with_relations:
                options.append(selectinload(UserBookListItem.list))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_list_item(
        self, item_id: int, item_data: Dict[str, Any]
    ) -> UserBookListItem:
        """Cập nhật thông tin mục danh sách sách (ví dụ: position, note).

        Args:
            item_id: ID của mục cần cập nhật.
            item_data: Dữ liệu cập nhật (position, note).

        Returns:
            Đối tượng UserBookListItem đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy mục.
        """
        item = await self.get_list_item_by_id(item_id)
        if not item:
            raise NotFoundException(
                detail=f"Không tìm thấy mục danh sách sách với ID {item_id}"
            )

        allowed_fields = {"position", "note"}
        for key, value in item_data.items():
            if key in allowed_fields:
                setattr(item, key, value)

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete_list_item(self, item_id: int) -> bool:
        """Xóa mục khỏi danh sách sách.

        Args:
            item_id: ID của mục cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        item = await self.get_list_item_by_id(item_id)
        if not item:
            return False

        await self.db.delete(item)
        await self.db.commit()
        return True

    async def list_list_items(
        self,
        list_id: int,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "position",
        sort_desc: bool = False,
        with_relations: Optional[List[str]] = ["book"],
    ) -> List[UserBookListItem]:
        """Liệt kê các sách trong một danh sách sách, sắp xếp theo vị trí.

        Args:
            list_id: ID của danh sách.
            skip, limit: Phân trang.
            sort_by, sort_desc: Sắp xếp (mặc định theo position).
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách các đối tượng UserBookListItem.
        """
        query = select(UserBookListItem).where(UserBookListItem.list_id == list_id)

        sort_attr = getattr(UserBookListItem, sort_by, UserBookListItem.position)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "book" in with_relations:
                options.append(selectinload(UserBookListItem.book))
            if "list" in with_relations:
                options.append(selectinload(UserBookListItem.list))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_list_items(self, list_id: int) -> int:
        """Đếm số lượng sách trong danh sách sách."""
        query = select(func.count(UserBookListItem.id)).where(
            UserBookListItem.list_id == list_id
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0
