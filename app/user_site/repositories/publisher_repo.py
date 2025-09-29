from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, or_, and_, desc, asc, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.publisher import Publisher
from app.user_site.models.book import Book
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ValidationException,
)


class PublisherRepository:
    """Repository cho các thao tác với Nhà xuất bản (Publisher)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession.

        Args:
            db: Đối tượng AsyncSession để tương tác với cơ sở dữ liệu.
        """
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Publisher:
        """Tạo một nhà xuất bản mới.

        Args:
            data: Dữ liệu nhà xuất bản. Các trường yêu cầu/tùy chọn:
                - name (str): Tên nhà xuất bản (bắt buộc).
                - description (Optional[str]): Mô tả.
                - website (Optional[str]): Trang web.
                - logo_url (Optional[str]): URL logo.

        Returns:
            Đối tượng Publisher đã tạo.

        Raises:
            ValidationException: Nếu thiếu tên.
            ConflictException: Nếu có lỗi ràng buộc (ví dụ: tên đã tồn tại nếu có UNIQUE constraint).
        """
        allowed_fields = {"name", "description", "website", "logo_url"}
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

        if not filtered_data.get("name"):
            raise ValidationException("Tên nhà xuất bản (name) là bắt buộc.")

        publisher = Publisher(**filtered_data)
        self.db.add(publisher)
        try:
            await self.db.commit()
            await self.db.refresh(publisher)
            return publisher
        except IntegrityError as e:
            await self.db.rollback()
            # Kiểm tra nếu lỗi do tên bị trùng (giả sử có UNIQUE constraint)
            existing = await self.get_by_name(filtered_data["name"])
            if existing:
                raise ConflictException(
                    f"Nhà xuất bản với tên '{filtered_data['name']}' đã tồn tại."
                )
            raise ConflictException(f"Không thể tạo nhà xuất bản: {e}")

    async def get_by_id(
        self, publisher_id: int, with_books: bool = False
    ) -> Optional[Publisher]:
        """Lấy nhà xuất bản theo ID.

        Args:
            publisher_id: ID của nhà xuất bản.
            with_books: Có load danh sách sách của NXB này không (yêu cầu có relationship 'books').

        Returns:
            Đối tượng Publisher hoặc None.
        """
        query = select(Publisher).where(Publisher.id == publisher_id)
        if with_books:
            # Giả sử có relationship tên là 'books' trong model Publisher
            query = query.options(selectinload(Publisher.books))
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_name(
        self, name: str, with_books: bool = False
    ) -> Optional[Publisher]:
        """Lấy nhà xuất bản theo tên (chính xác).

        Args:
            name: Tên của nhà xuất bản.
            with_books: Có load danh sách sách của NXB này không.

        Returns:
            Đối tượng Publisher hoặc None.
        """
        query = select(Publisher).where(Publisher.name == name)
        if with_books:
            query = query.options(selectinload(Publisher.books))
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_publishers(
        self,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "name",
        sort_desc: bool = False,
    ) -> List[Publisher]:
        """Lấy danh sách nhà xuất bản, có tìm kiếm, phân trang và sắp xếp.

        Args:
            search: Từ khóa tìm kiếm (trong tên hoặc mô tả).
            skip: Số lượng bản ghi bỏ qua.
            limit: Số lượng bản ghi tối đa.
            sort_by: Trường sắp xếp ('name', 'created_at').
            sort_desc: Sắp xếp giảm dần.

        Returns:
            Danh sách các đối tượng Publisher.
        """
        query = select(Publisher)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Publisher.name.ilike(search_term),
                    Publisher.description.ilike(search_term),
                )
            )

        # Sắp xếp
        sort_attr = getattr(Publisher, sort_by, Publisher.name)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_publishers(self, search: Optional[str] = None) -> int:
        """Đếm số lượng nhà xuất bản, có tìm kiếm.

        Args:
            search: Từ khóa tìm kiếm (trong tên hoặc mô tả).

        Returns:
            Tổng số nhà xuất bản khớp điều kiện.
        """
        query = select(func.count(Publisher.id))
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Publisher.name.ilike(search_term),
                    Publisher.description.ilike(search_term),
                )
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update(self, publisher_id: int, data: Dict[str, Any]) -> Publisher:
        """Cập nhật thông tin nhà xuất bản.

        Args:
            publisher_id: ID nhà xuất bản cần cập nhật.
            data: Dữ liệu cập nhật (name, description, website, logo_url).

        Returns:
            Đối tượng Publisher đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy nhà xuất bản.
            ConflictException: Nếu tên mới bị trùng (giả sử có UNIQUE constraint).
        """
        publisher = await self.get_by_id(publisher_id)
        if not publisher:
            raise NotFoundException(
                f"Không tìm thấy nhà xuất bản với ID {publisher_id}."
            )

        allowed_fields = {"name", "description", "website", "logo_url"}
        updated = False
        new_name = data.get("name")

        # Kiểm tra tên trùng nếu tên thay đổi
        if new_name and new_name != publisher.name:
            existing = await self.get_by_name(new_name)
            if existing:
                raise ConflictException(
                    f"Nhà xuất bản với tên '{new_name}' đã tồn tại."
                )

        for key, value in data.items():
            if (
                key in allowed_fields
                and value is not None
                and getattr(publisher, key) != value
            ):
                setattr(publisher, key, value)
                updated = True

        if not updated:
            return publisher  # Không có gì thay đổi

        try:
            await self.db.commit()
            await self.db.refresh(publisher)
            return publisher
        except IntegrityError as e:
            await self.db.rollback()
            # Lỗi có thể xảy ra nếu tên bị trùng do race condition
            raise ConflictException(f"Không thể cập nhật nhà xuất bản: {e}")

    async def delete_publisher(self, publisher_id: int) -> bool:
        """Xóa một nhà xuất bản.
           Cảnh báo: Cần đảm bảo không còn sách nào tham chiếu đến NXB này,
                 hoặc khóa ngoại trong Book đã được cấu hình phù hợp (ON DELETE SET NULL / CASCADE).

        Args:
            publisher_id: ID nhà xuất bản cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.

        Raises:
             ConflictException: Nếu không thể xóa do ràng buộc khóa ngoại.
        """
        # Kiểm tra xem còn sách nào liên kết không (nếu cần thiết và không có cascade)
        # book_count = await self.count_books_by_publisher(publisher_id)
        # if book_count > 0:
        #     raise ConflictException(f"Không thể xóa nhà xuất bản ID {publisher_id} vì còn sách liên kết.")

        stmt = delete(Publisher).where(Publisher.id == publisher_id)
        try:
            result = await self.db.execute(stmt)
            if result.rowcount > 0:
                await self.db.commit()
                return True
            return False  # Không tìm thấy
        except IntegrityError as e:
            # Lỗi này xảy ra nếu còn sách tham chiếu và FK không cho phép xóa
            await self.db.rollback()
            raise ConflictException(
                f"Không thể xóa nhà xuất bản ID {publisher_id} do ràng buộc khóa ngoại: {e}"
            )

    async def get_books_by_publisher(
        self,
        publisher_id: int,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "title",
        sort_desc: bool = False,
    ) -> List[Book]:
        """Lấy danh sách các sách của một nhà xuất bản, có phân trang, sắp xếp.
           (Yêu cầu model Book có trường publisher_id)

        Args:
            publisher_id: ID của nhà xuất bản.
            skip, limit: Phân trang.
            sort_by: Trường sắp xếp sách ('title', 'created_at', ...).
            sort_desc: Sắp xếp giảm dần.

        Returns:
            Danh sách các đối tượng Book.
        """
        query = select(Book).where(Book.publisher_id == publisher_id)

        # Sắp xếp sách
        sort_attr = getattr(Book, sort_by, Book.title)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Tùy chọn load thêm quan hệ của Book nếu cần (ví dụ: tác giả)
        # query = query.options(selectinload(Book.authors), ...)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_books_by_publisher(self, publisher_id: int) -> int:
        """Đếm số lượng sách của một nhà xuất bản.
           (Yêu cầu model Book có trường publisher_id)

        Args:
            publisher_id: ID của nhà xuất bản.

        Returns:
            Số lượng sách.
        """
        query = select(func.count(Book.id)).where(Book.publisher_id == publisher_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_or_create(self, name: str, **kwargs) -> tuple[Publisher, bool]:
        """Lấy hoặc tạo nhà xuất bản mới nếu chưa tồn tại."""
        publisher = await self.get_by_name(name)
        if publisher:
            return publisher, False

        data = {"name": name, **kwargs}
        publisher = await self.create(data)
        return publisher, True

    async def search_publishers(self, query: str, limit: int = 10) -> List[Publisher]:
        """Tìm kiếm nhà xuất bản theo từ khóa."""
        search_pattern = f"%{query}%"
        query = (
            select(Publisher)
            .where(
                or_(
                    Publisher.name.ilike(search_pattern),
                    Publisher.description.ilike(search_pattern),
                    Publisher.website.ilike(search_pattern),
                )
            )
            .limit(limit)
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_publisher_with_book_count(self, publisher_id: int) -> Dict[str, Any]:
        """Lấy thông tin nhà xuất bản kèm số lượng sách."""
        publisher = await self.get_by_id(publisher_id)
        if not publisher:
            raise NotFoundException(
                detail=f"Không tìm thấy nhà xuất bản với ID {publisher_id}"
            )

        # Đếm số lượng sách
        query = select(func.count(Book.id)).where(Book.publisher_id == publisher_id)
        result = await self.db.execute(query)
        book_count = result.scalar_one()

        # Chuyển đổi publisher sang dict
        publisher_dict = {
            "id": publisher.id,
            "name": publisher.name,
            "description": publisher.description,
            "logo_url": publisher.logo_url,
            "website": publisher.website,
            "contact_email": publisher.contact_email,
            "created_at": publisher.created_at,
            "updated_at": publisher.updated_at,
            "book_count": book_count,
        }

        return publisher_dict
