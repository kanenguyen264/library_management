from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.reading_session_repo import ReadingSessionRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.reading_history_repo import ReadingHistoryRepository
from app.user_site.repositories.bookmark_repo import BookmarkRepository
from app.user_site.services.reading_history_service import ReadingHistoryService
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    ConflictException,
)
from app.logs_manager.services import create_performance_log
from app.logs_manager.schemas.performance_log import PerformanceLogCreate
import time
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache
from app.cache.keys import CacheKeyBuilder
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import check_permission
from app.logs_manager.services.user_activity_log_service import UserActivityLogService
from app.core.config import get_settings

settings = get_settings()


class ReadingSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.session_repo = ReadingSessionRepository(db)
        self.book_repo = BookRepository(db)
        self.chapter_repo = ChapterRepository(db)
        self.user_repo = UserRepository(db)
        self.history_repo = ReadingHistoryRepository(db)
        self.bookmark_repo = BookmarkRepository(db)
        self.reading_history_service = ReadingHistoryService(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="reading_sessions", tags=["active_session", "user_sessions"]
    )
    async def start_session(
        self,
        user_id: int,
        book_id: int,
        chapter_id: Optional[int] = None,
        device_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Bắt đầu phiên đọc mới.

        Args:
            user_id: ID của người dùng
            book_id: ID của sách
            chapter_id: ID của chương (tùy chọn)
            device_info: Thông tin thiết bị (tùy chọn)

        Returns:
            Thông tin phiên đọc đã tạo

        Raises:
            NotFoundException: Nếu không tìm thấy sách hoặc chương
            ConflictException: Nếu đã có phiên đọc đang hoạt động
        """
        start_time = time.time()

        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra chương tồn tại nếu có
        if chapter_id:
            chapter = await self.chapter_repo.get_by_id(chapter_id)
            if not chapter:
                raise NotFoundException(
                    detail=f"Không tìm thấy chương với ID {chapter_id}"
                )

            if chapter.book_id != book_id:
                raise BadRequestException(detail="Chương không thuộc về sách này")

        # Kiểm tra có phiên đọc đang hoạt động không
        active_session = await self.session_repo.get_active_session(user_id)
        if active_session:
            # Tự động kết thúc phiên đọc cũ
            await self.end_session(active_session.id)

        # Lấy lịch sử đọc để xác định vị trí cuối
        history = await self.history_repo.get_by_user_and_book(user_id, book_id)
        last_position = history.last_position if history else None
        current_chapter_id = history.chapter_id if history else chapter_id

        # Tạo phiên đọc mới
        session_data = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_id": current_chapter_id or chapter_id,
            "start_position": last_position,
            "start_time": datetime.now(),
            "is_active": True,
            "device_info": device_info and str(device_info) or None,
        }

        session = await self.session_repo.create(session_data)

        # Lấy thông tin sách và chương
        session_chapter = None
        if session.chapter_id:
            session_chapter = await self.chapter_repo.get_by_id(session.chapter_id)

        # Tính thời gian xử lý
        elapsed_ms = (time.time() - start_time) * 1000

        # Log performance
        await create_performance_log(
            self.db,
            PerformanceLogCreate(
                component="reading_session_service",
                operation="start_session",
                duration_ms=elapsed_ms,
                endpoint=None,
                user_id=user_id,
                details={"book_id": book_id, "chapter_id": chapter_id},
            ),
        )

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="START_READING_SESSION",
            resource_type="book",
            resource_id=str(book_id),
            metadata={
                "book_title": book.title,
                "chapter_id": chapter_id,
                "chapter_title": chapter.title if chapter else None,
                "session_id": session.id,
                "device_info": session_data["device_info"],
            },
        )

        # Metrics
        self.metrics.track_user_activity("start_reading_session", "registered")

        return {
            "id": session.id,
            "user_id": session.user_id,
            "book_id": session.book_id,
            "chapter_id": session.chapter_id,
            "start_position": session.start_position,
            "start_time": session.start_time,
            "is_active": session.is_active,
            "book": {
                "id": book.id,
                "title": book.title,
                "cover_image": book.cover_image,
            },
            "chapter": session_chapter
            and {
                "id": session_chapter.id,
                "title": session_chapter.title,
                "number": session_chapter.number,
            }
            or None,
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="reading_sessions", tags=["session_details"])
    async def update_session(
        self, session_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin phiên đọc sách.

        Args:
            session_id: ID của phiên đọc sách
            data: Dữ liệu cập nhật

        Returns:
            Thông tin phiên đọc sách đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy phiên đọc sách
            BadRequestException: Nếu dữ liệu không hợp lệ
            ForbiddenException: Nếu phiên đọc sách đã kết thúc
        """
        # Kiểm tra phiên đọc sách tồn tại
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc sách với ID {session_id}"
            )

        # Kiểm tra phiên đọc sách có đang hoạt động không
        if not session.is_active:
            raise ForbiddenException(
                detail="Không thể cập nhật phiên đọc sách đã kết thúc"
            )

        # Xử lý trường hợp thay đổi chapter_id
        if "chapter_id" in data and data["chapter_id"] != session.chapter_id:
            # Kiểm tra chương tồn tại
            new_chapter_id = data["chapter_id"]
            if new_chapter_id:
                chapter = await self.chapter_repo.get_by_id(new_chapter_id)
                if not chapter:
                    raise NotFoundException(
                        detail=f"Không tìm thấy chương với ID {new_chapter_id}"
                    )
                if chapter.book_id != session.book_id:
                    raise BadRequestException(detail="Chương không thuộc sách này")

        # Không cho phép thay đổi một số trường
        forbidden_fields = ["user_id", "book_id", "start_time", "end_time", "is_active"]
        for field in forbidden_fields:
            if field in data:
                del data[field]

        # Cập nhật phiên đọc sách
        updated = await self.session_repo.update(session_id, data)

        # Lấy thông tin sách và chương
        book = await self.book_repo.get_by_id(updated.book_id)
        chapter = None
        if updated.chapter_id:
            chapter = await self.chapter_repo.get_by_id(updated.chapter_id)

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=updated.user_id,
            activity_type="UPDATE_READING_SESSION",
            resource_type="book",
            resource_id=str(updated.book_id),
            metadata={
                "book_title": book.title if book else None,
                "chapter_id": updated.chapter_id,
                "chapter_title": chapter.title if chapter else None,
                "session_id": updated.id,
                "changes": data,
            },
        )

        return {
            "id": updated.id,
            "user_id": updated.user_id,
            "book_id": updated.book_id,
            "book_title": book.title if book else None,
            "chapter_id": updated.chapter_id,
            "chapter_title": chapter.title if chapter else None,
            "start_time": updated.start_time,
            "end_time": updated.end_time,
            "duration_minutes": updated.duration_minutes,
            "is_active": updated.is_active,
            "pages_read": updated.pages_read,
            "current_position": updated.current_position,
            "device_info": updated.device_info,
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="reading_sessions",
        tags=["session_details", "active_session", "user_sessions"],
    )
    async def end_session(
        self,
        session_id: int,
        pages_read: Optional[int] = None,
        current_position: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Kết thúc phiên đọc sách.

        Args:
            session_id: ID của phiên đọc sách
            pages_read: Số trang đã đọc (tùy chọn)
            current_position: Vị trí hiện tại (tùy chọn)

        Returns:
            Thông tin phiên đọc sách đã kết thúc

        Raises:
            NotFoundException: Nếu không tìm thấy phiên đọc sách
            BadRequestException: Nếu dữ liệu không hợp lệ
            ForbiddenException: Nếu phiên đọc sách đã kết thúc
        """
        # Kiểm tra phiên đọc sách tồn tại
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc sách với ID {session_id}"
            )

        # Kiểm tra phiên đọc sách có đang hoạt động không
        if not session.is_active:
            raise ForbiddenException(detail="Phiên đọc sách đã kết thúc")

        # Tính thời gian kết thúc và thời lượng
        end_time = datetime.now()
        duration_minutes = (end_time - session.start_time).total_seconds() / 60

        # Chuẩn bị dữ liệu cập nhật
        update_data = {
            "is_active": False,
            "end_time": end_time,
            "duration_minutes": round(duration_minutes, 2),
        }

        if pages_read is not None:
            update_data["pages_read"] = pages_read

        if current_position is not None:
            update_data["current_position"] = current_position

        # Cập nhật phiên đọc sách
        updated = await self.session_repo.update(session_id, update_data)

        # Ghi lại hoạt động đọc sách vào lịch sử
        await self.reading_history_service.record_reading_activity(
            user_id=session.user_id,
            book_id=session.book_id,
            chapter_id=session.chapter_id,
            pages_read=pages_read,
            minutes_spent=round(duration_minutes),
        )

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=updated.user_id,
            activity_type="END_READING_SESSION",
            resource_type="book",
            resource_id=str(updated.book_id),
            metadata={
                "book_title": updated.book_title,
                "chapter_id": updated.chapter_id,
                "chapter_title": updated.chapter_title,
                "session_id": updated.id,
                "reading_time_minutes": round(duration_minutes),
                "pages_read": updated.pages_read,
            },
        )

        # Metrics
        self.metrics.track_user_activity("end_reading_session", "registered")
        if pages_read:
            self.metrics.track_reading_pages(pages_read)

        return {
            "id": updated.id,
            "user_id": updated.user_id,
            "book_id": updated.book_id,
            "book_title": updated.book_title,
            "chapter_id": updated.chapter_id,
            "chapter_title": updated.chapter_title,
            "start_time": updated.start_time,
            "end_time": updated.end_time,
            "duration_minutes": updated.duration_minutes,
            "is_active": updated.is_active,
            "pages_read": updated.pages_read,
            "current_position": updated.current_position,
            "device_info": updated.device_info,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="reading_sessions", tags=["session_details"])
    async def get_session(self, session_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin phiên đọc sách.

        Args:
            session_id: ID của phiên đọc sách

        Returns:
            Thông tin phiên đọc sách

        Raises:
            NotFoundException: Nếu không tìm thấy phiên đọc sách
        """
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc sách với ID {session_id}"
            )

        # Lấy thông tin sách và chương
        book = await self.book_repo.get_by_id(session.book_id)
        chapter = None
        if session.chapter_id:
            chapter = await self.chapter_repo.get_by_id(session.chapter_id)

        # Tính thời lượng hiện tại nếu phiên đang hoạt động
        duration_minutes = session.duration_minutes
        if session.is_active:
            duration_minutes = (
                datetime.now() - session.start_time
            ).total_seconds() / 60
            duration_minutes = round(duration_minutes, 2)

        return {
            "id": session.id,
            "user_id": session.user_id,
            "book_id": session.book_id,
            "book_title": book.title if book else None,
            "chapter_id": session.chapter_id,
            "chapter_title": chapter.title if chapter else None,
            "start_time": session.start_time,
            "end_time": session.end_time,
            "duration_minutes": duration_minutes,
            "is_active": session.is_active,
            "pages_read": session.pages_read,
            "current_position": session.current_position,
            "device_info": session.device_info,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=60, namespace="reading_sessions", tags=["active_session"])
    async def get_active_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Lấy phiên đọc sách đang hoạt động của người dùng.

        Args:
            user_id: ID của người dùng

        Returns:
            Thông tin phiên đọc sách đang hoạt động hoặc None

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        session = await self.session_repo.get_active_session(user_id)
        if not session:
            return None

        # Lấy thông tin sách và chương
        book = await self.book_repo.get_by_id(session.book_id)
        chapter = None
        if session.chapter_id:
            chapter = await self.chapter_repo.get_by_id(session.chapter_id)

        # Tính thời lượng hiện tại
        duration_minutes = (datetime.now() - session.start_time).total_seconds() / 60
        duration_minutes = round(duration_minutes, 2)

        return {
            "id": session.id,
            "user_id": session.user_id,
            "book_id": session.book_id,
            "book_title": book.title if book else None,
            "chapter_id": session.chapter_id,
            "chapter_title": chapter.title if chapter else None,
            "start_time": session.start_time,
            "duration_minutes": duration_minutes,
            "is_active": session.is_active,
            "pages_read": session.pages_read,
            "current_position": session.current_position,
            "device_info": session.device_info,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="reading_sessions", tags=["user_sessions"])
    async def list_user_sessions(
        self,
        user_id: int,
        book_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách phiên đọc sách của người dùng.

        Args:
            user_id: ID của người dùng
            book_id: Lọc theo ID sách (tùy chọn)
            start_date: Lọc từ ngày (tùy chọn)
            end_date: Lọc đến ngày (tùy chọn)
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách phiên đọc sách và thông tin phân trang

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Lấy danh sách phiên đọc sách
        sessions = await self.session_repo.list_by_user(
            user_id=user_id,
            book_id=book_id,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )

        total = await self.session_repo.count_by_user(
            user_id=user_id, book_id=book_id, start_date=start_date, end_date=end_date
        )

        # Thu thập thông tin sách và chương
        book_ids = set(session.book_id for session in sessions)
        books = {
            book.id: book for book in await self.book_repo.get_by_ids(list(book_ids))
        }

        chapter_ids = set(
            session.chapter_id for session in sessions if session.chapter_id
        )
        chapters = {
            chapter.id: chapter
            for chapter in await self.chapter_repo.get_by_ids(list(chapter_ids))
        }

        items = []
        for session in sessions:
            book = books.get(session.book_id)
            chapter = chapters.get(session.chapter_id) if session.chapter_id else None

            items.append(
                {
                    "id": session.id,
                    "book_id": session.book_id,
                    "book_title": book.title if book else None,
                    "book_cover": book.cover_image if book else None,
                    "chapter_id": session.chapter_id,
                    "chapter_title": chapter.title if chapter else None,
                    "start_time": session.start_time,
                    "end_time": session.end_time,
                    "duration_minutes": session.duration_minutes,
                    "is_active": session.is_active,
                    "pages_read": session.pages_read,
                    "device_info": session.device_info,
                }
            )

        return {"items": items, "total": total, "skip": skip, "limit": limit}

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="reading_sessions", tags=["reading_stats"])
    async def get_reading_time_stats(
        self, user_id: int, period: str = "all", book_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thống kê thời gian đọc sách.

        Args:
            user_id: ID của người dùng
            period: Thời kỳ thống kê ('day', 'week', 'month', 'year', 'all')
            book_id: ID của sách (tùy chọn)

        Returns:
            Thống kê thời gian đọc sách

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Tính toán thời gian dựa trên period
        today = datetime.now()
        start_date = None
        end_date = today

        if period == "day":
            start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            # Lấy ngày đầu tuần (thứ Hai)
            start_date = today - timedelta(days=today.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "month":
            # Lấy ngày đầu tháng
            start_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == "year":
            # Lấy ngày đầu năm
            start_date = today.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        elif period != "all":
            valid_periods = ["day", "week", "month", "year", "all"]
            raise BadRequestException(
                detail=f"Thời kỳ không hợp lệ. Cho phép: {', '.join(valid_periods)}"
            )

        # Lấy thống kê thời gian đọc sách
        stats = await self.session_repo.get_reading_time_stats(
            user_id=user_id, book_id=book_id, start_date=start_date, end_date=end_date
        )

        # Chuyển đổi phút thành giờ:phút
        total_minutes = stats.get("total_minutes", 0) or 0
        hours = total_minutes // 60
        minutes = total_minutes % 60

        return {
            "total_sessions": stats.get("total_sessions", 0),
            "total_minutes": total_minutes,
            "formatted_time": f"{hours}h {minutes}m",
            "avg_session_minutes": stats.get("avg_session_minutes", 0),
            "period": period,
            "book_id": book_id,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=7200, namespace="reading_sessions", tags=["reading_heatmap"])
    async def get_reading_heatmap(
        self, user_id: int, year: int, book_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy dữ liệu heatmap thời gian đọc sách theo ngày.

        Args:
            user_id: ID của người dùng
            year: Năm
            book_id: ID của sách (tùy chọn)

        Returns:
            Dữ liệu heatmap thời gian đọc sách

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra dữ liệu đầu vào
        if year < 2000 or year > 2100:
            raise BadRequestException(detail="Năm không hợp lệ")

        # Thiết lập khoảng thời gian
        start_date = datetime(year, 1, 1, 0, 0, 0)
        end_date = datetime(year, 12, 31, 23, 59, 59)

        # Lấy dữ liệu đọc sách theo ngày
        daily_stats = await self.session_repo.get_daily_reading_stats(
            user_id=user_id, book_id=book_id, start_date=start_date, end_date=end_date
        )

        # Định dạng kết quả
        result = {"user_id": user_id, "year": year, "book_id": book_id, "data": []}

        # Chuyển đổi dữ liệu thành định dạng heatmap
        for date_str, minutes in daily_stats.items():
            result["data"].append(
                {
                    "date": date_str,
                    "minutes": minutes,
                    "intensity": self._calculate_intensity(minutes),
                }
            )

        return result

    def _calculate_intensity(self, minutes: float) -> int:
        """
        Tính toán cường độ màu cho heatmap.

        Args:
            minutes: Số phút đọc sách

        Returns:
            Cường độ từ 0-4
        """
        if minutes == 0:
            return 0
        elif minutes < 15:
            return 1
        elif minutes < 30:
            return 2
        elif minutes < 60:
            return 3
        else:
            return 4

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="reading_sessions", tags=["session_details", "active_session"]
    )
    async def update_current_position(
        self, session_id: int, position: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật vị trí đọc hiện tại.

        Args:
            session_id: ID của phiên đọc sách
            position: Thông tin vị trí đọc

        Returns:
            Thông tin phiên đọc sách đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy phiên đọc sách
            ForbiddenException: Nếu phiên đọc sách đã kết thúc
        """
        # Kiểm tra phiên đọc sách tồn tại
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc sách với ID {session_id}"
            )

        # Kiểm tra phiên đọc sách có đang hoạt động không
        if not session.is_active:
            raise ForbiddenException(
                detail="Không thể cập nhật vị trí đọc cho phiên đã kết thúc"
            )

        # Cập nhật vị trí đọc
        update_data = {
            "current_position": position,
            "last_activity_time": datetime.now(),
        }

        # Cập nhật phiên đọc sách
        updated = await self.session_repo.update(session_id, update_data)

        return {
            "id": updated.id,
            "current_position": updated.current_position,
            "last_activity_time": updated.last_activity_time,
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="reading_sessions", tags=["active_session"])
    async def heartbeat(self, session_id: int) -> Dict[str, Any]:
        """
        Cập nhật thời gian hoạt động cuối cùng để duy trì phiên đọc sách.

        Args:
            session_id: ID của phiên đọc sách

        Returns:
            Trạng thái cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy phiên đọc sách
            ForbiddenException: Nếu phiên đọc sách đã kết thúc
        """
        # Kiểm tra phiên đọc sách tồn tại
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundException(
                detail=f"Không tìm thấy phiên đọc sách với ID {session_id}"
            )

        # Kiểm tra phiên đọc sách có đang hoạt động không
        if not session.is_active:
            raise ForbiddenException(detail="Không thể cập nhật cho phiên đã kết thúc")

        # Cập nhật thời gian hoạt động cuối cùng
        update_data = {"last_activity_time": datetime.now()}

        # Cập nhật phiên đọc sách
        await self.session_repo.update(session_id, update_data)

        # Tính thời lượng hiện tại
        duration_minutes = (datetime.now() - session.start_time).total_seconds() / 60

        return {
            "id": session.id,
            "is_active": True,
            "duration_minutes": round(duration_minutes, 2),
            "heartbeat_time": datetime.now(),
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="reading_sessions", tags=["active_session", "user_sessions"]
    )
    async def cleanup_inactive_sessions(
        self, timeout_minutes: int = 30
    ) -> Dict[str, Any]:
        """
        Dọn dẹp các phiên đọc sách không hoạt động.

        Args:
            timeout_minutes: Thời gian chờ trước khi đóng phiên (phút)

        Returns:
            Số lượng phiên đã đóng
        """
        # Tính thời gian giới hạn
        cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)

        # Lấy danh sách các phiên chưa hoạt động trong thời gian quy định
        inactive_sessions = await self.session_repo.get_inactive_sessions(cutoff_time)

        count = 0
        for session in inactive_sessions:
            # Kết thúc phiên đọc sách
            try:
                await self.end_session(session.id)
                count += 1
            except Exception:
                # Bỏ qua lỗi và tiếp tục xử lý các phiên khác
                pass

        return {
            "closed_sessions": count,
            "timeout_minutes": timeout_minutes,
            "cutoff_time": cutoff_time,
        }
