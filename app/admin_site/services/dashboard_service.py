from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, date, timedelta
import random  # Tạm thời dùng để tạo dữ liệu mẫu

from app.logging.setup import get_logger
from app.admin_site.repositories.admin_repo import AdminRepository
from app.admin_site.repositories.analytics_repo import AnalyticsRepository
from app.admin_site.repositories.content_approval_repo import ContentApprovalRepository
from app.admin_site.repositories.system_health_repo import SystemHealthRepository
from app.admin_site.repositories.system_metric_repo import SystemMetricRepository
from app.cache.decorators import cached
from app.core.exceptions import ServerException
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.reading_session_repo import ReadingSessionRepository
from app.user_site.repositories.subscription_repo import SubscriptionRepository
from app.user_site.repositories.review_repo import ReviewRepository
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


@cached(ttl=3600, namespace="admin:dashboard", tags=["dashboard"])
def get_dashboard_summary(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thông tin tổng quan cho dashboard.

    Args:
        db: Database session
        start_date: Thời gian bắt đầu (mặc định 30 ngày trước)
        end_date: Thời gian kết thúc (mặc định hiện tại)
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary với thông tin tổng quan
    """
    # Thiết lập thời gian mặc định
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        # Tổng số người dùng
        total_users = UserRepository.count(db)
        new_users = UserRepository.count_new_users(db, start_date, end_date)
        active_users = UserRepository.count_active_users(db, start_date, end_date)

        # Tổng số sách
        total_books = BookRepository.count(db)
        new_books = BookRepository.count_new_books(db, start_date, end_date)

        # Thời gian đọc
        total_reading_time = ReadingSessionRepository.get_total_reading_time(db)
        period_reading_time = ReadingSessionRepository.get_total_reading_time(
            db, start_date, end_date
        )

        # Số lượng đăng ký
        total_subscriptions = SubscriptionRepository.count(db, status="active")
        new_subscriptions = SubscriptionRepository.count_new_subscriptions(
            db, start_date, end_date
        )

        # Số lượng đánh giá
        total_reviews = ReviewRepository.count(db)
        new_reviews = ReviewRepository.count_new_reviews(db, start_date, end_date)

        # Dữ liệu thống kê theo ngày
        daily_new_users = UserRepository.count_by_day(db, start_date, end_date)
        daily_active_users = UserRepository.count_active_by_day(
            db, start_date, end_date
        )
        daily_reading_time = ReadingSessionRepository.get_reading_time_by_day(
            db, start_date, end_date
        )
        daily_new_subscriptions = SubscriptionRepository.count_by_day(
            db, start_date, end_date
        )

        result = {
            "users": {"total": total_users, "new": new_users, "active": active_users},
            "books": {"total": total_books, "new": new_books},
            "reading": {
                "total_time": total_reading_time,
                "period_time": period_reading_time,
            },
            "subscriptions": {"total": total_subscriptions, "new": new_subscriptions},
            "reviews": {"total": total_reviews, "new": new_reviews},
            "daily_stats": {
                "new_users": daily_new_users,
                "active_users": daily_active_users,
                "reading_time": daily_reading_time,
                "new_subscriptions": daily_new_subscriptions,
            },
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days,
            },
        }

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="DASHBOARD_SUMMARY",
                        entity_id=0,
                        description="Viewed dashboard summary",
                        metadata={
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "total_users": total_users,
                            "new_users": new_users,
                            "active_users": active_users,
                            "total_books": total_books,
                            "total_subscriptions": total_subscriptions,
                            "period_days": (end_date - start_date).days,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin tổng quan dashboard: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy thông tin tổng quan dashboard: {str(e)}"
        )


@cached(ttl=600, namespace="admin:dashboard:stats", tags=["dashboard"])
def get_dashboard_stats(
    db: Session, start_date: date, end_date: date
) -> Dict[str, Any]:
    """
    Lấy thống kê cho dashboard.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc

    Returns:
        Dictionary chứa thông tin thống kê
    """
    try:
        # Lấy dữ liệu người dùng
        user_stats = AnalyticsRepository.get_user_growth_data(
            db, start_date, end_date, "day"
        )

        # Lấy dữ liệu nội dung
        content_stats = AnalyticsRepository.get_content_stats(
            db, start_date, end_date, "day"
        )

        # Lấy dữ liệu doanh thu
        revenue_stats = AnalyticsRepository.get_revenue_stats(
            db, start_date, end_date, "day"
        )

        # Lấy dữ liệu tương tác
        engagement_stats = AnalyticsRepository.get_engagement_stats(
            db, start_date, end_date, "day"
        )

        # Lấy dữ liệu hiệu suất hệ thống
        performance_metrics = SystemMetricRepository.get_aggregation(
            db,
            "cpu_usage",
            "day",
            start_time=datetime.combine(start_date, datetime.min.time()),
            end_time=datetime.combine(end_date, datetime.max.time()),
        )

        # Tạo kết quả
        result = {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "users": user_stats,
            "content": content_stats,
            "revenue": revenue_stats,
            "engagement": engagement_stats,
            "performance": performance_metrics,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê dashboard: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê dashboard: {str(e)}")


@cached(
    ttl=300, namespace="admin:dashboard:activities", tags=["dashboard", "activities"]
)
def get_recent_activities(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Lấy hoạt động gần đây.

    Args:
        db: Database session
        limit: Số lượng hoạt động tối đa

    Returns:
        Danh sách hoạt động gần đây
    """
    try:
        # Lấy hoạt động từ các hệ thống khác nhau và kết hợp
        # Lưu ý: Cần phải có bảng hoạt động trong database

        # TODO: Thay thế bằng truy vấn thực tế từ bảng hoạt động
        # Đây là dữ liệu mẫu
        activities = [
            {
                "id": 1,
                "type": "user_registration",
                "user": "newreader123",
                "timestamp": datetime.now() - timedelta(minutes=5),
                "details": "Đăng ký tài khoản mới",
            },
            {
                "id": 2,
                "type": "content_approval",
                "user": "admin.nguyen",
                "timestamp": datetime.now() - timedelta(minutes=12),
                "details": "Phê duyệt truyện 'Đêm trăng mờ'",
            },
            {
                "id": 3,
                "type": "payment",
                "user": "reader456",
                "timestamp": datetime.now() - timedelta(minutes=18),
                "details": "Thanh toán gói Premium",
            },
            {
                "id": 4,
                "type": "content_upload",
                "user": "author789",
                "timestamp": datetime.now() - timedelta(minutes=25),
                "details": "Tải lên chương mới của 'Hành trình về phương Đông'",
            },
            {
                "id": 5,
                "type": "user_login",
                "user": "admin.tran",
                "timestamp": datetime.now() - timedelta(minutes=30),
                "details": "Đăng nhập vào hệ thống admin",
            },
            {
                "id": 6,
                "type": "system_backup",
                "user": "system",
                "timestamp": datetime.now() - timedelta(minutes=42),
                "details": "Sao lưu dữ liệu hàng ngày",
            },
            {
                "id": 7,
                "type": "system_alert",
                "user": "system",
                "timestamp": datetime.now() - timedelta(minutes=57),
                "details": "Cảnh báo: Mức sử dụng CPU cao",
            },
            {
                "id": 8,
                "type": "user_purchase",
                "user": "reader123",
                "timestamp": datetime.now() - timedelta(minutes=63),
                "details": "Mua sách 'Bí mật của não bộ'",
            },
            {
                "id": 9,
                "type": "promotion_created",
                "user": "admin.le",
                "timestamp": datetime.now() - timedelta(minutes=78),
                "details": "Tạo khuyến mãi 'Giảm giá mùa hè'",
            },
            {
                "id": 10,
                "type": "payment_error",
                "user": "user567",
                "timestamp": datetime.now() - timedelta(minutes=92),
                "details": "Lỗi thanh toán: Thẻ hết hạn",
            },
        ]

        return activities[:limit]
    except Exception as e:
        logger.error(f"Lỗi khi lấy hoạt động gần đây: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy hoạt động gần đây: {str(e)}")


@cached(ttl=300, namespace="admin:dashboard:alerts", tags=["dashboard", "alerts"])
def get_alerts_and_notifications(db: Session, admin_id: int) -> Dict[str, Any]:
    """
    Lấy cảnh báo và thông báo cho admin.

    Args:
        db: Database session
        admin_id: ID của admin

    Returns:
        Dictionary chứa cảnh báo và thông báo
    """
    try:
        # TODO: Thay thế bằng truy vấn thực tế từ database
        # Đây là dữ liệu mẫu

        # Lấy thông tin admin để kiểm tra quyền
        admin = AdminRepository.get_by_id(db, admin_id)
        if not admin:
            return {"alerts": [], "notifications": []}

        alerts = [
            {
                "id": 1,
                "severity": "high",
                "type": "system",
                "message": "Mức sử dụng CPU vượt quá 80%",
                "timestamp": datetime.now() - timedelta(minutes=12),
                "is_read": False,
            },
            {
                "id": 2,
                "severity": "medium",
                "type": "content",
                "message": "57 nội dung đang chờ phê duyệt",
                "timestamp": datetime.now() - timedelta(hours=1),
                "is_read": False,
            },
            {
                "id": 3,
                "severity": "low",
                "type": "user",
                "message": "Tăng đột biến đăng ký người dùng mới",
                "timestamp": datetime.now() - timedelta(hours=3),
                "is_read": True,
            },
        ]

        notifications = [
            {
                "id": 1,
                "type": "system",
                "message": "Bản cập nhật hệ thống sẽ diễn ra vào 22:00 hôm nay",
                "timestamp": datetime.now() - timedelta(hours=2),
                "is_read": False,
            },
            {
                "id": 2,
                "type": "task",
                "message": "Bạn được giao nhiệm vụ duyệt nội dung mới",
                "timestamp": datetime.now() - timedelta(hours=4),
                "is_read": True,
            },
            {
                "id": 3,
                "type": "message",
                "message": "Admin Trần gửi tin nhắn cho bạn",
                "timestamp": datetime.now() - timedelta(hours=6),
                "is_read": False,
            },
            {
                "id": 4,
                "type": "report",
                "message": "Báo cáo doanh thu tháng đã được tạo",
                "timestamp": datetime.now() - timedelta(hours=8),
                "is_read": True,
            },
        ]

        # Đếm số thông báo chưa đọc
        unread_alerts = sum(1 for alert in alerts if not alert["is_read"])
        unread_notifications = sum(
            1 for notification in notifications if not notification["is_read"]
        )

        return {
            "alerts": alerts,
            "notifications": notifications,
            "unread_count": {
                "alerts": unread_alerts,
                "notifications": unread_notifications,
                "total": unread_alerts + unread_notifications,
            },
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy cảnh báo và thông báo: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy cảnh báo và thông báo: {str(e)}")


@cached(ttl=3600, namespace="admin:dashboard:user_stats", tags=["dashboard", "users"])
def get_user_statistics(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê chi tiết về người dùng.

    Args:
        db: Database session
        start_date: Thời gian bắt đầu (mặc định 30 ngày trước)
        end_date: Thời gian kết thúc (mặc định hiện tại)
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary với thông tin thống kê
    """
    # Thiết lập thời gian mặc định
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        # Tổng số người dùng
        total_users = UserRepository.count(db)
        new_users = UserRepository.count_new_users(db, start_date, end_date)
        active_users = UserRepository.count_active_users(db, start_date, end_date)

        # Phân bố người dùng theo tuổi
        age_distribution = UserRepository.get_age_distribution(db)

        # Phân bố người dùng theo quốc gia
        country_distribution = UserRepository.get_country_distribution(db)

        # Người dùng theo thiết bị
        device_distribution = UserRepository.get_device_distribution(db)

        # Tỷ lệ người dùng đăng ký
        subscription_rate = SubscriptionRepository.get_subscription_rate(db)

        # Tỷ lệ giữ chân
        retention_rate = UserRepository.get_retention_rate(db, start_date, end_date)

        # Tỷ lệ người dùng active theo tuần/tháng
        weekly_active_rate = UserRepository.get_weekly_active_rate(db)
        monthly_active_rate = UserRepository.get_monthly_active_rate(db)

        result = {
            "users": {
                "total": total_users,
                "new": new_users,
                "active": active_users,
                "subscription_rate": subscription_rate,
                "retention_rate": retention_rate,
                "weekly_active_rate": weekly_active_rate,
                "monthly_active_rate": monthly_active_rate,
            },
            "distributions": {
                "age": age_distribution,
                "country": country_distribution,
                "device": device_distribution,
            },
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days,
            },
        }

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_STATISTICS",
                        entity_id=0,
                        description="Viewed detailed user statistics",
                        metadata={
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "total_users": total_users,
                            "new_users": new_users,
                            "active_users": active_users,
                            "subscription_rate": subscription_rate,
                            "period_days": (end_date - start_date).days,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê người dùng: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê người dùng: {str(e)}")


@cached(
    ttl=3600, namespace="admin:dashboard:reading_stats", tags=["dashboard", "reading"]
)
def get_reading_statistics(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê chi tiết về hoạt động đọc sách.

    Args:
        db: Database session
        start_date: Thời gian bắt đầu (mặc định 30 ngày trước)
        end_date: Thời gian kết thúc (mặc định hiện tại)
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary với thông tin thống kê
    """
    # Thiết lập thời gian mặc định
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        # Tổng thời gian đọc
        total_reading_time = ReadingSessionRepository.get_total_reading_time(db)
        period_reading_time = ReadingSessionRepository.get_total_reading_time(
            db, start_date, end_date
        )

        # Thời gian đọc trung bình
        avg_reading_time = ReadingSessionRepository.get_average_reading_time(
            db, start_date, end_date
        )

        # Số phiên đọc
        total_sessions = ReadingSessionRepository.count(db)
        period_sessions = ReadingSessionRepository.count(db, start_date, end_date)

        # Phân bố thời gian đọc theo giờ trong ngày
        hourly_distribution = ReadingSessionRepository.get_hourly_distribution(
            db, start_date, end_date
        )

        # Phân bố thời gian đọc theo ngày trong tuần
        weekly_distribution = ReadingSessionRepository.get_weekly_distribution(
            db, start_date, end_date
        )

        # Sách được đọc nhiều nhất
        most_read_books = ReadingSessionRepository.get_most_read_books(
            db, start_date, end_date, limit=10
        )

        # Người dùng đọc nhiều nhất
        most_active_readers = ReadingSessionRepository.get_most_active_readers(
            db, start_date, end_date, limit=10
        )

        result = {
            "reading": {
                "total_time": total_reading_time,
                "period_time": period_reading_time,
                "avg_time": avg_reading_time,
                "total_sessions": total_sessions,
                "period_sessions": period_sessions,
            },
            "distributions": {
                "hourly": hourly_distribution,
                "weekly": weekly_distribution,
            },
            "rankings": {
                "most_read_books": most_read_books,
                "most_active_readers": most_active_readers,
            },
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days,
            },
        }

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="READING_STATISTICS",
                        entity_id=0,
                        description="Viewed detailed reading statistics",
                        metadata={
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "total_time": total_reading_time,
                            "period_time": period_reading_time,
                            "avg_time": avg_reading_time,
                            "total_sessions": total_sessions,
                            "period_sessions": period_sessions,
                            "period_days": (end_date - start_date).days,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê đọc sách: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê đọc sách: {str(e)}")


@cached(
    ttl=3600,
    namespace="admin:dashboard:subscription_stats",
    tags=["dashboard", "subscriptions"],
)
def get_subscription_statistics(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê chi tiết về đăng ký.

    Args:
        db: Database session
        start_date: Thời gian bắt đầu (mặc định 30 ngày trước)
        end_date: Thời gian kết thúc (mặc định hiện tại)
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary với thông tin thống kê
    """
    # Thiết lập thời gian mặc định
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        # Tổng số đăng ký
        total_subscriptions = SubscriptionRepository.count(db)
        active_subscriptions = SubscriptionRepository.count(db, status="active")

        # Đăng ký mới trong khoảng thời gian
        new_subscriptions = SubscriptionRepository.count_new_subscriptions(
            db, start_date, end_date
        )

        # Đăng ký hết hạn trong khoảng thời gian
        expired_subscriptions = SubscriptionRepository.count_expired_subscriptions(
            db, start_date, end_date
        )

        # Đăng ký được gia hạn trong khoảng thời gian
        renewed_subscriptions = SubscriptionRepository.count_renewed_subscriptions(
            db, start_date, end_date
        )

        # Phân bố theo loại đăng ký
        plan_distribution = SubscriptionRepository.get_plan_distribution(db)

        # Tỷ lệ chuyển đổi (từ free -> paid)
        conversion_rate = SubscriptionRepository.get_conversion_rate(
            db, start_date, end_date
        )

        # Tỷ lệ hủy đăng ký
        churn_rate = SubscriptionRepository.get_churn_rate(db, start_date, end_date)

        # Thời gian đăng ký trung bình
        avg_subscription_time = SubscriptionRepository.get_average_subscription_time(db)

        result = {
            "subscriptions": {
                "total": total_subscriptions,
                "active": active_subscriptions,
                "new": new_subscriptions,
                "expired": expired_subscriptions,
                "renewed": renewed_subscriptions,
                "conversion_rate": conversion_rate,
                "churn_rate": churn_rate,
                "avg_time": avg_subscription_time,
            },
            "distributions": {"plan": plan_distribution},
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days,
            },
        }

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SUBSCRIPTION_STATISTICS",
                        entity_id=0,
                        description="Viewed detailed subscription statistics",
                        metadata={
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "total_subscriptions": total_subscriptions,
                            "active_subscriptions": active_subscriptions,
                            "new_subscriptions": new_subscriptions,
                            "conversion_rate": conversion_rate,
                            "churn_rate": churn_rate,
                            "period_days": (end_date - start_date).days,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê đăng ký: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê đăng ký: {str(e)}")


@cached(
    ttl=3600, namespace="admin:dashboard:review_stats", tags=["dashboard", "reviews"]
)
def get_review_statistics(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê chi tiết về đánh giá.

    Args:
        db: Database session
        start_date: Thời gian bắt đầu (mặc định 30 ngày trước)
        end_date: Thời gian kết thúc (mặc định hiện tại)
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary với thông tin thống kê
    """
    # Thiết lập thời gian mặc định
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        # Tổng số đánh giá
        total_reviews = ReviewRepository.count(db)

        # Đánh giá mới trong khoảng thời gian
        new_reviews = ReviewRepository.count_new_reviews(db, start_date, end_date)

        # Điểm đánh giá trung bình
        avg_rating = ReviewRepository.get_average_rating(db)
        period_avg_rating = ReviewRepository.get_average_rating(
            db, start_date, end_date
        )

        # Phân bố theo số sao
        rating_distribution = ReviewRepository.get_rating_distribution(db)

        # Sách có đánh giá cao nhất
        highest_rated_books = ReviewRepository.get_highest_rated_books(db, limit=10)

        # Sách có nhiều đánh giá nhất
        most_reviewed_books = ReviewRepository.get_most_reviewed_books(db, limit=10)

        result = {
            "reviews": {
                "total": total_reviews,
                "new": new_reviews,
                "avg_rating": avg_rating,
                "period_avg_rating": period_avg_rating,
            },
            "distributions": {"rating": rating_distribution},
            "rankings": {
                "highest_rated_books": highest_rated_books,
                "most_reviewed_books": most_reviewed_books,
            },
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days,
            },
        }

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="REVIEW_STATISTICS",
                        entity_id=0,
                        description="Viewed detailed review statistics",
                        metadata={
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "total_reviews": total_reviews,
                            "new_reviews": new_reviews,
                            "avg_rating": avg_rating,
                            "period_avg_rating": period_avg_rating,
                            "period_days": (end_date - start_date).days,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê đánh giá: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê đánh giá: {str(e)}")
