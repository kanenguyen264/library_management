from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, desc, asc, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.user_site.models.annotation import Annotation
from app.core.exceptions import NotFoundException


class AnnotationRepository:
    """Repository cho các thao tác liên quan đến ghi chú (Annotation)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def create(self, annotation_data: Dict[str, Any]) -> Annotation:
        """Tạo một ghi chú mới.

        Args:
            annotation_data: Dữ liệu của ghi chú mới.
                Bao gồm các trường như: user_id, book_id, chapter_id, content, position_start, position_end, color, note, is_public.

        Returns:
            Đối tượng Annotation đã được tạo.
        """
        # Lọc các trường hợp lệ cho Annotation
        allowed_fields = {
            "user_id",
            "book_id",
            "chapter_id",
            "content",
            "position_start",
            "position_end",
            "cfi_range",
            "color",
            "note",
            "is_public",
        }
        filtered_data = {
            k: v for k, v in annotation_data.items() if k in allowed_fields
        }
        annotation = Annotation(**filtered_data)
        self.db.add(annotation)
        await self.db.commit()
        await self.db.refresh(annotation)
        return annotation

    async def get_by_id(
        self, annotation_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[Annotation]:
        """Lấy ghi chú theo ID.

        Args:
            annotation_id: ID của ghi chú.
            with_relations: Danh sách các mối quan hệ cần load (ví dụ: ["user", "book", "chapter"]).

        Returns:
            Đối tượng Annotation hoặc None nếu không tìm thấy.
        """
        query = select(Annotation).where(Annotation.id == annotation_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Annotation.user))
            if "book" in with_relations:
                options.append(selectinload(Annotation.book))
            if "chapter" in with_relations:
                options.append(selectinload(Annotation.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        book_id: Optional[int] = None,
        chapter_id: Optional[int] = None,
        only_public: bool = False,
        skip: int = 0,
        limit: int = 20,
        with_relations: Optional[List[str]] = [
            "book",
            "chapter",
        ],  # Mặc định load book, chapter
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> List[Annotation]:
        """Lấy danh sách ghi chú của một người dùng, có thể lọc theo sách, chương.

        Args:
            user_id: ID của người dùng.
            book_id: Lọc theo ID sách (tùy chọn).
            chapter_id: Lọc theo ID chương (tùy chọn).
            only_public: Chỉ lấy các ghi chú công khai (tùy chọn).
            skip: Số lượng bản ghi bỏ qua.
            limit: Số lượng bản ghi tối đa trả về.
            with_relations: Danh sách các mối quan hệ cần load.
            sort_by: Tên trường dùng để sắp xếp (mặc định: created_at).
            sort_desc: Sắp xếp giảm dần (True) hay tăng dần (False).

        Returns:
            Danh sách các đối tượng Annotation.
        """
        query = select(Annotation).where(Annotation.user_id == user_id)

        if book_id:
            query = query.filter(Annotation.book_id == book_id)

        if chapter_id:
            query = query.filter(Annotation.chapter_id == chapter_id)

        if only_public:
            query = query.filter(Annotation.is_public == True)

        # Sắp xếp
        sort_attr = getattr(Annotation, sort_by, Annotation.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load các mối quan hệ
        if with_relations:
            options = []
            if (
                "user" in with_relations
            ):  # Mặc dù lọc theo user_id, vẫn có thể cần load object User đầy đủ
                options.append(selectinload(Annotation.user))
            if "book" in with_relations:
                options.append(selectinload(Annotation.book))
            if "chapter" in with_relations:
                options.append(selectinload(Annotation.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def list_public_by_book(
        self,
        book_id: int,
        chapter_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
        with_relations: Optional[List[str]] = [
            "user",
            "chapter",
        ],  # Mặc định load user, chapter
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> List[Annotation]:
        """Lấy danh sách ghi chú công khai của một cuốn sách, có thể lọc theo chương.

        Args:
            book_id: ID của sách.
            chapter_id: Lọc theo ID chương (tùy chọn).
            skip: Số lượng bản ghi bỏ qua.
            limit: Số lượng bản ghi tối đa trả về.
            with_relations: Danh sách các mối quan hệ cần load.
            sort_by: Tên trường dùng để sắp xếp.
            sort_desc: Sắp xếp giảm dần hay tăng dần.

        Returns:
            Danh sách các đối tượng Annotation công khai.
        """
        query = select(Annotation).where(
            and_(Annotation.book_id == book_id, Annotation.is_public == True)
        )

        if chapter_id:
            query = query.filter(Annotation.chapter_id == chapter_id)

        # Sắp xếp
        sort_attr = getattr(Annotation, sort_by, Annotation.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load các mối quan hệ
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Annotation.user))
            # Không cần load book vì đã lọc theo book_id
            if "chapter" in with_relations:
                options.append(selectinload(Annotation.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(
        self,
        user_id: int,
        book_id: Optional[int] = None,
        chapter_id: Optional[int] = None,
    ) -> int:
        """Đếm số lượng ghi chú của người dùng, có thể lọc theo sách, chương.

        Args:
            user_id: ID của người dùng.
            book_id: Lọc theo ID sách (tùy chọn).
            chapter_id: Lọc theo ID chương (tùy chọn).

        Returns:
            Tổng số lượng ghi chú khớp điều kiện.
        """
        query = select(func.count(Annotation.id)).where(Annotation.user_id == user_id)

        if book_id:
            query = query.filter(Annotation.book_id == book_id)

        if chapter_id:
            query = query.filter(Annotation.chapter_id == chapter_id)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update(self, annotation_id: int, data: Dict[str, Any]) -> Annotation:
        """Cập nhật thông tin ghi chú.

        Args:
            annotation_id: ID của ghi chú cần cập nhật.
            data: Dữ liệu cập nhật.

        Returns:
            Đối tượng Annotation đã được cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy ghi chú với ID cung cấp.
        """
        annotation = await self.get_by_id(annotation_id)
        if not annotation:
            raise NotFoundException(
                detail=f"Không tìm thấy ghi chú với ID {annotation_id}"
            )

        # Lọc các trường hợp lệ
        allowed_fields = {
            "content",
            "position_start",
            "position_end",
            "cfi_range",
            "color",
            "note",
            "is_public",
        }
        for key, value in data.items():
            if key in allowed_fields:
                setattr(annotation, key, value)

        await self.db.commit()
        await self.db.refresh(annotation)
        return annotation

    async def delete(self, annotation_id: int) -> bool:
        """Xóa ghi chú.

        Args:
            annotation_id: ID của ghi chú cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.

        Raises:
            NotFoundException: Nếu không tìm thấy ghi chú để xóa (cách tiếp cận khác).
        """
        annotation = await self.get_by_id(annotation_id)
        if not annotation:
            # raise NotFoundException(detail=f"Không tìm thấy ghi chú với ID {annotation_id}")
            return False  # Trả về False nếu không tìm thấy

        await self.db.delete(annotation)
        await self.db.commit()
        return True
