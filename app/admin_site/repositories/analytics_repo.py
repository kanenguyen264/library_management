from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc, cast, Date
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
import random

from app.user_site.models import User, Book, ReadingSession, Review


# Tạo class Order giả lập để tránh lỗi import
class Order:
    """Lớp Order giả lập để thay thế model chưa tồn tại"""

    __tablename__ = "orders"
    id = None
    user_id = None
    total_amount = None
    created_at = None
    status = None


from app.logging.setup import get_logger

logger = get_logger(__name__)


class AnalyticsRepository:
    """
    Repository để lấy dữ liệu phân tích từ cơ sở dữ liệu.
    """

    @staticmethod
    def get_user_growth_data(
        db: Session, start_date: date, end_date: date, interval: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Lấy dữ liệu tăng trưởng người dùng.

        Args:
            db: Database session
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            interval: Khoảng thời gian ('day', 'week', 'month')

        Returns:
            Danh sách dữ liệu tăng trưởng người dùng theo thời gian
        """
        try:
            # Xác định trường ngày tháng dựa trên khoảng thời gian
            if interval == "day":
                date_trunc = func.date_trunc("day", User.created_at)
            elif interval == "week":
                date_trunc = func.date_trunc("week", User.created_at)
            elif interval == "month":
                date_trunc = func.date_trunc("month", User.created_at)
            else:
                date_trunc = func.date_trunc("day", User.created_at)

            # Truy vấn người dùng mới theo khoảng thời gian
            new_users_query = (
                db.query(
                    date_trunc.label("date"), func.count(User.id).label("new_users")
                )
                .filter(User.created_at.between(start_date, end_date))
                .group_by("date")
                .order_by("date")
                .all()
            )

            # Chuyển kết quả thành dictionary
            results = []
            cumulative_count = 0

            # Lấy số người dùng trước khi bắt đầu
            initial_users = (
                db.query(func.count(User.id))
                .filter(User.created_at < start_date)
                .scalar()
                or 0
            )
            cumulative_count = initial_users

            # Tạo từng mục trong kết quả
            for date, new_users in new_users_query:
                cumulative_count += new_users
                results.append(
                    {
                        "date": date.isoformat() if date else None,
                        "new_users": new_users,
                        "total_users": cumulative_count,
                    }
                )

            return results
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu tăng trưởng người dùng: {str(e)}")
            raise e

    @staticmethod
    def get_user_demographics(db: Session) -> Dict[str, List[Dict[str, Any]]]:
        """
        Lấy dữ liệu nhân khẩu học người dùng.

        Args:
            db: Database session

        Returns:
            Danh sách dữ liệu nhân khẩu học người dùng
        """
        try:
            # Lấy tổng số người dùng
            total_users = (
                db.query(func.count(User.id)).scalar() or 1
            )  # Tránh chia cho 0

            # Phân bố theo độ tuổi
            age_query = (
                db.query(User.age_group, func.count(User.id).label("count"))
                .group_by(User.age_group)
                .order_by(User.age_group)
                .all()
            )

            age_distribution = [
                {
                    "category": data[0] or "Không xác định",
                    "count": data[1],
                    "percentage": round((data[1] / total_users) * 100, 1),
                }
                for data in age_query
            ]

            # Phân bố theo giới tính
            gender_query = (
                db.query(User.gender, func.count(User.id).label("count"))
                .group_by(User.gender)
                .all()
            )

            gender_distribution = [
                {
                    "category": data[0] or "Không xác định",
                    "count": data[1],
                    "percentage": round((data[1] / total_users) * 100, 1),
                }
                for data in gender_query
            ]

            # Phân bố theo vị trí
            location_query = (
                db.query(User.location, func.count(User.id).label("count"))
                .group_by(User.location)
                .order_by(desc("count"))
                .limit(10)
                .all()
            )

            location_distribution = [
                {
                    "category": data[0] or "Không xác định",
                    "count": data[1],
                    "percentage": round((data[1] / total_users) * 100, 1),
                }
                for data in location_query
            ]

            return {
                "age": age_distribution,
                "gender": gender_distribution,
                "location": location_distribution,
            }
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu nhân khẩu học người dùng: {str(e)}")
            raise e

    @staticmethod
    def get_content_stats(
        db: Session,
        start_date: date,
        end_date: date,
        interval: str = "day",
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lấy thống kê về nội dung.

        Args:
            db: Database session
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            interval: Khoảng thời gian ('day', 'week', 'month')
            content_type: Loại nội dung

        Returns:
            Danh sách thống kê nội dung theo thời gian
        """
        try:
            # Xác định trường ngày tháng dựa trên khoảng thời gian
            if interval == "day":
                date_trunc = func.date_trunc("day", Book.created_at)
            elif interval == "week":
                date_trunc = func.date_trunc("week", Book.created_at)
            elif interval == "month":
                date_trunc = func.date_trunc("month", Book.created_at)
            else:
                date_trunc = func.date_trunc("day", Book.created_at)

            # Truy vấn nội dung mới
            query_new_content = db.query(
                date_trunc.label("date"), func.count(Book.id).label("new_content")
            ).filter(Book.created_at.between(start_date, end_date))

            if content_type:
                query_new_content = query_new_content.filter(Book.type == content_type)

            query_new_content = (
                query_new_content.group_by("date").order_by("date").all()
            )

            # Truy vấn lượt xem
            query_views = db.query(
                date_trunc.label("date"), func.sum(Book.view_count).label("views")
            ).filter(Book.created_at.between(start_date, end_date))

            if content_type:
                query_views = query_views.filter(Book.type == content_type)

            query_views = query_views.group_by("date").order_by("date").all()

            # Truy vấn lượt đọc
            query_reads = (
                db.query(
                    date_trunc.label("date"),
                    func.count(ReadingSession.id).label("reads"),
                )
                .join(Book, ReadingSession.book_id == Book.id)
                .filter(ReadingSession.created_at.between(start_date, end_date))
            )

            if content_type:
                query_reads = query_reads.filter(Book.type == content_type)

            query_reads = query_reads.group_by("date").order_by("date").all()

            # Truy vấn lượt thích
            query_likes = db.query(
                date_trunc.label("date"), func.sum(Book.like_count).label("likes")
            ).filter(Book.created_at.between(start_date, end_date))

            if content_type:
                query_likes = query_likes.filter(Book.type == content_type)

            query_likes = query_likes.group_by("date").order_by("date").all()

            # Truy vấn lượt đánh giá
            query_reviews = (
                db.query(
                    date_trunc.label("date"), func.count(Review.id).label("reviews")
                )
                .join(Book, Review.book_id == Book.id)
                .filter(Review.created_at.between(start_date, end_date))
            )

            if content_type:
                query_reviews = query_reviews.filter(Book.type == content_type)

            query_reviews = query_reviews.group_by("date").order_by("date").all()

            # Tạo từng mục trong kết quả
            results = []

            # Danh sách tất cả các ngày trong khoảng
            all_dates = {}
            current = start_date
            while current <= end_date:
                if interval == "day":
                    date_key = datetime(current.year, current.month, current.day)
                elif interval == "week":
                    # Ngày đầu tuần
                    date_key = datetime(
                        current.year, current.month, current.day
                    ) - timedelta(days=current.weekday())
                elif interval == "month":
                    # Ngày đầu tháng
                    date_key = datetime(current.year, current.month, 1)

                all_dates[date_key] = {
                    "date": date_key.isoformat(),
                    "new_content": 0,
                    "views": 0,
                    "reads": 0,
                    "likes": 0,
                    "reviews": 0,
                }

                # Tăng ngày theo khoảng thời gian
                if interval == "day":
                    current += timedelta(days=1)
                elif interval == "week":
                    current += timedelta(days=7)
                elif interval == "month":
                    if current.month == 12:
                        current = date(current.year + 1, 1, 1)
                    else:
                        current = date(current.year, current.month + 1, 1)

            # Cập nhật dữ liệu từ các truy vấn
            for date, value in query_new_content:
                if date in all_dates:
                    all_dates[date]["new_content"] = value

            for date, value in query_views:
                if date in all_dates:
                    all_dates[date]["views"] = value or 0

            for date, value in query_reads:
                if date in all_dates:
                    all_dates[date]["reads"] = value

            for date, value in query_likes:
                if date in all_dates:
                    all_dates[date]["likes"] = value or 0

            for date, value in query_reviews:
                if date in all_dates:
                    all_dates[date]["reviews"] = value

            # Chuyển từ dictionary sang list
            results = list(all_dates.values())
            results.sort(key=lambda x: x["date"])

            return results
        except Exception as e:
            logger.error(f"Lỗi khi lấy thống kê nội dung: {str(e)}")
            raise e

    @staticmethod
    def get_revenue_stats(
        db: Session, start_date: date, end_date: date, interval: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Lấy thống kê về doanh thu.

        Args:
            db: Database session
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            interval: Khoảng thời gian ('day', 'week', 'month')

        Returns:
            Danh sách thống kê doanh thu theo thời gian
        """
        try:
            # Xác định trường ngày tháng dựa trên khoảng thời gian
            if interval == "day":
                date_trunc = func.date_trunc("day", Order.completed_at)
            elif interval == "week":
                date_trunc = func.date_trunc("week", Order.completed_at)
            elif interval == "month":
                date_trunc = func.date_trunc("month", Order.completed_at)
            else:
                date_trunc = func.date_trunc("day", Order.completed_at)

            # Truy vấn tổng doanh thu
            revenue_query = (
                db.query(
                    date_trunc.label("date"),
                    func.sum(Order.total_amount).label("total_revenue"),
                )
                .filter(
                    Order.status == "completed",
                    Order.completed_at.between(start_date, end_date),
                )
                .group_by("date")
                .order_by("date")
                .all()
            )

            # Truy vấn doanh thu từ đăng ký (subscription)
            subscription_query = (
                db.query(
                    date_trunc.label("date"),
                    func.sum(Order.total_amount).label("subscription_revenue"),
                )
                .filter(
                    Order.status == "completed",
                    Order.product_type == "subscription",
                    Order.completed_at.between(start_date, end_date),
                )
                .group_by("date")
                .order_by("date")
                .all()
            )

            # Truy vấn doanh thu từ mua một lần
            one_time_query = (
                db.query(
                    date_trunc.label("date"),
                    func.sum(Order.total_amount).label("one_time_purchases"),
                )
                .filter(
                    Order.status == "completed",
                    Order.product_type == "one_time",
                    Order.completed_at.between(start_date, end_date),
                )
                .group_by("date")
                .order_by("date")
                .all()
            )

            # Truy vấn số lượng đăng ký mới
            new_subscriptions_query = (
                db.query(
                    date_trunc.label("date"),
                    func.count(Order.id).label("new_subscriptions"),
                )
                .filter(
                    Order.status == "completed",
                    Order.product_type == "subscription",
                    Order.completed_at.between(start_date, end_date),
                )
                .group_by("date")
                .order_by("date")
                .all()
            )

            # Tạo từng mục trong kết quả
            results = []

            # Danh sách tất cả các ngày trong khoảng
            all_dates = {}
            current = start_date
            while current <= end_date:
                if interval == "day":
                    date_key = datetime(current.year, current.month, current.day)
                elif interval == "week":
                    # Ngày đầu tuần
                    date_key = datetime(
                        current.year, current.month, current.day
                    ) - timedelta(days=current.weekday())
                elif interval == "month":
                    # Ngày đầu tháng
                    date_key = datetime(current.year, current.month, 1)

                all_dates[date_key] = {
                    "date": date_key.isoformat(),
                    "total_revenue": 0,
                    "subscription_revenue": 0,
                    "one_time_purchases": 0,
                    "new_subscriptions": 0,
                }

                # Tăng ngày theo khoảng thời gian
                if interval == "day":
                    current += timedelta(days=1)
                elif interval == "week":
                    current += timedelta(days=7)
                elif interval == "month":
                    if current.month == 12:
                        current = date(current.year + 1, 1, 1)
                    else:
                        current = date(current.year, current.month + 1, 1)

            # Cập nhật dữ liệu từ các truy vấn
            for date, value in revenue_query:
                if date in all_dates:
                    all_dates[date]["total_revenue"] = float(value or 0)

            for date, value in subscription_query:
                if date in all_dates:
                    all_dates[date]["subscription_revenue"] = float(value or 0)

            for date, value in one_time_query:
                if date in all_dates:
                    all_dates[date]["one_time_purchases"] = float(value or 0)

            for date, value in new_subscriptions_query:
                if date in all_dates:
                    all_dates[date]["new_subscriptions"] = value

            # Chuyển từ dictionary sang list
            results = list(all_dates.values())
            results.sort(key=lambda x: x["date"])

            return results
        except Exception as e:
            logger.error(f"Lỗi khi lấy thống kê doanh thu: {str(e)}")
            raise e
