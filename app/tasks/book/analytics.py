"""
Tác vụ phân tích dữ liệu sách

Module này cung cấp các tác vụ phân tích dữ liệu sách:
- Phân tích xu hướng đọc của người dùng
- Tạo báo cáo đọc
- Theo dõi hành vi đọc của người dùng
"""

import datetime
import time
import os
import json
import asyncio
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy import func, select, and_, desc, text

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.tasks.worker import celery_app
from app.tasks.base_task import BaseTask
from app.tasks.scheduler import scheduled_task, ScheduleType
from app.db.session import async_session, get_db, engine

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.analytics.analyze_reading_trends",
    queue="books",
    max_retries=3,
    # Cache để tránh phân tích lại
    cache_result=True,
    cache_ttl=86400,  # 1 ngày
)
def analyze_reading_trends(
    self, time_period: str = "week", limit: int = 20
) -> Dict[str, Any]:
    """
    Phân tích xu hướng đọc và tạo thống kê.

    Args:
        time_period: Thời gian phân tích (day, week, month, year)
        limit: Số lượng kết quả trả về

    Returns:
        Dict chứa các xu hướng và thống kê
    """
    from app.user_site.models.book_view import BookView
    from app.user_site.models.book import Book
    from app.user_site.models.user_reading_progress import UserReadingProgress
    from app.user_site.models.category import Category

    try:
        logger.info(f"Analyzing reading trends for {time_period}")

        # Tính thời gian bắt đầu phân tích
        now = datetime.datetime.now()
        if time_period == "day":
            start_date = now - datetime.timedelta(days=1)
        elif time_period == "week":
            start_date = now - datetime.timedelta(weeks=1)
        elif time_period == "month":
            start_date = now - datetime.timedelta(days=30)
        else:  # year
            start_date = now - datetime.timedelta(days=365)

        # Sử dụng database trực tiếp
        with engine.connect() as connection:
            # 1. Sách được xem nhiều nhất
            most_viewed_query = text(
                """
                SELECT b.id, b.title, b.author_id, COUNT(bv.id) as view_count
                FROM books b
                JOIN book_views bv ON b.id = bv.book_id
                WHERE bv.viewed_at >= :start_date
                GROUP BY b.id, b.title, b.author_id
                ORDER BY view_count DESC
                LIMIT :limit
            """
            )

            most_viewed_result = connection.execute(
                most_viewed_query, {"start_date": start_date, "limit": limit}
            )
            most_viewed_books = [dict(row) for row in most_viewed_result]

            # 2. Danh mục phổ biến
            popular_categories_query = text(
                """
                SELECT c.id, c.name, COUNT(bv.id) as view_count
                FROM categories c
                JOIN book_categories bc ON c.id = bc.category_id
                JOIN book_views bv ON bc.book_id = bv.book_id
                WHERE bv.viewed_at >= :start_date
                GROUP BY c.id, c.name
                ORDER BY view_count DESC
                LIMIT :limit
            """
            )

            categories_result = connection.execute(
                popular_categories_query, {"start_date": start_date, "limit": limit}
            )
            popular_categories = [dict(row) for row in categories_result]

            # 3. Tỷ lệ đọc hoàn thành
            completion_rate_query = text(
                """
                SELECT 
                    COUNT(CASE WHEN progress >= 95 THEN 1 END) as completed,
                    COUNT(*) as total,
                    CASE 
                        WHEN COUNT(*) > 0 THEN 
                            (COUNT(CASE WHEN progress >= 95 THEN 1 END) * 100.0 / COUNT(*))
                        ELSE 0
                    END as completion_rate
                FROM user_reading_progress
                WHERE updated_at >= :start_date
            """
            )

            completion_result = connection.execute(
                completion_rate_query, {"start_date": start_date}
            )
            completion_rate = dict(completion_result.fetchone())

            # 4. Thời gian đọc trung bình
            avg_reading_time_query = text(
                """
                SELECT AVG(reading_time_seconds) as avg_reading_time
                FROM user_reading_sessions
                WHERE session_end >= :start_date
            """
            )

            reading_time_result = connection.execute(
                avg_reading_time_query, {"start_date": start_date}
            )
            avg_reading_time = dict(reading_time_result.fetchone())

        # Tổng hợp kết quả
        results = {
            "time_period": time_period,
            "start_date": start_date.isoformat(),
            "end_date": now.isoformat(),
            "most_viewed_books": most_viewed_books,
            "popular_categories": popular_categories,
            "completion_rate": completion_rate,
            "avg_reading_time": avg_reading_time,
            "analysis_timestamp": now.isoformat(),
        }

        logger.info("Reading trends analysis completed successfully")
        return results

    except Exception as e:
        logger.error(f"Error analyzing reading trends: {str(e)}")
        self.retry(exc=e, countdown=60)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.analytics.generate_reading_report",
    queue="books",
)
def generate_reading_report(
    self, user_id: int, time_period: str = "month"
) -> Dict[str, Any]:
    """
    Tạo báo cáo chi tiết về hoạt động đọc sách cho người dùng.

    Args:
        user_id: ID của người dùng
        time_period: Thời gian báo cáo (week, month, year)

    Returns:
        Dict chứa báo cáo đọc sách
    """
    from app.user_site.models.user_reading_progress import UserReadingProgress
    from app.user_site.models.user_reading_session import UserReadingSession
    from app.user_site.models.book import Book

    try:
        logger.info(
            f"Generating reading report for user {user_id}, period: {time_period}"
        )

        # Tính thời gian bắt đầu báo cáo
        now = datetime.datetime.now()
        if time_period == "week":
            start_date = now - datetime.timedelta(weeks=1)
        elif time_period == "month":
            start_date = now - datetime.timedelta(days=30)
        else:  # year
            start_date = now - datetime.timedelta(days=365)

        # Sử dụng database để lấy dữ liệu
        with engine.connect() as connection:
            # 1. Sách đã đọc
            books_read_query = text(
                """
                SELECT 
                    b.id, b.title, 
                    urp.progress,
                    urp.updated_at,
                    SUM(urs.reading_time_seconds) as total_reading_time
                FROM books b
                JOIN user_reading_progress urp ON b.id = urp.book_id
                LEFT JOIN user_reading_sessions urs ON b.id = urs.book_id AND urs.user_id = urp.user_id
                WHERE urp.user_id = :user_id AND urp.updated_at >= :start_date
                GROUP BY b.id, b.title, urp.progress, urp.updated_at
                ORDER BY urp.updated_at DESC
            """
            )

            books_result = connection.execute(
                books_read_query, {"user_id": user_id, "start_date": start_date}
            )
            books_read = [dict(row) for row in books_result]

            # 2. Tổng thời gian đọc
            reading_time_query = text(
                """
                SELECT 
                    SUM(reading_time_seconds) as total_seconds,
                    COUNT(DISTINCT book_id) as books_count,
                    COUNT(*) as sessions_count
                FROM user_reading_sessions
                WHERE user_id = :user_id AND session_end >= :start_date
            """
            )

            reading_time_result = connection.execute(
                reading_time_query, {"user_id": user_id, "start_date": start_date}
            )
            reading_time = dict(reading_time_result.fetchone())

            # 3. Số trang đã đọc
            pages_read_query = text(
                """
                SELECT 
                    SUM(b.pages * (urp.progress / 100.0)) as estimated_pages_read
                FROM user_reading_progress urp
                JOIN books b ON urp.book_id = b.id
                WHERE urp.user_id = :user_id AND urp.updated_at >= :start_date
            """
            )

            pages_result = connection.execute(
                pages_read_query, {"user_id": user_id, "start_date": start_date}
            )
            pages_read = dict(pages_result.fetchone())

            # 4. Danh mục đọc nhiều nhất
            categories_query = text(
                """
                SELECT 
                    c.id, c.name, COUNT(urp.id) as read_count
                FROM categories c
                JOIN book_categories bc ON c.id = bc.category_id
                JOIN user_reading_progress urp ON bc.book_id = urp.book_id
                WHERE urp.user_id = :user_id AND urp.updated_at >= :start_date
                GROUP BY c.id, c.name
                ORDER BY read_count DESC
                LIMIT 5
            """
            )

            categories_result = connection.execute(
                categories_query, {"user_id": user_id, "start_date": start_date}
            )
            favorite_categories = [dict(row) for row in categories_result]

            # 5. Thời gian đọc theo ngày
            reading_time_by_day_query = text(
                """
                SELECT 
                    DATE(session_start) as reading_date,
                    SUM(reading_time_seconds) as total_seconds
                FROM user_reading_sessions
                WHERE user_id = :user_id AND session_end >= :start_date
                GROUP BY DATE(session_start)
                ORDER BY reading_date ASC
            """
            )

            reading_by_day_result = connection.execute(
                reading_time_by_day_query,
                {"user_id": user_id, "start_date": start_date},
            )
            reading_by_day = [dict(row) for row in reading_by_day_result]

        # Tổng hợp kết quả
        report = {
            "user_id": user_id,
            "time_period": time_period,
            "start_date": start_date.isoformat(),
            "end_date": now.isoformat(),
            "books_read": books_read,
            "reading_time": reading_time,
            "pages_read": pages_read,
            "favorite_categories": favorite_categories,
            "reading_by_day": reading_by_day,
            "generated_at": now.isoformat(),
        }

        logger.info(f"Reading report generated for user {user_id}")
        return report

    except Exception as e:
        logger.error(f"Error generating reading report for user {user_id}: {str(e)}")
        self.retry(exc=e, countdown=30)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.analytics.track_user_reading_patterns",
    queue="books",
)
def track_user_reading_patterns(
    self, user_id: int, book_id: int, session_data: Dict[str, Any]
) -> bool:
    """
    Lưu trữ và phân tích dữ liệu đọc sách của người dùng.

    Args:
        user_id: ID của người dùng
        book_id: ID của sách
        session_data: Dữ liệu phiên đọc sách

    Returns:
        True nếu thành công
    """
    from app.user_site.models.user_reading_session import UserReadingSession
    from app.user_site.models.user_reading_progress import UserReadingProgress

    try:
        logger.info(f"Tracking reading patterns for user {user_id}, book {book_id}")

        # Cập nhật session đọc sách
        async def update_reading_session():
            async with async_session() as session:
                # Tạo session đọc mới
                reading_session = UserReadingSession(
                    user_id=user_id,
                    book_id=book_id,
                    session_start=session_data.get("start_time"),
                    session_end=session_data.get("end_time"),
                    reading_time_seconds=session_data.get("duration"),
                    pages_read=session_data.get("pages_read", 0),
                    start_position=session_data.get("start_position", 0),
                    end_position=session_data.get("end_position", 0),
                    device_info=session_data.get("device_info", {}),
                )

                session.add(reading_session)

                # Cập nhật tiến độ đọc
                progress = session_data.get("progress")
                if progress is not None:
                    # Lấy progress hiện tại
                    stmt = select(UserReadingProgress).where(
                        and_(
                            UserReadingProgress.user_id == user_id,
                            UserReadingProgress.book_id == book_id,
                        )
                    )
                    result = await session.execute(stmt)
                    reading_progress = result.scalars().first()

                    if reading_progress:
                        # Cập nhật nếu tiến độ mới cao hơn
                        if progress > reading_progress.progress:
                            reading_progress.progress = progress
                            reading_progress.updated_at = datetime.datetime.now()
                            session.add(reading_progress)
                    else:
                        # Tạo mới nếu chưa có
                        reading_progress = UserReadingProgress(
                            user_id=user_id,
                            book_id=book_id,
                            progress=progress,
                            updated_at=datetime.datetime.now(),
                        )
                        session.add(reading_progress)

                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(update_reading_session())

        logger.info(
            f"Reading patterns tracked successfully for user {user_id}, book {book_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error tracking reading patterns: {str(e)}")
        self.retry(exc=e, countdown=30)
        return False
