from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.reading_history_repo import ReadingHistoryRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.services.reading_goal_service import ReadingGoalService
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
)
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


class ReadingHistoryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.reading_history_repo = ReadingHistoryRepository(db)
        self.book_repo = BookRepository(db)
        self.chapter_repo = ChapterRepository(db)
        self.user_repo = UserRepository(db)
        self.reading_goal_service = ReadingGoalService(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="reading_history", tags=["user_history", "book_history"]
    )
    async def record_reading_activity(
        self,
        user_id: int,
        book_id: int,
        chapter_id: Optional[int] = None,
        pages_read: Optional[int] = None,
        minutes_spent: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Ghi lại hoạt động đọc sách của người dùng.

        Args:
            user_id: ID người dùng
            book_id: ID sách
            chapter_id: ID chương (tùy chọn)
            pages_read: Số trang đã đọc (tùy chọn)
            minutes_spent: Số phút đã dành để đọc (tùy chọn)

        Returns:
            Thông tin hoạt động đọc sách đã ghi lại

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng, sách hoặc chương
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra chương tồn tại (nếu có)
        chapter = None
        if chapter_id:
            chapter = await self.chapter_repo.get_by_id(chapter_id)
            if not chapter:
                raise NotFoundException(f"Không tìm thấy chương với ID {chapter_id}")

            if chapter.book_id != book_id:
                raise BadRequestException("Chương không thuộc sách này")

        # Kiểm tra dữ liệu đầu vào
        if not pages_read and not minutes_spent:
            raise BadRequestException("Cần cung cấp số trang đọc hoặc thời gian đọc")

        if pages_read is not None and pages_read <= 0:
            raise BadRequestException("Số trang đọc phải lớn hơn 0")

        if minutes_spent is not None and minutes_spent <= 0:
            raise BadRequestException("Thời gian đọc phải lớn hơn 0")

        # Tạo bản ghi hoạt động đọc sách
        data = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "pages_read": pages_read,
            "minutes_spent": minutes_spent,
            "read_date": datetime.now().date(),
            "created_at": datetime.now(),
        }

        activity = await self.reading_history_repo.create(data)

        # Cập nhật tiến độ mục tiêu đọc sách
        try:
            if pages_read:
                await self.reading_goal_service.track_pages_read(user_id, pages_read)

            if minutes_spent:
                await self.reading_goal_service.track_reading_time(
                    user_id, minutes_spent
                )
        except Exception as e:
            # Ghi log lỗi nhưng không fail request
            print(f"Lỗi cập nhật tiến độ mục tiêu: {str(e)}")

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="READ_BOOK",
            resource_type="book",
            resource_id=str(book_id),
            metadata={
                "book_title": book.title,
                "chapter_id": chapter_id,
                "chapter_title": chapter.title if chapter else None,
                "pages_read": pages_read,
                "minutes_spent": minutes_spent,
            },
        )

        # Metrics
        self.metrics.track_user_activity("read_book", "registered")
        if pages_read:
            self.metrics.track_reading_pages(pages_read)
        if minutes_spent:
            self.metrics.track_reading_time(minutes_spent)

        return {
            "id": activity.id,
            "user_id": activity.user_id,
            "book_id": activity.book_id,
            "chapter_id": activity.chapter_id,
            "pages_read": activity.pages_read,
            "minutes_spent": activity.minutes_spent,
            "read_date": activity.read_date,
            "created_at": activity.created_at,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="reading_history", tags=["activity_details"])
    async def get_reading_activity(self, activity_id: int) -> Dict[str, Any]:
        """Lấy thông tin hoạt động đọc sách.

        Args:
            activity_id: ID của hoạt động đọc sách

        Returns:
            Thông tin hoạt động đọc sách

        Raises:
            NotFoundException: Nếu không tìm thấy hoạt động đọc sách
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("reading_activity", activity_id)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy hoạt động đọc sách
        activity = await self.reading_history_repo.get_by_id(activity_id)
        if not activity:
            raise NotFoundException(
                f"Không tìm thấy hoạt động đọc sách với ID {activity_id}"
            )

        # Lấy thêm thông tin sách và chương
        book = await self.book_repo.get_by_id(activity.book_id)
        chapter = None
        if activity.chapter_id:
            chapter = await self.chapter_repo.get_by_id(activity.chapter_id)

        result = {
            "id": activity.id,
            "user_id": activity.user_id,
            "book_id": activity.book_id,
            "book_title": book.title if book else None,
            "chapter_id": activity.chapter_id,
            "chapter_title": chapter.title if chapter else None,
            "pages_read": activity.pages_read,
            "minutes_spent": activity.minutes_spent,
            "read_date": activity.read_date,
            "created_at": activity.created_at,
        }

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=3600)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="reading_history", tags=["user_history"])
    async def list_user_reading_history(
        self,
        user_id: int,
        book_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Lấy lịch sử đọc sách của người dùng.

        Args:
            user_id: ID người dùng
            book_id: Lọc theo ID sách (tùy chọn)
            start_date: Lọc từ ngày (tùy chọn)
            end_date: Lọc đến ngày (tùy chọn)
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách hoạt động đọc sách và thông tin phân trang

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Tạo cache key
        filters = {
            "book_id": book_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }

        cache_key = CacheKeyBuilder.build_key(
            "user_reading_history", user_id, skip, limit, str(filters)
        )

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy lịch sử đọc sách
        activities = await self.reading_history_repo.list_by_user(
            user_id=user_id,
            book_id=book_id,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )

        total = await self.reading_history_repo.count_by_user(
            user_id=user_id, book_id=book_id, start_date=start_date, end_date=end_date
        )

        # Thu thập thông tin sách và chương
        book_ids = set(activity.book_id for activity in activities)
        chapter_ids = set(
            activity.chapter_id for activity in activities if activity.chapter_id
        )

        books = {
            book.id: book for book in await self.book_repo.get_by_ids(list(book_ids))
        }

        chapters = {
            chapter.id: chapter
            for chapter in await self.chapter_repo.get_by_ids(list(chapter_ids))
        }

        items = []
        for activity in activities:
            book = books.get(activity.book_id)
            chapter = chapters.get(activity.chapter_id) if activity.chapter_id else None

            items.append(
                {
                    "id": activity.id,
                    "book_id": activity.book_id,
                    "book_title": book.title if book else None,
                    "book_cover": book.cover_image if book else None,
                    "chapter_id": activity.chapter_id,
                    "chapter_title": chapter.title if chapter else None,
                    "pages_read": activity.pages_read,
                    "minutes_spent": activity.minutes_spent,
                    "read_date": activity.read_date,
                    "created_at": activity.created_at,
                }
            )

        result = {"items": items, "total": total, "skip": skip, "limit": limit}

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=1800)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="reading_history", tags=["reading_stats"])
    async def get_reading_stats(
        self,
        user_id: int,
        period: str = "all",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Lấy thống kê đọc sách của người dùng.

        Args:
            user_id: ID người dùng
            period: Thời kỳ thống kê (day, week, month, year, all, custom)
            start_date: Ngày bắt đầu tùy chỉnh (chỉ áp dụng nếu period='custom')
            end_date: Ngày kết thúc tùy chỉnh (chỉ áp dụng nếu period='custom')

        Returns:
            Thống kê đọc sách

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Tính toán thời gian dựa trên period
        today = datetime.now().date()

        if period == "day":
            start_date = today
            end_date = today
        elif period == "week":
            # Lấy ngày đầu tuần (thứ Hai)
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == "month":
            # Lấy ngày đầu tháng
            start_date = date(today.year, today.month, 1)
            end_date = today
        elif period == "year":
            # Lấy ngày đầu năm
            start_date = date(today.year, 1, 1)
            end_date = today
        elif period == "custom":
            if not start_date or not end_date:
                raise BadRequestException(
                    "start_date và end_date là bắt buộc đối với period='custom'"
                )

            if end_date < start_date:
                raise BadRequestException("end_date phải sau start_date")
        elif period != "all":
            valid_periods = ["day", "week", "month", "year", "all", "custom"]
            raise BadRequestException(
                f"Thời kỳ không hợp lệ. Hỗ trợ: {', '.join(valid_periods)}"
            )

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key(
            "reading_stats",
            user_id,
            period,
            start_date.isoformat() if start_date else None,
            end_date.isoformat() if end_date else None,
        )

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Lấy thống kê đọc sách
        stats = await self.reading_history_repo.get_user_stats(
            user_id=user_id, start_date=start_date, end_date=end_date
        )

        # Lấy danh sách sách đã đọc
        books_read = await self.reading_history_repo.get_books_read(
            user_id=user_id, start_date=start_date, end_date=end_date
        )

        # Số ngày đọc sách
        reading_days = await self.reading_history_repo.get_reading_days_count(
            user_id=user_id, start_date=start_date, end_date=end_date
        )

        # Tổng số trang đã đọc
        total_pages = stats.get("total_pages", 0) or 0

        # Tổng số phút đã đọc
        total_minutes = stats.get("total_minutes", 0) or 0

        # Chuyển đổi phút thành giờ:phút
        hours = total_minutes // 60
        minutes = total_minutes % 60

        # Lấy thông tin streak
        current_streak = await self.get_current_streak(user_id)
        longest_streak = await self.get_longest_streak(user_id)

        result = {
            "total_books": len(books_read),
            "total_pages": total_pages,
            "total_reading_time": {
                "minutes": total_minutes,
                "formatted": f"{hours}h {minutes}m",
            },
            "reading_days": reading_days,
            "streak": current_streak,
            "longest_streak": longest_streak,
            "books": books_read,
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
        }

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=3600)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="reading_history", tags=["streak"])
    async def get_current_streak(self, user_id: int) -> int:
        """Lấy số ngày liên tục đọc sách hiện tại của người dùng.

        Args:
            user_id: ID người dùng

        Returns:
            Số ngày liên tục đọc sách
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("current_streak", user_id)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Lấy danh sách các ngày đọc sách, sắp xếp giảm dần
        today = datetime.now().date()
        read_dates = await self.reading_history_repo.get_read_dates(user_id)

        # Kiểm tra xem người dùng có đọc hôm nay không
        if not read_dates or read_dates[0] != today:
            # Nếu hôm nay chưa đọc, kiểm tra hôm qua
            yesterday = today - timedelta(days=1)
            if not read_dates or read_dates[0] != yesterday:
                streak = 0
                await self.cache.set(cache_key, streak, ttl=3600)
                return streak

        # Tính streak
        streak = 1
        last_date = read_dates[0]

        for i in range(1, len(read_dates)):
            expected_date = last_date - timedelta(days=1)
            if read_dates[i] == expected_date:
                streak += 1
                last_date = read_dates[i]
            else:
                break

        # Lưu cache
        await self.cache.set(cache_key, streak, ttl=3600)

        return streak

    @CodeProfiler.profile_time()
    @cached(ttl=86400, namespace="reading_history", tags=["streak"])
    async def get_longest_streak(self, user_id: int) -> int:
        """Lấy số ngày liên tục đọc sách dài nhất của người dùng.

        Args:
            user_id: ID người dùng

        Returns:
            Số ngày liên tục đọc sách dài nhất
        """
        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("longest_streak", user_id)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        # Lấy danh sách các ngày đọc sách, sắp xếp tăng dần
        read_dates = sorted(await self.reading_history_repo.get_read_dates(user_id))

        if not read_dates:
            await self.cache.set(cache_key, 0, ttl=86400)
            return 0

        # Tính streak dài nhất
        longest_streak = 1
        current_streak = 1
        last_date = read_dates[0]

        for i in range(1, len(read_dates)):
            expected_date = last_date + timedelta(days=1)
            if read_dates[i] == expected_date:
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            elif read_dates[i] > expected_date:
                current_streak = 1
            last_date = read_dates[i]

        # Lưu cache
        await self.cache.set(cache_key, longest_streak, ttl=86400)

        return longest_streak

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="reading_history",
        tags=["user_history", "book_history", "reading_stats", "streak"],
    )
    async def mark_book_as_finished(
        self, user_id: int, book_id: int, completion_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Đánh dấu sách đã đọc xong.

        Args:
            user_id: ID người dùng
            book_id: ID sách
            completion_date: Ngày hoàn thành (mặc định là ngày hiện tại)

        Returns:
            Thông tin hoạt động đọc sách đã ghi lại

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc sách
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách với ID {book_id}")

        # Nếu không cung cấp ngày hoàn thành, sử dụng ngày hiện tại
        if not completion_date:
            completion_date = datetime.now().date()

        # Tạo bản ghi hoạt động đánh dấu sách đã đọc xong
        pages_count = book.page_count or 0

        activity_data = {
            "user_id": user_id,
            "book_id": book_id,
            "is_finished": True,
            "pages_read": pages_count,
            "read_date": completion_date,
            "created_at": datetime.now(),
        }

        activity = await self.reading_history_repo.create(activity_data)

        # Cập nhật tiến độ mục tiêu đọc sách
        try:
            # Đánh dấu đã đọc xong 1 cuốn sách
            goal_result = await self.reading_goal_service.track_book_completion(
                user_id, book_id
            )

            # Nếu có số trang, cũng cập nhật mục tiêu số trang
            if pages_count > 0:
                await self.reading_goal_service.track_pages_read(user_id, pages_count)
        except Exception as e:
            # Ghi log lỗi nhưng không fail request
            print(f"Lỗi cập nhật tiến độ mục tiêu: {str(e)}")

        # Ghi log
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="FINISH_BOOK",
            resource_type="book",
            resource_id=str(book_id),
            metadata={
                "book_title": book.title,
                "pages_count": pages_count,
                "completion_date": completion_date.isoformat(),
            },
        )

        # Metrics
        self.metrics.track_user_activity("finish_book", "registered")
        if pages_count > 0:
            self.metrics.track_reading_pages(pages_count)

        return {
            "id": activity.id,
            "user_id": activity.user_id,
            "book_id": activity.book_id,
            "book_title": book.title,
            "is_finished": True,
            "completion_date": completion_date,
            "created_at": activity.created_at,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=7200, namespace="reading_history", tags=["reading_calendar"])
    async def get_reading_calendar(
        self, user_id: int, year: int, month: Optional[int] = None
    ) -> Dict[str, Any]:
        """Lấy lịch đọc sách theo tháng/năm.

        Args:
            user_id: ID người dùng
            year: Năm
            month: Tháng (tùy chọn, nếu không cung cấp sẽ trả về dữ liệu cả năm)

        Returns:
            Dữ liệu lịch đọc sách

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra dữ liệu đầu vào
        if year < 2000 or year > 2100:
            raise BadRequestException("Năm không hợp lệ")

        if month and (month < 1 or month > 12):
            raise BadRequestException("Tháng không hợp lệ")

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("reading_calendar", user_id, year, month)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Thiết lập khoảng thời gian
        if month:
            # Nếu cung cấp tháng, lấy dữ liệu cho tháng đó
            start_date = date(year, month, 1)
            # Tính ngày cuối tháng
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
        else:
            # Nếu không cung cấp tháng, lấy dữ liệu cho cả năm
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)

        # Lấy dữ liệu đọc sách theo ngày
        daily_stats = await self.reading_history_repo.get_daily_stats(
            user_id=user_id, start_date=start_date, end_date=end_date
        )

        # Định dạng kết quả
        result = {"user_id": user_id, "year": year, "month": month, "days": []}

        # Tạo dữ liệu cho từng ngày
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.isoformat()
            day_stats = daily_stats.get(date_str, {})

            result["days"].append(
                {
                    "date": date_str,
                    "pages_read": day_stats.get("pages_read", 0),
                    "minutes_spent": day_stats.get("minutes_spent", 0),
                    "books_count": day_stats.get("books_count", 0),
                    "has_activity": bool(day_stats),
                }
            )

            current_date += timedelta(days=1)

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=7200)

        return result

    @CodeProfiler.profile_time()
    @cached(ttl=7200, namespace="reading_history", tags=["monthly_stats"])
    async def get_monthly_stats(self, user_id: int, year: int) -> Dict[str, Any]:
        """Lấy thống kê đọc sách theo tháng trong năm.

        Args:
            user_id: ID người dùng
            year: Năm

        Returns:
            Thống kê đọc sách theo tháng

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra dữ liệu đầu vào
        if year < 2000 or year > 2100:
            raise BadRequestException("Năm không hợp lệ")

        # Tạo cache key
        cache_key = CacheKeyBuilder.build_key("monthly_stats", user_id, year)

        # Kiểm tra cache
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            return cached_data

        # Thiết lập khoảng thời gian
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

        # Lấy thống kê theo tháng
        monthly_stats = await self.reading_history_repo.get_monthly_stats(
            user_id=user_id, year=year
        )

        # Định dạng kết quả
        result = {"user_id": user_id, "year": year, "months": []}

        # Tạo dữ liệu cho từng tháng
        for month in range(1, 13):
            month_stats = monthly_stats.get(month, {})

            result["months"].append(
                {
                    "month": month,
                    "pages_read": month_stats.get("pages_read", 0),
                    "minutes_spent": month_stats.get("minutes_spent", 0),
                    "books_count": month_stats.get("books_count", 0),
                    "reading_days": month_stats.get("reading_days", 0),
                }
            )

        # Tính tổng của cả năm
        total_pages = sum(month["pages_read"] for month in result["months"])
        total_minutes = sum(month["minutes_spent"] for month in result["months"])
        total_books = sum(month["books_count"] for month in result["months"])
        total_reading_days = sum(month["reading_days"] for month in result["months"])

        result["totals"] = {
            "pages_read": total_pages,
            "minutes_spent": total_minutes,
            "hours_spent": total_minutes // 60,
            "books_count": total_books,
            "reading_days": total_reading_days,
        }

        # Lưu cache
        await self.cache.set(cache_key, result, ttl=7200)

        return result
