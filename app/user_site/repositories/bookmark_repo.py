from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func, update, delete, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime

from app.user_site.models.bookmark import Bookmark
from app.core.exceptions import NotFoundException


class BookmarkRepository:
    """Repository cho các thao tác liên quan đến đánh dấu trang (Bookmark) của người dùng."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Bookmark:
        """Tạo một bookmark mới.

        Args:
            data: Dữ liệu bookmark (user_id, book_id, chapter_id, position, note).

        Returns:
            Đối tượng Bookmark đã được tạo.
        """
        allowed_fields = {"user_id", "book_id", "chapter_id", "position", "note"}
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
        bookmark = Bookmark(**filtered_data)
        self.db.add(bookmark)
        await self.db.commit()
        await self.db.refresh(bookmark)
        return bookmark

    async def get_by_id(
        self, bookmark_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[Bookmark]:
        """Lấy bookmark theo ID.

        Args:
            bookmark_id: ID của bookmark.
            with_relations: Danh sách quan hệ cần load (["user", "book", "chapter"]).

        Returns:
            Đối tượng Bookmark hoặc None.
        """
        query = select(Bookmark).where(Bookmark.id == bookmark_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Bookmark.user))
            if "book" in with_relations:
                options.append(selectinload(Bookmark.book))
            if "chapter" in with_relations:
                options.append(selectinload(Bookmark.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_and_chapter(
        self, user_id: int, chapter_id: int
    ) -> Optional[Bookmark]:
        """Lấy bookmark theo user_id và chapter_id (thường là duy nhất)."""
        query = select(Bookmark).where(
            Bookmark.user_id == user_id, Bookmark.chapter_id == chapter_id
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        book_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        with_relations: Optional[List[str]] = ["book", "chapter"],
    ) -> List[Bookmark]:
        """Lấy danh sách bookmark của người dùng, có thể lọc theo sách.

        Args:
            user_id: ID người dùng.
            book_id: Lọc theo ID sách (tùy chọn).
            skip, limit: Phân trang.
            sort_by, sort_desc: Sắp xếp.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách Bookmark.
        """
        query = select(Bookmark).where(Bookmark.user_id == user_id)

        if book_id:
            query = query.filter(Bookmark.book_id == book_id)

        # Sắp xếp
        sort_attr = getattr(Bookmark, sort_by, Bookmark.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load relations
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Bookmark.user))
            if "book" in with_relations:
                options.append(selectinload(Bookmark.book))
            if "chapter" in with_relations:
                options.append(selectinload(Bookmark.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int, book_id: Optional[int] = None) -> int:
        """Đếm số lượng bookmark của người dùng, có thể lọc theo sách.

        Args:
            user_id: ID người dùng.
            book_id: Lọc theo ID sách (tùy chọn).

        Returns:
            Tổng số bookmark khớp điều kiện.
        """
        query = select(func.count(Bookmark.id)).where(Bookmark.user_id == user_id)

        if book_id:
            query = query.filter(Bookmark.book_id == book_id)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update(self, bookmark_id: int, data: Dict[str, Any]) -> Bookmark:
        """Cập nhật thông tin bookmark (position, note).

        Args:
            bookmark_id: ID bookmark cần cập nhật.
            data: Dữ liệu cập nhật (position, note).

        Returns:
            Đối tượng Bookmark đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy bookmark.
        """
        bookmark = await self.get_by_id(bookmark_id)
        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID {bookmark_id}"
            )

        allowed_fields = {"position", "note"}
        updated = False
        for key, value in data.items():
            if key in allowed_fields and getattr(bookmark, key) != value:
                setattr(bookmark, key, value)
                updated = True

        if updated:
            # SQLAlchemy tự cập nhật updated_at nếu được cấu hình
            # Hoặc cập nhật thủ công: bookmark.updated_at = datetime.now()
            await self.db.commit()
            await self.db.refresh(bookmark)
        return bookmark

    async def delete(self, bookmark_id: int) -> bool:
        """Xóa bookmark theo ID.

        Args:
            bookmark_id: ID bookmark cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        bookmark = await self.get_by_id(bookmark_id)
        if not bookmark:
            return False

        await self.db.delete(bookmark)
        await self.db.commit()
        return True

    async def get_latest_by_user_and_book(
        self,
        user_id: int,
        book_id: int,
        with_relations: Optional[List[str]] = ["chapter"],
    ) -> Optional[Bookmark]:
        """Lấy bookmark mới nhất của user cho một cuốn sách.

        Args:
            user_id: ID người dùng.
            book_id: ID sách.
            with_relations: Quan hệ cần load (mặc định: chapter).

        Returns:
            Bookmark mới nhất hoặc None.
        """
        query = (
            select(Bookmark)
            .where(Bookmark.user_id == user_id, Bookmark.book_id == book_id)
            .order_by(desc(Bookmark.updated_at))
            .limit(1)
        )  # Sắp xếp theo updated_at

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Bookmark.user))
            if "book" in with_relations:
                options.append(selectinload(Bookmark.book))
            if "chapter" in with_relations:
                options.append(selectinload(Bookmark.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def delete_by_user_and_book(self, user_id: int, book_id: int) -> int:
        """Xóa tất cả bookmark của user cho một cuốn sách.

        Args:
            user_id: ID người dùng.
            book_id: ID sách.

        Returns:
            Số lượng bookmark đã xóa.
        """
        query = delete(Bookmark).where(
            Bookmark.user_id == user_id, Bookmark.book_id == book_id
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount  # Trả về số dòng bị ảnh hưởng

    async def list_recent_by_user(
        self,
        user_id: int,
        limit: int = 5,
        with_relations: Optional[List[str]] = ["book", "chapter"],
    ) -> List[Bookmark]:
        """Lấy danh sách bookmark gần đây của user (sắp xếp theo updated_at).

        Args:
            user_id: ID người dùng.
            limit: Số lượng tối đa.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách Bookmark.
        """
        query = (
            select(Bookmark)
            .where(Bookmark.user_id == user_id)
            .order_by(desc(Bookmark.updated_at))
            .limit(limit)
        )

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Bookmark.user))
            if "book" in with_relations:
                options.append(selectinload(Bookmark.book))
            if "chapter" in with_relations:
                options.append(selectinload(Bookmark.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def add_or_update(
        self,
        user_id: int,
        book_id: int,
        chapter_id: int,
        position: Optional[Any] = None,
        note: Optional[str] = None,
    ) -> Bookmark:
        """Thêm hoặc cập nhật bookmark cho user tại một chapter cụ thể.
           Nếu bookmark đã tồn tại, cập nhật position và/hoặc note.
           Nếu chưa tồn tại, tạo mới.

        Args:
            user_id: ID người dùng.
            book_id: ID sách.
            chapter_id: ID chương.
            position: Vị trí đánh dấu (tùy chọn).
            note: Ghi chú (tùy chọn).

        Returns:
            Đối tượng Bookmark đã được tạo hoặc cập nhật.
        """
        bookmark = await self.get_by_user_and_chapter(user_id, chapter_id)

        update_data = {}
        if position is not None:
            update_data["position"] = position
        if note is not None:
            update_data["note"] = note

        if bookmark:
            # Cập nhật bookmark hiện có nếu có dữ liệu mới
            if update_data:
                return await self.update(bookmark.id, update_data)
            # Nếu không có gì cập nhật, chỉ cần trả về bookmark hiện có (hoặc có thể cập nhật updated_at)
            # bookmark.updated_at = datetime.now() # Cập nhật thủ công nếu cần
            # await self.db.commit()
            # await self.db.refresh(bookmark)
            return bookmark
        else:
            # Tạo bookmark mới
            create_data = {
                "user_id": user_id,
                "book_id": book_id,
                "chapter_id": chapter_id,
                **update_data,  # Thêm position, note nếu có
            }
            return await self.create(create_data)
