from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, Session

from app.user_site.models.tag import Tag, BookTag
from app.user_site.models.book import Book
from app.core.exceptions import NotFoundException, ConflictException


class TagRepository:
    """Repository cho các thao tác với Tag và BookTag."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def create(self, tag_data: Dict[str, Any]) -> Tag:
        """Tạo một tag mới.

        Args:
            tag_data: Dữ liệu của tag mới (name, slug, description, color).

        Returns:
            Đối tượng Tag đã được tạo.

        Raises:
            ConflictException: Nếu slug đã tồn tại.
        """
        slug = tag_data.get("slug")
        if slug:
            existing_tag = await self.get_by_slug(slug)
            if existing_tag:
                raise ConflictException(detail=f"Slug '{slug}' đã được sử dụng")

        # Đảm bảo chỉ truyền các trường hợp lệ vào model
        allowed_fields = {"name", "slug", "description", "color"}
        filtered_data = {k: v for k, v in tag_data.items() if k in allowed_fields}

        tag = Tag(**filtered_data)
        self.db.add(tag)
        await self.db.commit()
        await self.db.refresh(tag)
        return tag

    async def get_by_id(
        self, tag_id: int, include_books: bool = False
    ) -> Optional[Tag]:
        """Lấy tag theo ID.

        Args:
            tag_id: ID của tag.
            include_books: Có load danh sách sách liên quan không.

        Returns:
            Đối tượng Tag hoặc None nếu không tìm thấy.
        """
        query = select(Tag).where(Tag.id == tag_id)

        if include_books:
            query = query.options(selectinload(Tag.books))

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Optional[Tag]:
        """Lấy tag theo tên (phân biệt chữ hoa/thường)."""
        query = select(Tag).where(Tag.name == name)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_slug(self, slug: str) -> Optional[Tag]:
        """Lấy tag theo slug."""
        query = select(Tag).where(Tag.slug == slug)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update(self, tag_id: int, tag_data: Dict[str, Any]) -> Tag:
        """Cập nhật thông tin tag.

        Args:
            tag_id: ID của tag cần cập nhật.
            tag_data: Dữ liệu cập nhật (name, slug, description, color).

        Returns:
            Đối tượng Tag đã được cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy tag.
            ConflictException: Nếu slug mới đã tồn tại cho tag khác.
        """
        tag = await self.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(detail=f"Không tìm thấy tag với ID {tag_id}")

        # Kiểm tra slug mới (nếu có)
        new_slug = tag_data.get("slug")
        if new_slug and new_slug != tag.slug:
            existing_tag = await self.get_by_slug(new_slug)
            if existing_tag:
                raise ConflictException(detail=f"Slug '{new_slug}' đã được sử dụng")

        # Đảm bảo chỉ cập nhật các trường hợp lệ
        allowed_fields = {"name", "slug", "description", "color"}
        for key, value in tag_data.items():
            if key in allowed_fields:
                setattr(tag, key, value)

        await self.db.commit()
        await self.db.refresh(tag)
        return tag

    async def delete(self, tag_id: int) -> bool:
        """Xóa tag. Lưu ý: Cần xử lý BookTag liên quan trước hoặc dùng cascade."""
        tag = await self.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(detail=f"Không tìm thấy tag với ID {tag_id}")

        # Cân nhắc: Nếu không có cascade on delete, cần xóa BookTag trước
        # await self.db.execute(delete(BookTag).where(BookTag.tag_id == tag_id))

        await self.db.delete(tag)
        await self.db.commit()
        return True

    async def list_tags(
        self,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "name",
        sort_desc: bool = False,
        search_query: Optional[str] = None,
    ) -> List[Tag]:
        """Liệt kê danh sách tag với tìm kiếm, sắp xếp và phân trang."""
        query = select(Tag)

        # Tìm kiếm
        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.where(
                or_(Tag.name.ilike(search_pattern), Tag.slug.ilike(search_pattern))
            )

        # Sắp xếp
        sort_attr = getattr(Tag, sort_by, Tag.name)  # Mặc định sort theo tên
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_tags(self, search_query: Optional[str] = None) -> int:
        """Đếm số lượng tag với điều kiện tìm kiếm."""
        query = select(func.count(Tag.id))

        # Tìm kiếm
        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.where(
                or_(Tag.name.ilike(search_pattern), Tag.slug.ilike(search_pattern))
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0  # Trả về 0 nếu không có tag nào

    async def get_tag_book_count(self, tag_id: int) -> int:
        """Đếm số lượng sách của một tag cụ thể."""
        query = select(func.count(BookTag.book_id)).where(BookTag.tag_id == tag_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_books_by_tag(
        self, tag_id: int, skip: int = 0, limit: int = 20, only_published: bool = True
    ) -> List[Book]:
        """Lấy danh sách sách của một tag, có thể lọc sách đã xuất bản."""
        query = select(Book).join(BookTag).where(BookTag.tag_id == tag_id)

        # Lọc sách đã xuất bản
        if only_published:
            query = query.where(Book.is_published == True)

        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_books_by_tag(self, tag_id: int, only_published: bool = True) -> int:
        """Đếm số lượng sách của một tag, có thể lọc sách đã xuất bản."""
        query = select(func.count(BookTag.book_id)).where(BookTag.tag_id == tag_id)

        if only_published:
            query = query.join(Book).where(Book.is_published == True)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_or_create(
        self, name: str, slug: Optional[str] = None, **kwargs
    ) -> Tag:
        """Lấy tag theo tên hoặc tạo mới nếu chưa tồn tại.
        Cho phép truyền thêm description, color qua kwargs.
        """
        tag = await self.get_by_name(name)
        if not tag:
            if not slug:
                # Sử dụng thư viện slugify nếu có
                try:
                    from slugify import slugify

                    generated_slug = slugify(name)
                except ImportError:
                    # Fallback đơn giản
                    import re

                    generated_slug = re.sub(r"[\s\W]+", "-", name).lower().strip("-")
                slug = generated_slug

            # Kiểm tra slug tồn tại
            counter = 1
            base_slug = slug
            while await self.get_by_slug(slug):
                slug = f"{base_slug}-{counter}"
                counter += 1

            tag_data = {"name": name, "slug": slug, **kwargs}
            # Lọc lại kwargs chỉ lấy các trường hợp lệ
            allowed_kwargs = {"description", "color"}
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_kwargs}
            tag_data.update(filtered_kwargs)

            tag = await self.create(tag_data)
        return tag

    async def get_popular_tags(self, limit: int = 10) -> List[Tag]:
        """Lấy danh sách tag phổ biến dựa trên số lượng sách liên kết."""
        # Subquery để đếm số sách
        book_count_sq = (
            select(BookTag.tag_id, func.count(BookTag.book_id).label("book_count"))
            .group_by(BookTag.tag_id)
            .subquery()
        )

        # Query chính join với subquery và sắp xếp
        query = (
            select(Tag)
            .join(book_count_sq, Tag.id == book_count_sq.c.tag_id)
            .order_by(desc(book_count_sq.c.book_count))
            .limit(limit)
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def add_book_tag(self, book_id: int, tag_id: int) -> Optional[BookTag]:
        """Thêm tag vào sách nếu chưa có."""
        # Kiểm tra xem liên kết đã tồn tại chưa
        existing_link = await self.db.execute(
            select(BookTag).where(BookTag.book_id == book_id, BookTag.tag_id == tag_id)
        )
        if existing_link.scalars().first():
            return None  # Hoặc trả về existing_link nếu cần

        # Kiểm tra xem book và tag có tồn tại không (tùy chọn, tăng độ an toàn)
        # book = await self.db.get(Book, book_id)
        # tag = await self.db.get(Tag, tag_id)
        # if not book or not tag:
        #     raise NotFoundException("Book hoặc Tag không tồn tại")

        book_tag = BookTag(book_id=book_id, tag_id=tag_id)
        self.db.add(book_tag)
        await self.db.commit()
        # Không cần refresh vì BookTag thường không có nhiều thông tin cần load lại
        return book_tag

    async def remove_book_tag(self, book_id: int, tag_id: int) -> bool:
        """Xóa tag khỏi sách. Trả về True nếu xóa thành công, False nếu không tìm thấy."""
        result = await self.db.execute(
            delete(BookTag).where(BookTag.book_id == book_id, BookTag.tag_id == tag_id)
        )
        await self.db.commit()
        # rowcount trả về số dòng bị ảnh hưởng
        return result.rowcount > 0

    async def get_tags_by_book(self, book_id: int) -> List[Tag]:
        """Lấy danh sách các tag của một cuốn sách."""
        query = (
            select(Tag)
            .join(BookTag, BookTag.tag_id == Tag.id)
            .where(BookTag.book_id == book_id)
        )
        result = await self.db.execute(query)
        return result.scalars().all()
