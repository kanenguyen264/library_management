from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc, cast, Date
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
import random  # Tạm thời dùng để tạo dữ liệu mẫu

# Thử import User, Book, etc.
try:
    from app.user_site.models import User, Book, ReadingSession, Review

    # Tạm thời comment Order vì có thể chưa tồn tại
    # from app.user_site.models import Order
except ImportError as e:
    # Fallback: tạo class giả tạm thời
    from sqlalchemy.ext.declarative import declarative_base

    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = None
        created_at = None
        is_active = None
        age_group = None
        gender = None

    class Book(Base):
        __tablename__ = "books"
        id = None
        title = None
        created_at = None
        category = None

    class ReadingSession(Base):
        __tablename__ = "reading_sessions"
        id = None
        book_id = None
        created_at = None
        start_time = None

    class Review(Base):
        __tablename__ = "reviews"
        id = None
        book_id = None
        rating = None
        created_at = None

    # Mock Order class tạm thời
    class Order(Base):
        __tablename__ = "orders"
        id = None
        user_id = None
        total_amount = None
        created_at = None
        status = None


from app.logging.setup import get_logger

logger = get_logger(__name__)


class ReportRepository:
    """
    Repository để tạo và lấy báo cáo từ cơ sở dữ liệu.
    """

    @staticmethod
    def get_user_report_data(
        db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """
        Lấy dữ liệu báo cáo về người dùng.

        Args:
            db: Database session
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc

        Returns:
            Dictionary chứa dữ liệu báo cáo người dùng
        """
        try:
            # Tổng số người dùng
            total_users = db.query(func.count(User.id)).scalar()

            # Số người dùng mới trong khoảng thời gian
            new_users = (
                db.query(func.count(User.id))
                .filter(User.created_at.between(start_date, end_date))
                .scalar()
            )

            # Người dùng kích hoạt
            active_users = (
                db.query(func.count(User.id)).filter(User.is_active == True).scalar()
            )

            # Người dùng theo thời gian
            users_by_date = (
                db.query(
                    cast(User.created_at, Date).label("date"),
                    func.count(User.id).label("count"),
                )
                .filter(User.created_at.between(start_date, end_date))
                .group_by("date")
                .order_by("date")
                .all()
            )

            # Biến đổi kết quả thành định dạng phù hợp
            users_by_date_list = [
                {"date": str(data[0]), "count": data[1]} for data in users_by_date
            ]

            # Phân bố người dùng theo nhóm tuổi
            age_distribution = (
                db.query(User.age_group, func.count(User.id).label("count"))
                .group_by(User.age_group)
                .order_by(User.age_group)
                .all()
            )

            age_distribution_list = [
                {"age_group": data[0], "count": data[1]} for data in age_distribution
            ]

            # Phân bố theo giới tính
            gender_distribution = (
                db.query(User.gender, func.count(User.id).label("count"))
                .group_by(User.gender)
                .all()
            )

            gender_distribution_list = [
                {"gender": data[0], "count": data[1]} for data in gender_distribution
            ]

            return {
                "total_users": total_users,
                "new_users": new_users,
                "active_users": active_users,
                "users_by_date": users_by_date_list,
                "age_distribution": age_distribution_list,
                "gender_distribution": gender_distribution_list,
            }
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu báo cáo người dùng: {str(e)}")
            raise e

    @staticmethod
    def get_content_report_data(
        db: Session,
        start_date: date,
        end_date: date,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Lấy dữ liệu báo cáo về nội dung.

        Args:
            db: Database session
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            content_type: Loại nội dung

        Returns:
            Dictionary chứa dữ liệu báo cáo nội dung
        """
        try:
            # Tổng số sách
            total_books = db.query(func.count(Book.id)).scalar()

            # Sách mới trong khoảng thời gian
            new_books = (
                db.query(func.count(Book.id))
                .filter(Book.created_at.between(start_date, end_date))
                .scalar()
            )

            # Sách theo thể loại
            books_by_category = (
                db.query(Book.category, func.count(Book.id).label("count"))
                .group_by(Book.category)
                .order_by(desc("count"))
                .limit(10)
                .all()
            )

            books_by_category_list = [
                {"category": data[0], "count": data[1]} for data in books_by_category
            ]

            # Sách phổ biến (dựa trên số lượt đọc)
            popular_books = (
                db.query(
                    Book.id,
                    Book.title,
                    func.count(ReadingSession.id).label("read_count"),
                )
                .join(ReadingSession, Book.id == ReadingSession.book_id)
                .filter(ReadingSession.created_at.between(start_date, end_date))
                .group_by(Book.id, Book.title)
                .order_by(desc("read_count"))
                .limit(10)
                .all()
            )

            popular_books_list = [
                {"id": data[0], "title": data[1], "read_count": data[2]}
                for data in popular_books
            ]

            # Sách được đánh giá cao
            top_rated_books = (
                db.query(
                    Book.id,
                    Book.title,
                    func.avg(Review.rating).label("avg_rating"),
                    func.count(Review.id).label("review_count"),
                )
                .join(Review, Book.id == Review.book_id)
                .filter(Review.created_at.between(start_date, end_date))
                .group_by(Book.id, Book.title)
                .having(func.count(Review.id) > 5)  # Ít nhất 5 đánh giá
                .order_by(desc("avg_rating"))
                .limit(10)
                .all()
            )

            top_rated_books_list = [
                {
                    "id": data[0],
                    "title": data[1],
                    "avg_rating": float(data[2]),
                    "review_count": data[3],
                }
                for data in top_rated_books
            ]

            return {
                "total_books": total_books,
                "new_books": new_books,
                "books_by_category": books_by_category_list,
                "popular_books": popular_books_list,
                "top_rated_books": top_rated_books_list,
            }
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu báo cáo nội dung: {str(e)}")
            raise e

    @staticmethod
    def get_financial_report_data(
        db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """
        Lấy dữ liệu báo cáo tài chính.

        Args:
            db: Database session
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc

        Returns:
            Dictionary chứa dữ liệu báo cáo tài chính
        """
        try:
            # Tổng doanh thu trong khoảng thời gian
            total_revenue = (
                db.query(func.sum(Order.total_amount))
                .filter(
                    Order.status == "completed",
                    Order.completed_at.between(start_date, end_date),
                )
                .scalar()
                or 0
            )

            # Doanh thu theo ngày
            revenue_by_date = (
                db.query(
                    cast(Order.completed_at, Date).label("date"),
                    func.sum(Order.total_amount).label("revenue"),
                )
                .filter(
                    Order.status == "completed",
                    Order.completed_at.between(start_date, end_date),
                )
                .group_by("date")
                .order_by("date")
                .all()
            )

            revenue_by_date_list = [
                {"date": str(data[0]), "revenue": float(data[1])}
                for data in revenue_by_date
            ]

            # Doanh thu theo loại sản phẩm
            revenue_by_product_type = (
                db.query(
                    Order.product_type, func.sum(Order.total_amount).label("revenue")
                )
                .filter(
                    Order.status == "completed",
                    Order.completed_at.between(start_date, end_date),
                )
                .group_by(Order.product_type)
                .order_by(desc("revenue"))
                .all()
            )

            revenue_by_product_type_list = [
                {"product_type": data[0], "revenue": float(data[1])}
                for data in revenue_by_product_type
            ]

            # Thống kê đơn hàng
            order_stats = {
                "total_orders": (
                    db.query(func.count(Order.id))
                    .filter(Order.created_at.between(start_date, end_date))
                    .scalar()
                    or 0
                ),
                "completed_orders": (
                    db.query(func.count(Order.id))
                    .filter(
                        Order.status == "completed",
                        Order.completed_at.between(start_date, end_date),
                    )
                    .scalar()
                    or 0
                ),
                "cancelled_orders": (
                    db.query(func.count(Order.id))
                    .filter(
                        Order.status == "cancelled",
                        Order.updated_at.between(start_date, end_date),
                    )
                    .scalar()
                    or 0
                ),
                "average_order_value": (
                    db.query(func.avg(Order.total_amount))
                    .filter(
                        Order.status == "completed",
                        Order.completed_at.between(start_date, end_date),
                    )
                    .scalar()
                    or 0
                ),
            }

            return {
                "total_revenue": float(total_revenue),
                "revenue_by_date": revenue_by_date_list,
                "revenue_by_product_type": revenue_by_product_type_list,
                "order_stats": order_stats,
            }
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu báo cáo tài chính: {str(e)}")
            raise e

    @staticmethod
    def get_system_report_data(
        db: Session, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        """
        Lấy dữ liệu báo cáo hệ thống.

        Args:
            db: Database session
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc

        Returns:
            Dictionary chứa dữ liệu báo cáo hệ thống
        """
        try:
            from app.admin_site.models import SystemMetric, SystemHealth

            # Hiệu suất hệ thống
            performance_metrics = (
                db.query(
                    SystemMetric.metric_type,
                    func.avg(SystemMetric.value).label("average"),
                    func.min(SystemMetric.value).label("minimum"),
                    func.max(SystemMetric.value).label("maximum"),
                    func.count(SystemMetric.id).label("data_points"),
                )
                .filter(
                    SystemMetric.created_at.between(start_date, end_date),
                    SystemMetric.metric_type.in_(
                        ["cpu_usage", "memory_usage", "disk_usage", "response_time"]
                    ),
                )
                .group_by(SystemMetric.metric_type)
                .all()
            )

            performance_metrics_list = [
                {
                    "metric_type": data[0],
                    "average": float(data[1]),
                    "minimum": float(data[2]),
                    "maximum": float(data[3]),
                    "data_points": data[4],
                }
                for data in performance_metrics
            ]

            # Trạng thái các thành phần hệ thống
            system_status = (
                db.query(
                    SystemHealth.component,
                    SystemHealth.status,
                    func.max(SystemHealth.created_at).label("last_update"),
                )
                .group_by(SystemHealth.component, SystemHealth.status)
                .order_by(SystemHealth.component)
                .all()
            )

            system_status_list = [
                {
                    "component": data[0],
                    "status": data[1],
                    "last_update": data[2].isoformat(),
                }
                for data in system_status
            ]

            # Hoạt động người dùng
            user_activity = {
                "total_sessions": (
                    db.query(func.count(ReadingSession.id))
                    .filter(ReadingSession.created_at.between(start_date, end_date))
                    .scalar()
                    or 0
                ),
                "total_reading_time": (
                    db.query(func.sum(ReadingSession.duration))
                    .filter(ReadingSession.created_at.between(start_date, end_date))
                    .scalar()
                    or 0
                ),
                "average_session_duration": (
                    db.query(func.avg(ReadingSession.duration))
                    .filter(ReadingSession.created_at.between(start_date, end_date))
                    .scalar()
                    or 0
                ),
                "total_reviews": (
                    db.query(func.count(Review.id))
                    .filter(Review.created_at.between(start_date, end_date))
                    .scalar()
                    or 0
                ),
            }

            return {
                "performance_metrics": performance_metrics_list,
                "system_status": system_status_list,
                "user_activity": user_activity,
            }
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu báo cáo hệ thống: {str(e)}")
            raise e
