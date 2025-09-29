from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func, update, delete, desc, asc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.user_site.models.chapter import Chapter, ChapterMedia
from app.core.exceptions import NotFoundException


class ChapterRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Chapter:
        """Tạo một chương mới."""
        # Chuyển đổi chapter_number thành number nếu có
        if "chapter_number" in data:
            data["number"] = data.pop("chapter_number")

        chapter = Chapter(**data)
        self.db.add(chapter)
        await self.db.commit()
        await self.db.refresh(chapter)
        return chapter

    async def get_by_id(
        self, chapter_id: int, with_relations: bool = False
    ) -> Optional[Chapter]:
        """Lấy chương theo ID."""
        query = select(Chapter).where(Chapter.id == chapter_id)

        if with_relations:
            query = query.options(joinedload(Chapter.book), joinedload(Chapter.media))

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_book_and_number(
        self, book_id: int, number: int
    ) -> Optional[Chapter]:
        """Lấy chương theo book_id và số thứ tự."""
        query = select(Chapter).where(
            Chapter.book_id == book_id, Chapter.number == number
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_book(
        self, book_id: int, is_published: Optional[bool] = None
    ) -> List[Chapter]:
        """Lấy danh sách chương theo book_id."""
        query = select(Chapter).where(Chapter.book_id == book_id)

        if is_published is not None:
            query = query.filter(Chapter.is_published == is_published)

        query = query.order_by(Chapter.number)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update(self, chapter_id: int, data: Dict[str, Any]) -> Chapter:
        """Cập nhật thông tin chương."""
        chapter = await self.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        # Chuyển đổi chapter_number thành number nếu có
        if "chapter_number" in data:
            data["number"] = data.pop("chapter_number")

        for key, value in data.items():
            setattr(chapter, key, value)

        await self.db.commit()
        await self.db.refresh(chapter)
        return chapter

    async def delete(self, chapter_id: int) -> bool:
        """Xóa chương."""
        chapter = await self.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        await self.db.delete(chapter)
        await self.db.commit()
        return True

    async def increment_view_count(self, chapter_id: int) -> Chapter:
        """Tăng số lượt xem cho chương."""
        chapter = await self.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        chapter.view_count += 1
        await self.db.commit()
        await self.db.refresh(chapter)
        return chapter

    async def get_next_chapter(self, chapter_id: int) -> Optional[Chapter]:
        """Lấy chương tiếp theo."""
        current_chapter = await self.get_by_id(chapter_id)
        if not current_chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        query = (
            select(Chapter)
            .where(
                Chapter.book_id == current_chapter.book_id,
                Chapter.number > current_chapter.number,
                Chapter.is_published == True,
            )
            .order_by(Chapter.number)
            .limit(1)
        )

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_previous_chapter(self, chapter_id: int) -> Optional[Chapter]:
        """Lấy chương trước đó."""
        current_chapter = await self.get_by_id(chapter_id)
        if not current_chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        query = (
            select(Chapter)
            .where(
                Chapter.book_id == current_chapter.book_id,
                Chapter.number < current_chapter.number,
                Chapter.is_published == True,
            )
            .order_by(desc(Chapter.number))
            .limit(1)
        )

        result = await self.db.execute(query)
        return result.scalars().first()

    async def count_chapters_by_book(
        self, book_id: int, is_published: Optional[bool] = None
    ) -> int:
        """Đếm số lượng chương của một cuốn sách."""
        query = select(func.count(Chapter.id)).where(Chapter.book_id == book_id)

        if is_published is not None:
            query = query.where(Chapter.is_published == is_published)

        result = await self.db.execute(query)
        return result.scalar_one()

    async def get_first_chapter(
        self, book_id: int, only_published: bool = True
    ) -> Optional[Chapter]:
        """Lấy chương đầu tiên của sách."""
        query = select(Chapter).where(Chapter.book_id == book_id)

        if only_published:
            query = query.where(Chapter.is_published == True)

        query = query.order_by(Chapter.number).limit(1)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_last_chapter(
        self, book_id: int, only_published: bool = True
    ) -> Optional[Chapter]:
        """Lấy chương cuối cùng của sách."""
        query = select(Chapter).where(Chapter.book_id == book_id)

        if only_published:
            query = query.where(Chapter.is_published == True)

        query = query.order_by(desc(Chapter.number)).limit(1)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def calculate_word_count(self, chapter_id: int) -> int:
        """Tính số từ của chương."""
        chapter = await self.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        content = chapter.content or ""
        # Đơn giản hóa: chia theo khoảng trắng
        words = content.split()
        word_count = len(words)

        # Cập nhật số từ và ước tính thời gian đọc
        chapter.word_count = word_count
        # Giả sử tốc độ đọc trung bình là 200 từ/phút
        chapter.estimated_read_time = max(1, round(word_count / 200))

        await self.db.commit()
        await self.db.refresh(chapter)
        return word_count

    async def publish_chapter(self, chapter_id: int) -> Chapter:
        """Xuất bản chương."""
        chapter = await self.get_by_id(chapter_id)
        if not chapter:
            raise NotFoundException(detail=f"Không tìm thấy chương với ID {chapter_id}")

        chapter.is_published = True
        chapter.status = "published"

        await self.db.commit()
        await self.db.refresh(chapter)
        return chapter

    # ChapterMedia methods

    async def create_media(self, media_data: Dict[str, Any]) -> ChapterMedia:
        """Tạo media cho chương."""
        media = ChapterMedia(**media_data)
        self.db.add(media)
        await self.db.commit()
        await self.db.refresh(media)
        return media

    async def get_media_by_id(self, media_id: int) -> Optional[ChapterMedia]:
        """Lấy media theo ID."""
        query = select(ChapterMedia).where(ChapterMedia.id == media_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_media(
        self, media_id: int, media_data: Dict[str, Any]
    ) -> ChapterMedia:
        """Cập nhật thông tin media."""
        media = await self.get_media_by_id(media_id)
        if not media:
            raise NotFoundException(detail=f"Không tìm thấy media với ID {media_id}")

        for key, value in media_data.items():
            setattr(media, key, value)

        await self.db.commit()
        await self.db.refresh(media)
        return media

    async def delete_media(self, media_id: int) -> None:
        """Xóa media."""
        media = await self.get_media_by_id(media_id)
        if not media:
            raise NotFoundException(detail=f"Không tìm thấy media với ID {media_id}")

        await self.db.delete(media)
        await self.db.commit()

    async def list_media_by_chapter(
        self, chapter_id: int, skip: int = 0, limit: int = 100
    ) -> List[ChapterMedia]:
        """Liệt kê media của một chương."""
        query = (
            select(ChapterMedia)
            .where(ChapterMedia.chapter_id == chapter_id)
            .order_by(ChapterMedia.position)
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()
