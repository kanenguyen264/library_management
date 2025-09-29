from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func, update, delete, desc, asc, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from app.user_site.models.reading_history import ReadingHistory
from app.user_site.models.book import Book
from app.user_site.models.user import User  # Để kiểm tra user_id
from app.user_site.models.chapter import Chapter  # Để kiểm tra chapter_id
from app.core.exceptions import (
    NotFoundException,
    ValidationException,
    ConflictException,
)


class ReadingHistoryRepository:
    """Repository cho các thao tác với Lịch sử Đọc (ReadingHistory)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def _validate_dependencies(
        self, user_id: int, book_id: int, chapter_id: Optional[int] = None
    ):
        """(Nội bộ) Kiểm tra sự tồn tại của user, book và chapter (nếu có)."""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValidationException(f"Người dùng với ID {user_id} không tồn tại.")
        book = await self.db.get(Book, book_id)
        if not book:
            raise ValidationException(f"Sách với ID {book_id} không tồn tại.")
        if chapter_id:
            chapter = await self.db.get(Chapter, chapter_id)
            if not chapter:
                raise ValidationException(f"Chương với ID {chapter_id} không tồn tại.")
            if chapter.book_id != book_id:
                raise ValidationException(
                    f"Chương {chapter_id} không thuộc về sách {book_id}."
                )

    async def create(self, data: Dict[str, Any]) -> ReadingHistory:
        """Tạo một bản ghi lịch sử đọc mới.

        Args:
            data: Dict chứa dữ liệu cho lịch sử mới (user_id, book_id, chapter_id?, ...).

        Returns:
            Đối tượng ReadingHistory đã được tạo.

        Raises:
            ValidationException: Nếu thiếu trường bắt buộc hoặc dependencies không tồn tại.
            ConflictException: Nếu đã tồn tại bản ghi cho user-book-chapter này.
        """
        user_id = data.get("user_id")
        book_id = data.get("book_id")
        chapter_id = data.get("chapter_id")

        if not user_id or not book_id:
            raise ValidationException("Thiếu thông tin bắt buộc: user_id, book_id.")

        await self._validate_dependencies(user_id, book_id, chapter_id)

        # Lọc các trường hợp lệ
        allowed_fields = {
            col.name
            for col in ReadingHistory.__table__.columns
            if col.name not in ["id", "created_at", "updated_at"]
        }
        filtered_data = {
            k: v for k, v in data.items() if k in allowed_fields and v is not None
        }

        # Validate percentage
        if "progress_percentage" in filtered_data:
            perc = filtered_data["progress_percentage"]
            if not isinstance(perc, (int, float)) or not (0 <= perc <= 100):
                raise ValidationException(
                    f"Tỷ lệ phần trăm tiến độ không hợp lệ: {perc}. Phải từ 0 đến 100."
                )

        # Đảm bảo last_read_at được cập nhật
        filtered_data["last_read_at"] = datetime.now(timezone.utc)

        history = ReadingHistory(**filtered_data)
        self.db.add(history)
        try:
            await self.db.commit()
            await self.db.refresh(
                history, attribute_names=["user", "book", "chapter"]
            )  # Tải lại quan hệ nếu cần
            return history
        except IntegrityError as e:
            await self.db.rollback()
            # Kiểm tra xem có phải lỗi unique constraint không
            existing = await self.get_by_user_book_chapter(user_id, book_id, chapter_id)
            if existing:
                raise ConflictException(
                    f"Lịch sử đọc cho user {user_id}, sách {book_id}, chương {chapter_id} đã tồn tại."
                )
            raise ConflictException(f"Không thể tạo lịch sử đọc: {e}")

    async def get_by_id(
        self, history_id: int, with_relations: List[str] = None
    ) -> Optional[ReadingHistory]:
        """Lấy lịch sử đọc theo ID.

        Args:
            history_id: ID của lịch sử đọc.
            with_relations: Danh sách tên quan hệ cần tải (vd: ['user', 'book', 'chapter']).

        Returns:
            Đối tượng ReadingHistory hoặc None.
        """
        query = select(ReadingHistory).where(ReadingHistory.id == history_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(ReadingHistory.user))
            if "book" in with_relations:
                options.append(selectinload(ReadingHistory.book))
            if "chapter" in with_relations:
                options.append(selectinload(ReadingHistory.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_book_chapter(
        self,
        user_id: int,
        book_id: int,
        chapter_id: Optional[int] = None,
        with_relations: List[str] = None,
    ) -> Optional[ReadingHistory]:
        """Lấy lịch sử đọc theo user_id, book_id và chapter_id (tùy chọn).

        Args:
            user_id: ID người dùng.
            book_id: ID sách.
            chapter_id: ID chương (nếu có).
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Đối tượng ReadingHistory hoặc None.
        """
        query = select(ReadingHistory).where(
            ReadingHistory.user_id == user_id, ReadingHistory.book_id == book_id
        )

        if chapter_id is not None:
            query = query.where(ReadingHistory.chapter_id == chapter_id)
        else:
            # Nếu không cung cấp chapter_id, có thể cần tìm bản ghi không có chapter_id
            # Hoặc bản ghi đại diện cho sách (tùy logic ứng dụng)
            query = query.where(ReadingHistory.chapter_id.is_(None))

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(ReadingHistory.user))
            if "book" in with_relations:
                options.append(selectinload(ReadingHistory.book))
            if "chapter" in with_relations:
                options.append(selectinload(ReadingHistory.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "last_read_at",  # Thêm các tùy chọn sort
        sort_desc: bool = True,
        with_relations: List[str] = ["book", "chapter"],  # Mặc định tải book, chapter
    ) -> List[ReadingHistory]:
        """Lấy danh sách lịch sử đọc theo user_id.

        Args:
            user_id: ID người dùng.
            skip: Số lượng bỏ qua.
            limit: Giới hạn số lượng.
            sort_by: Trường sắp xếp ('last_read_at', 'created_at', 'progress_percentage').
            sort_desc: Sắp xếp giảm dần.
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Danh sách ReadingHistory.
        """
        query = select(ReadingHistory).where(ReadingHistory.user_id == user_id)

        # Sắp xếp
        sort_column = ReadingHistory.last_read_at  # Mặc định
        if sort_by == "created_at":
            sort_column = ReadingHistory.created_at
        elif sort_by == "progress_percentage":
            sort_column = ReadingHistory.progress_percentage

        order = desc(sort_column) if sort_desc else asc(sort_column)
        query = query.order_by(order)

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load các mối quan hệ
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(ReadingHistory.user))
            if "book" in with_relations:
                options.append(selectinload(ReadingHistory.book))
            if "chapter" in with_relations:
                options.append(selectinload(ReadingHistory.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int) -> int:
        """Đếm số lượng bản ghi lịch sử đọc của người dùng."""
        query = (
            select(func.count(ReadingHistory.id))
            .select_from(ReadingHistory)
            .where(ReadingHistory.user_id == user_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update(
        self, history_id: int, data: Dict[str, Any]
    ) -> Optional[ReadingHistory]:
        """Cập nhật thông tin lịch sử đọc bằng ID.

        Args:
            history_id: ID của lịch sử cần cập nhật.
            data: Dict chứa dữ liệu cập nhật.

        Returns:
            Đối tượng ReadingHistory đã cập nhật hoặc None nếu không tìm thấy.

        Raises:
             ValidationException: Nếu dữ liệu không hợp lệ.
        """
        history = await self.get_by_id(history_id)
        if not history:
            return None  # Hoặc raise NotFoundException tùy logic gọi

        allowed_fields = {
            "progress_percentage",
            "last_position",
            "time_spent_seconds",
            "is_completed",
        }
        updated = False

        for key, value in data.items():
            if key in allowed_fields and value is not None:
                # Validate percentage
                if key == "progress_percentage":
                    perc = value
                    if not isinstance(perc, (int, float)) or not (0 <= perc <= 100):
                        raise ValidationException(
                            f"Tỷ lệ phần trăm tiến độ không hợp lệ: {perc}. Phải từ 0 đến 100."
                        )
                    # Tự động đánh dấu hoàn thành nếu progress >= 100
                    if perc >= 100:
                        history.is_completed = True

                if getattr(history, key) != value:
                    setattr(history, key, value)
                    updated = True

        if updated:
            history.last_read_at = (
                datetime.now(timezone.utc)
            )  # Luôn cập nhật last_read_at khi có thay đổi
            await self.db.commit()
            await self.db.refresh(history, attribute_names=["user", "book", "chapter"])

        return history

    async def delete(self, history_id: int) -> bool:
        """Xóa lịch sử đọc bằng ID.

        Args:
            history_id: ID lịch sử cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        query = delete(ReadingHistory).where(ReadingHistory.id == history_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def delete_by_user(self, user_id: int) -> int:
        """Xóa tất cả lịch sử đọc của một người dùng.

        Args:
            user_id: ID người dùng.

        Returns:
            Số lượng bản ghi đã xóa.
        """
        query = delete(ReadingHistory).where(ReadingHistory.user_id == user_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def get_or_create(
        self,
        user_id: int,
        book_id: int,
        chapter_id: Optional[int] = None,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> Tuple[ReadingHistory, bool]:
        """Lấy hoặc tạo mới lịch sử đọc.

        Args:
            user_id: ID người dùng.
            book_id: ID sách.
            chapter_id: ID chương (tùy chọn).
            defaults: Giá trị mặc định nếu tạo mới.

        Returns:
            Tuple[ReadingHistory, bool]: (Đối tượng lịch sử, True nếu được tạo mới).
        """
        existing = await self.get_by_user_book_chapter(user_id, book_id, chapter_id)
        if existing:
            return existing, False

        create_data = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "progress_percentage": 0.0,
            "time_spent_seconds": 0,
            "is_completed": False,
        }
        if defaults:
            create_data.update(defaults)

        try:
            created_history = await self.create(create_data)
            return created_history, True
        except ConflictException:
            # Race condition: ai đó vừa tạo, thử lấy lại
            existing = await self.get_by_user_book_chapter(user_id, book_id, chapter_id)
            if existing:
                return existing, False
            else:
                # Lỗi khác không mong muốn
                raise  # Re-raise the exception

    async def update_progress(
        self,
        user_id: int,
        book_id: int,
        progress_data: Dict[str, Any],
        chapter_id: Optional[int] = None,
    ) -> ReadingHistory:
        """Cập nhật hoặc tạo mới tiến độ đọc sách.

        Args:
            user_id: ID người dùng.
            book_id: ID sách.
            progress_data: Dict chứa dữ liệu tiến độ cập nhật
                           (vd: progress_percentage, last_position, time_spent_increment).
            chapter_id: ID chương (tùy chọn).

        Returns:
            Đối tượng ReadingHistory đã được cập nhật hoặc tạo mới.

        Raises:
             ValidationException: Nếu dữ liệu không hợp lệ.
        """
        history, created = await self.get_or_create(user_id, book_id, chapter_id)

        allowed_fields = {
            "progress_percentage",
            "last_position",
            "time_spent_increment",
            "is_completed",
        }
        update_payload = {}
        time_increment = progress_data.get("time_spent_increment", 0)

        for key, value in progress_data.items():
            if key in allowed_fields and value is not None:
                # Xử lý cộng dồn thời gian
                if key == "time_spent_increment":
                    if not isinstance(time_increment, int) or time_increment < 0:
                        raise ValidationException(
                            f"Giá trị tăng thời gian không hợp lệ: {time_increment}"
                        )
                    continue  # Đã lấy giá trị ở trên

                # Validate percentage
                if key == "progress_percentage":
                    perc = value
                    if not isinstance(perc, (int, float)) or not (0 <= perc <= 100):
                        raise ValidationException(
                            f"Tỷ lệ phần trăm tiến độ không hợp lệ: {perc}. Phải từ 0 đến 100."
                        )
                    # Tự động đánh dấu hoàn thành nếu progress >= 100
                    if perc >= 100:
                        update_payload["is_completed"] = True

                update_payload[key] = value

        if not update_payload and time_increment <= 0:
            return history  # Không có gì để cập nhật

        # Áp dụng cập nhật
        updated = False
        for key, value in update_payload.items():
            if getattr(history, key) != value:
                setattr(history, key, value)
                updated = True

        # Cập nhật thời gian
        if time_increment > 0:
            history.time_spent_seconds = (
                history.time_spent_seconds or 0
            ) + time_increment
            updated = True

        if updated or created:
            history.last_read_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(history, attribute_names=["user", "book", "chapter"])

        return history

    async def list_recent_books(
        self, user_id: int, limit: int = 5, with_relations: List[str] = ["book"]
    ) -> List[ReadingHistory]:
        """Lấy danh sách lịch sử đọc gần đây nhất cho mỗi sách.

        Args:
            user_id: ID người dùng.
            limit: Giới hạn số lượng sách trả về.
            with_relations: Danh sách quan hệ cần tải cho ReadingHistory.

        Returns:
            Danh sách các bản ghi ReadingHistory gần đây nhất cho mỗi sách.
        """
        # Subquery để tìm last_read_at mới nhất cho mỗi book_id của user
        latest_read_subquery = (
            select(
                ReadingHistory.book_id,
                func.max(ReadingHistory.last_read_at).label("latest_read_at"),
            )
            .where(ReadingHistory.user_id == user_id)
            .group_by(ReadingHistory.book_id)
            .subquery()
        )

        # Query chính để lấy các bản ghi ReadingHistory khớp với latest_read_at
        # Lưu ý: Có thể có nhiều bản ghi history cho cùng 1 book nếu last_read_at trùng nhau (vd: đọc nhiều chapter cùng lúc)
        # Cần quyết định logic xử lý (vd: lấy bản ghi có chapter_id lớn nhất?)
        # Tạm thời lấy một bản ghi bất kỳ khớp với latest_read_at.
        # Để đơn giản, join và lấy history có last_read_at khớp
        query = (
            select(ReadingHistory)
            .join(
                latest_read_subquery,
                and_(
                    ReadingHistory.book_id == latest_read_subquery.c.book_id,
                    ReadingHistory.last_read_at
                    == latest_read_subquery.c.latest_read_at,
                    ReadingHistory.user_id
                    == user_id,  # Thêm điều kiện user_id ở đây để tối ưu join
                ),
            )
            .order_by(desc(latest_read_subquery.c.latest_read_at))
            .limit(limit)
        )

        # Load book relationship (và các quan hệ khác nếu cần)
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(ReadingHistory.user))
            if "book" in with_relations:
                options.append(selectinload(ReadingHistory.book))
            if "chapter" in with_relations:
                options.append(selectinload(ReadingHistory.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        # Dùng unique() để xử lý trường hợp có nhiều chapter cùng last_read_at cho 1 book
        # Nó sẽ trả về các đối tượng ReadingHistory riêng biệt
        return result.scalars().unique().all()

    async def mark_as_completed(self, history_id: int) -> Optional[ReadingHistory]:
        """Đánh dấu một bản ghi lịch sử là đã hoàn thành đọc.

        Args:
            history_id: ID của bản ghi lịch sử.

        Returns:
            Đối tượng ReadingHistory đã cập nhật hoặc None nếu không tìm thấy.
        """
        return await self.update(
            history_id, {"is_completed": True, "progress_percentage": 100.0}
        )

    async def get_reading_stats_by_user(self, user_id: int) -> Dict[str, Any]:
        """Lấy thống kê đọc sách của người dùng.

        Returns:
            Dict chứa: books_in_progress, books_completed, total_time_seconds.
        """
        # Đếm số sách đang đọc (có bản ghi history nhưng chưa completed)
        in_progress_query = (
            select(func.count(distinct(ReadingHistory.book_id)))
            .select_from(ReadingHistory)
            .where(
                ReadingHistory.user_id == user_id, ReadingHistory.is_completed == False
            )
        )
        in_progress_result = await self.db.execute(in_progress_query)
        books_in_progress = in_progress_result.scalar_one() or 0

        # Đếm số sách đã hoàn thành (có bản ghi history và is_completed = True)
        completed_books_query = (
            select(func.count(distinct(ReadingHistory.book_id)))
            .select_from(ReadingHistory)
            .where(
                ReadingHistory.user_id == user_id, ReadingHistory.is_completed == True
            )
        )
        completed_result = await self.db.execute(completed_books_query)
        books_completed = completed_result.scalar_one() or 0

        # Tính tổng thời gian đọc từ tất cả các bản ghi history của user
        time_spent_query = (
            select(func.sum(ReadingHistory.time_spent_seconds))
            .select_from(ReadingHistory)
            .where(ReadingHistory.user_id == user_id)
        )
        time_result = await self.db.execute(time_spent_query)
        total_time_seconds = time_result.scalar_one() or 0

        return {
            "books_in_progress": books_in_progress,
            "books_completed": books_completed,
            "total_time_seconds": total_time_seconds,
        }
