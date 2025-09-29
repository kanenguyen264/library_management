from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, Date, and_, or_
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
import random  # Tạm thời dùng để tạo dữ liệu mẫu

from app.admin_site.schemas.analytics import (
    UserAnalyticsResponse,
    ContentAnalyticsResponse,
    RevenueAnalyticsResponse,
    EngagementAnalyticsResponse,
    UserAnalyticsDataPoint,
    ContentAnalyticsDataPoint,
    RevenueAnalyticsDataPoint,
    EngagementAnalyticsDataPoint,
)
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.admin_site.repositories.analytics_repo import AnalyticsRepository
from app.cache.decorators import cached
from app.core.exceptions import (
    ServerException,
    ValidationException,
    BadRequestException,
)

logger = get_logger(__name__)


@cached(ttl=1800, namespace="admin:analytics:user", tags=["analytics", "users"])
def get_user_analytics(
    db: Session,
    start_date: date,
    end_date: date,
    interval: str = "day",
    metrics: Optional[List[str]] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê người dùng.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        interval: Khoảng thời gian ('day', 'week', 'month')
        metrics: Danh sách các chỉ số cần lấy
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary chứa dữ liệu thống kê

    Raises:
        BadRequestException: Nếu tham số không hợp lệ
        ServerException: Nếu có lỗi khi lấy dữ liệu
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian thống kê
    if (end_date - start_date).days > 365:
        raise BadRequestException(detail="Khoảng thời gian thống kê tối đa là 1 năm")

    # Kiểm tra interval hợp lệ
    valid_intervals = ["day", "week", "month"]
    if interval not in valid_intervals:
        raise BadRequestException(
            detail=f"Interval không hợp lệ. Chọn một trong: {', '.join(valid_intervals)}"
        )

    try:
        # Lấy dữ liệu tăng trưởng người dùng
        growth_data = AnalyticsRepository.get_user_growth_data(
            db, start_date, end_date, interval
        )

        # Lấy dữ liệu nhân khẩu học người dùng
        demographics_data = AnalyticsRepository.get_user_demographics(db)

        # Kết hợp dữ liệu
        result = {
            "growth": growth_data,
            "demographics": demographics_data,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "interval": interval,
            },
        }

        # Lọc các metrics nếu có chỉ định
        if metrics:
            filtered_result = {"period": result["period"]}
            for metric in metrics:
                if metric in result:
                    filtered_result[metric] = result[metric]
            result = filtered_result

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ANALYTICS",
                        entity_id=0,
                        description="Viewed user analytics",
                        metadata={
                            "analytics_type": "user",
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "interval": interval,
                            "metrics": metrics,
                            "data_points_count": len(growth_data) if growth_data else 0,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê người dùng: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê người dùng: {str(e)}")


@cached(ttl=1800, namespace="admin:analytics:content", tags=["analytics", "content"])
def get_content_analytics(
    db: Session,
    start_date: date,
    end_date: date,
    interval: str = "day",
    content_type: Optional[str] = None,
    metrics: Optional[List[str]] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê nội dung.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        interval: Khoảng thời gian ('day', 'week', 'month')
        content_type: Loại nội dung cần lọc
        metrics: Danh sách các chỉ số cần lấy
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary chứa dữ liệu thống kê

    Raises:
        BadRequestException: Nếu tham số không hợp lệ
        ServerException: Nếu có lỗi khi lấy dữ liệu
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian thống kê
    if (end_date - start_date).days > 365:
        raise BadRequestException(detail="Khoảng thời gian thống kê tối đa là 1 năm")

    # Kiểm tra interval hợp lệ
    valid_intervals = ["day", "week", "month"]
    if interval not in valid_intervals:
        raise BadRequestException(
            detail=f"Interval không hợp lệ. Chọn một trong: {', '.join(valid_intervals)}"
        )

    try:
        # Lấy dữ liệu thống kê nội dung
        content_stats = AnalyticsRepository.get_content_stats(
            db, start_date, end_date, interval, content_type
        )

        # Tạo kết quả
        result = {
            "stats": content_stats,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "interval": interval,
            },
        }

        if content_type:
            result["content_type"] = content_type

        # Lọc các metrics nếu có chỉ định
        if metrics:
            filtered_result = {"period": result["period"]}
            if content_type:
                filtered_result["content_type"] = content_type

            for metric in metrics:
                if metric in result:
                    filtered_result[metric] = result[metric]
            result = filtered_result

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ANALYTICS",
                        entity_id=0,
                        description="Viewed content analytics",
                        metadata={
                            "analytics_type": "content",
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "interval": interval,
                            "content_type": content_type,
                            "metrics": metrics,
                            "data_points_count": (
                                len(content_stats) if content_stats else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê nội dung: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê nội dung: {str(e)}")


@cached(ttl=1800, namespace="admin:analytics:revenue", tags=["analytics", "revenue"])
def get_revenue_analytics(
    db: Session,
    start_date: date,
    end_date: date,
    interval: str = "day",
    metrics: Optional[List[str]] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê doanh thu.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        interval: Khoảng thời gian ('day', 'week', 'month')
        metrics: Danh sách các chỉ số cần lấy
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary chứa dữ liệu thống kê

    Raises:
        BadRequestException: Nếu tham số không hợp lệ
        ServerException: Nếu có lỗi khi lấy dữ liệu
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian thống kê
    if (end_date - start_date).days > 365:
        raise BadRequestException(detail="Khoảng thời gian thống kê tối đa là 1 năm")

    # Kiểm tra interval hợp lệ
    valid_intervals = ["day", "week", "month"]
    if interval not in valid_intervals:
        raise BadRequestException(
            detail=f"Interval không hợp lệ. Chọn một trong: {', '.join(valid_intervals)}"
        )

    try:
        # Lấy dữ liệu thống kê doanh thu
        revenue_stats = AnalyticsRepository.get_revenue_stats(
            db, start_date, end_date, interval
        )

        # Tạo kết quả
        result = {
            "revenue": revenue_stats,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "interval": interval,
            },
        }

        # Lọc các metrics nếu có chỉ định
        if metrics:
            filtered_result = {"period": result["period"]}
            for metric in metrics:
                if metric in result:
                    filtered_result[metric] = result[metric]
            result = filtered_result

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ANALYTICS",
                        entity_id=0,
                        description="Viewed revenue analytics",
                        metadata={
                            "analytics_type": "revenue",
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "interval": interval,
                            "metrics": metrics,
                            "data_points_count": (
                                len(revenue_stats) if revenue_stats else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê doanh thu: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê doanh thu: {str(e)}")


@cached(
    ttl=1800, namespace="admin:analytics:engagement", tags=["analytics", "engagement"]
)
def get_engagement_analytics(
    db: Session,
    start_date: date,
    end_date: date,
    interval: str = "day",
    activity_type: Optional[str] = None,
    metrics: Optional[List[str]] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê mức độ tương tác.

    Args:
        db: Database session
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        interval: Khoảng thời gian ('day', 'week', 'month')
        activity_type: Loại hoạt động cần lọc
        metrics: Danh sách các chỉ số cần lấy
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary chứa dữ liệu thống kê

    Raises:
        BadRequestException: Nếu tham số không hợp lệ
        ServerException: Nếu có lỗi khi lấy dữ liệu
    """
    # Kiểm tra tham số
    if start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Giới hạn khoảng thời gian thống kê
    if (end_date - start_date).days > 365:
        raise BadRequestException(detail="Khoảng thời gian thống kê tối đa là 1 năm")

    # Kiểm tra interval hợp lệ
    valid_intervals = ["day", "week", "month"]
    if interval not in valid_intervals:
        raise BadRequestException(
            detail=f"Interval không hợp lệ. Chọn một trong: {', '.join(valid_intervals)}"
        )

    try:
        # Lấy dữ liệu thống kê tương tác
        engagement_stats = AnalyticsRepository.get_engagement_stats(
            db, start_date, end_date, interval, activity_type
        )

        # Tạo kết quả
        result = {
            "engagement": engagement_stats,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "interval": interval,
            },
        }

        if activity_type:
            result["activity_type"] = activity_type

        # Lọc các metrics nếu có chỉ định
        if metrics:
            filtered_result = {"period": result["period"]}
            if activity_type:
                filtered_result["activity_type"] = activity_type

            for metric in metrics:
                if metric in result:
                    filtered_result[metric] = result[metric]
            result = filtered_result

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ANALYTICS",
                        entity_id=0,
                        description="Viewed engagement analytics",
                        metadata={
                            "analytics_type": "engagement",
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "interval": interval,
                            "activity_type": activity_type,
                            "metrics": metrics,
                            "data_points_count": (
                                len(engagement_stats) if engagement_stats else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê tương tác: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê tương tác: {str(e)}")


# Thêm class AnalyticsService
class AnalyticsService:
    """Service class cho phân tích dữ liệu"""

    def __init__(self, db: Session):
        """Khởi tạo AnalyticsService

        Args:
            db: Database session
        """
        self.db = db
        self.logger = logger

    async def get_user_analytics(
        self,
        start_date: date,
        end_date: date,
        interval: str = "day",
        metrics: Optional[List[str]] = None,
    ) -> UserAnalyticsResponse:
        """Lấy phân tích về người dùng

        Args:
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            interval: Khoảng thời gian ('day', 'week', 'month')
            metrics: Danh sách các chỉ số cần lấy

        Returns:
            Dữ liệu phân tích người dùng
        """
        # Sử dụng hàm sẵn có
        result = get_user_analytics(self.db, start_date, end_date, interval, metrics)

        # Chuyển đổi kết quả sang đối tượng schema
        data_points = []
        for point in result.get("growth", []):
            data_points.append(
                UserAnalyticsDataPoint(
                    date=point.get("date"),
                    new_users=point.get("new_users", 0),
                    active_users=point.get("active_users", 0),
                    total_users=point.get("total_users", 0),
                    returning_users=point.get("returning_users", 0),
                    churned_users=point.get("churned_users", 0),
                )
            )

        return UserAnalyticsResponse(
            summary={
                "total_users": result.get("demographics", {}).get("total_users", 0),
                "active_users": result.get("demographics", {}).get("active_users", 0),
                "growth_rate": result.get("demographics", {}).get("growth_rate", 0),
                "retention_rate": result.get("demographics", {}).get(
                    "retention_rate", 0
                ),
            },
            data_points=data_points,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_content_analytics(
        self,
        start_date: date,
        end_date: date,
        interval: str = "day",
        content_type: Optional[str] = None,
        metrics: Optional[List[str]] = None,
    ) -> ContentAnalyticsResponse:
        """Lấy phân tích về nội dung

        Args:
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            interval: Khoảng thời gian ('day', 'week', 'month')
            content_type: Loại nội dung
            metrics: Danh sách các chỉ số cần lấy

        Returns:
            Dữ liệu phân tích nội dung
        """
        # Sử dụng hàm sẵn có
        result = get_content_analytics(
            self.db, start_date, end_date, interval, content_type, metrics
        )

        # Chuyển đổi kết quả sang đối tượng schema
        data_points = []
        for point in result.get("stats", []):
            data_points.append(
                ContentAnalyticsDataPoint(
                    date=point.get("date"),
                    new_content=point.get("new_content", 0),
                    views=point.get("views", 0),
                    likes=point.get("likes", 0),
                    comments=point.get("comments", 0),
                    shares=point.get("shares", 0),
                )
            )

        return ContentAnalyticsResponse(
            summary={
                "total_content": result.get("summary", {}).get("total_content", 0),
                "avg_engagement": result.get("summary", {}).get("avg_engagement", 0),
                "popular_categories": result.get("summary", {}).get(
                    "popular_categories", []
                ),
            },
            data_points=data_points,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_revenue_analytics(
        self,
        start_date: date,
        end_date: date,
        interval: str = "day",
        metrics: Optional[List[str]] = None,
    ) -> RevenueAnalyticsResponse:
        """Lấy phân tích về doanh thu

        Args:
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            interval: Khoảng thời gian ('day', 'week', 'month')
            metrics: Danh sách các chỉ số cần lấy

        Returns:
            Dữ liệu phân tích doanh thu
        """
        # Sử dụng hàm sẵn có
        result = get_revenue_analytics(self.db, start_date, end_date, interval, metrics)

        # Chuyển đổi kết quả sang đối tượng schema
        data_points = []
        for point in result.get("revenue", []):
            data_points.append(
                RevenueAnalyticsDataPoint(
                    date=point.get("date"),
                    total_revenue=point.get("total_revenue", 0),
                    subscription_revenue=point.get("subscription_revenue", 0),
                    one_time_purchases=point.get("one_time_purchases", 0),
                    refunds=point.get("refunds", 0),
                )
            )

        return RevenueAnalyticsResponse(
            summary={
                "total_revenue": result.get("summary", {}).get("total_revenue", 0),
                "growth_rate": result.get("summary", {}).get("growth_rate", 0),
                "arpu": result.get("summary", {}).get("arpu", 0),
                "ltv": result.get("summary", {}).get("ltv", 0),
            },
            data_points=data_points,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_engagement_analytics(
        self,
        start_date: date,
        end_date: date,
        interval: str = "day",
        activity_type: Optional[str] = None,
        metrics: Optional[List[str]] = None,
    ) -> EngagementAnalyticsResponse:
        """Lấy phân tích về tương tác

        Args:
            start_date: Ngày bắt đầu
            end_date: Ngày kết thúc
            interval: Khoảng thời gian ('day', 'week', 'month')
            activity_type: Loại hoạt động
            metrics: Danh sách các chỉ số cần lấy

        Returns:
            Dữ liệu phân tích tương tác
        """
        # Sử dụng hàm sẵn có
        result = get_engagement_analytics(
            self.db, start_date, end_date, interval, activity_type, metrics
        )

        # Chuyển đổi kết quả sang đối tượng schema
        data_points = []
        for point in result.get("engagement", []):
            data_points.append(
                EngagementAnalyticsDataPoint(
                    date=point.get("date"),
                    sessions=point.get("sessions", 0),
                    avg_session_duration=point.get("avg_session_duration", 0),
                    page_views=point.get("page_views", 0),
                    bounce_rate=point.get("bounce_rate", 0),
                    interactions=point.get("interactions", 0),
                )
            )

        return EngagementAnalyticsResponse(
            summary={
                "total_sessions": result.get("summary", {}).get("total_sessions", 0),
                "avg_session_duration": result.get("summary", {}).get(
                    "avg_session_duration", 0
                ),
                "avg_pages_per_session": result.get("summary", {}).get(
                    "avg_pages_per_session", 0
                ),
                "bounce_rate": result.get("summary", {}).get("bounce_rate", 0),
            },
            data_points=data_points,
            start_date=start_date,
            end_date=end_date,
        )
