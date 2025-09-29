from typing import Optional, List
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import expression

from app.user_site.models.tag import BookTag
from app.user_site.models.book import Book
from app.user_site.models.tag import Tag


class BookTagRepository:
    """Repository cho các thao tác với mối quan hệ giữa Book và Tag."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def add_book_tag(self, book_id: int, tag_id: int) -> Optional[BookTag]:
        """Thêm tag vào sách nếu chưa có."""
        # Kiểm tra xem liên kết đã tồn tại chưa
        existing_link = await self.db.execute(
            select(BookTag).where(BookTag.book_id == book_id, BookTag.tag_id == tag_id)
        )
        if existing_link.scalars().first():
            return None  # Hoặc trả về existing_link nếu cần

        book_tag = BookTag(book_id=book_id, tag_id=tag_id)
        self.db.add(book_tag)
        await self.db.commit()
        return book_tag

    async def remove_book_tag(self, book_id: int, tag_id: int) -> bool:
        """Xóa tag khỏi sách. Trả về True nếu xóa thành công, False nếu không tìm thấy."""
        result = await self.db.execute(
            delete(BookTag).where(BookTag.book_id == book_id, BookTag.tag_id == tag_id)
        )
        await self.db.commit()
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

    async def get_books_by_tag(
        self, tag_id: int, skip: int = 0, limit: int = 20
    ) -> List[Book]:
        """Lấy danh sách sách của một tag."""
        query = (
            select(Book)
            .join(BookTag, BookTag.book_id == Book.id)
            .where(BookTag.tag_id == tag_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_books_by_tag(self, tag_id: int) -> int:
        """Đếm số lượng sách của một tag."""
        query = select(func.count(BookTag.book_id)).where(BookTag.tag_id == tag_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def count_tags_by_book(self, book_id: int) -> int:
        """Đếm số lượng tag của một sách."""
        query = select(func.count(BookTag.tag_id)).where(BookTag.book_id == book_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0
