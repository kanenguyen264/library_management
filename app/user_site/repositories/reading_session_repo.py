from typing import Optional, List, Dict, Any, Tuple
from datetime import date, datetime, timedelta
from sqlalchemy import (
    select,
    update,
    delete,
    func,
    or_,
    and_,
    desc,
    asc,
    text,
    extract,
    join,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.reading_session import ReadingSession
from app.user_site.models.user import User
from app.user_site.models.book import Book
from app.user_site.models.chapter import Chapter
from app.core.exceptions import (
    NotFoundException,
    ValidationException,
    ConflictException,
)


class ReadingSessionRepository:
    """Repository cho các thao tác với Phiên Đọc (ReadingSession)."""

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

    async def create(self, session_data: Dict[str, Any]) -> ReadingSession:
        """Tạo phiên đọc mới (bắt đầu một phiên đọc).

        Args:
            session_data: Dict chứa dữ liệu (user_id, book_id, start_time, chapter_id?, start_location?, device_info?).

        Returns:
            Đối tượng ReadingSession đã tạo.

        Raises:
            ValidationException: Nếu thiếu trường, dữ liệu không hợp lệ, hoặc dependencies không tồn tại.
            ConflictException: Nếu có lỗi ràng buộc.
        """
        user_id = session_data.get("user_id")
        book_id = session_data.get("book_id")
        start_time = session_data.get("start_time")
        chapter_id = session_data.get("chapter_id")

        if not all([user_id, book_id, start_time]):
            raise ValidationException(
                "Thiếu thông tin bắt buộc: user_id, book_id, start_time."
            )
        if not isinstance(start_time, datetime):
            raise ValidationException("start_time phải là kiểu datetime.")

        await self._validate_dependencies(user_id, book_id, chapter_id)

        # Lọc dữ liệu
        allowed_fields = {
            col.name
            for col in ReadingSession.__table__.columns
            if col.name not in ["id", "end_time", "duration_seconds", "end_location"]
        }
        """Tạo phiên đọc mới."""
        session = ReadingSession(**session_data)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_by_id(
        self, session_id: int, with_relations: bool = False
    ) -> Optional[ReadingSession]:
        """Lấy phiên đọc theo ID."""
        query = select(ReadingSession).where(ReadingSession.id == session_id)

        if with_relations:
            query = query.options(
                joinedload(ReadingSession.user),
                joinedload(ReadingSession.book),
                joinedload(ReadingSession.chapter),
            )

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        book_id: Optional[int] = None,
        with_relations: bool = True,
    ) -> List[ReadingSession]:
        """Liệt kê phiên đọc của người dùng."""
        query = select(ReadingSession).where(ReadingSession.user_id == user_id)

        if start_date:
            query = query.where(ReadingSession.start_time >= start_date)

        if end_date:
            # Ensure the end date includes the entire day
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.where(ReadingSession.start_time <= end_datetime)

        if book_id:
            query = query.where(ReadingSession.book_id == book_id)

        if with_relations:
            query = query.options(
                joinedload(ReadingSession.book), joinedload(ReadingSession.chapter)
            )

        query = (
            query.order_by(desc(ReadingSession.start_time)).offset(skip).limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(
        self,
        user_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        book_id: Optional[int] = None,
    ) -> int:
        """Đếm số lượng phiên đọc của người dùng."""
        query = select(func.count(ReadingSession.id)).where(
            ReadingSession.user_id == user_id
        )

        if start_date:
            query = query.where(ReadingSession.start_time >= start_date)

        if end_date:
            # Ensure the end date includes the entire day
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.where(ReadingSession.start_time <= end_datetime)

        if book_id:
            query = query.where(ReadingSession.book_id == book_id)

        result = await self.db.execute(query)
        return result.scalar_one()

    async def update(self, session_id: int, data: Dict[str, Any]) -> ReadingSession:
        """Cập nhật thông tin phiên đọc."""
        session = await self.get_by_id(session_id)
        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc với ID {session_id}"
            )

        for key, value in data.items():
            setattr(session, key, value)

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def delete(self, session_id: int) -> None:
        """Xóa phiên đọc."""
        session = await self.get_by_id(session_id)
        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc với ID {session_id}"
            )

        await self.db.delete(session)
        await self.db.commit()

    async def get_reading_stats(
        self, user_id: int, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """Lấy thống kê đọc theo ngày."""
        # Ensure the end date includes the entire day
        end_datetime = datetime.combine(end_date, datetime.max.time())

        # Tạo query để nhóm theo ngày và tính tổng
        query = (
            select(
                func.date(ReadingSession.start_time).label("date"),
                func.sum(ReadingSession.duration_seconds).label("seconds_read"),
                func.count(func.distinct(ReadingSession.book_id)).label("books_count"),
            )
            .where(
                ReadingSession.user_id == user_id,
                ReadingSession.start_time >= start_date,
                ReadingSession.start_time <= end_datetime,
            )
            .group_by(func.date(ReadingSession.start_time))
            .order_by(func.date(ReadingSession.start_time))
        )

        result = await self.db.execute(query)
        return [
            {
                "date": row.date,
                "seconds_read": row.seconds_read,
                "books_count": row.books_count,
            }
            for row in result
        ]

    async def get_reading_streaks(self, user_id: int) -> Dict[str, int]:
        """Tính chuỗi ngày đọc sách liên tục."""
        # Lấy danh sách ngày có phiên đọc
        query = (
            select(func.date(ReadingSession.start_time).label("date"))
            .where(ReadingSession.user_id == user_id)
            .group_by(func.date(ReadingSession.start_time))
            .order_by(func.date(ReadingSession.start_time))
        )

        result = await self.db.execute(query)
        reading_dates = [row.date for row in result]

        if not reading_dates:
            return {"current_streak": 0, "longest_streak": 0}

        # Tính chuỗi hiện tại
        current_streak = 0
        today = date.today()

        # Kiểm tra ngày gần nhất
        if reading_dates[-1] == today:
            current_streak = 1

            # Lùi về kiểm tra các ngày trước đó
            check_date = today - timedelta(days=1)
            i = len(reading_dates) - 2

            while i >= 0 and reading_dates[i] == check_date:
                current_streak += 1
                check_date -= timedelta(days=1)
                i -= 1

        # Tính chuỗi dài nhất
        longest_streak = 1
        current = 1

        for i in range(1, len(reading_dates)):
            if (reading_dates[i] - reading_dates[i - 1]).days == 1:
                current += 1
            else:
                longest_streak = max(longest_streak, current)
                current = 1

        longest_streak = max(longest_streak, current)

        return {"current_streak": current_streak, "longest_streak": longest_streak}

    async def get_reading_totals(
        self,
        user_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Lấy tổng số thời gian đọc và số sách."""
        query = select(
            func.sum(ReadingSession.duration_seconds).label("total_seconds"),
            func.count(func.distinct(ReadingSession.book_id)).label("total_books"),
        ).where(ReadingSession.user_id == user_id)

        if start_date:
            query = query.where(ReadingSession.start_time >= start_date)

        if end_date:
            # Ensure the end date includes the entire day
            end_datetime = datetime.combine(end_date, datetime.max.time())
            query = query.where(ReadingSession.start_time <= end_datetime)

        result = await self.db.execute(query)
        row = result.first()

        return {
            "total_seconds": row.total_seconds or 0,
            "total_books": row.total_books or 0,
        }

    async def get_reading_by_hour(self, user_id: int, days: int = 30) -> Dict[int, int]:
        """Lấy thống kê thời gian đọc theo giờ trong ngày."""
        start_date = date.today() - timedelta(days=days)

        query = (
            select(
                func.extract("hour", ReadingSession.start_time).label("hour"),
                func.sum(ReadingSession.duration_seconds).label("total_seconds"),
            )
            .where(
                ReadingSession.user_id == user_id,
                ReadingSession.start_time >= start_date,
            )
            .group_by(func.extract("hour", ReadingSession.start_time))
            .order_by(func.extract("hour", ReadingSession.start_time))
        )

        result = await self.db.execute(query)

        # Khởi tạo dict với 24 giờ
        hours_dict = {hour: 0 for hour in range(24)}

        # Cập nhật từ kết quả
        for row in result:
            hours_dict[int(row.hour)] = int(row.total_seconds)

        return hours_dict

    async def get_reading_by_weekday(
        self, user_id: int, days: int = 90
    ) -> Dict[int, int]:
        """Lấy thống kê thời gian đọc theo ngày trong tuần."""
        start_date = date.today() - timedelta(days=days)

        query = (
            select(
                func.extract("dow", ReadingSession.start_time).label("weekday"),
                func.sum(ReadingSession.duration_seconds).label("total_seconds"),
            )
            .where(
                ReadingSession.user_id == user_id,
                ReadingSession.start_time >= start_date,
            )
            .group_by(func.extract("dow", ReadingSession.start_time))
            .order_by(func.extract("dow", ReadingSession.start_time))
        )

        result = await self.db.execute(query)

        # Khởi tạo dict với 7 ngày trong tuần (0 = Sunday, 6 = Saturday)
        weekday_dict = {day: 0 for day in range(7)}

        # Cập nhật từ kết quả
        for row in result:
            weekday_dict[int(row.weekday)] = int(row.total_seconds)

        return weekday_dict
