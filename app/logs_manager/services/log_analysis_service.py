from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, cast, Date
from datetime import datetime, timezone, timedelta
import logging

from app.logs_manager.models.user_activity_log import UserActivityLog
from app.logs_manager.models.admin_activity_log import AdminActivityLog
from app.logs_manager.models.error_log import ErrorLog
from app.logs_manager.models.authentication_log import AuthenticationLog
from app.logs_manager.models.performance_log import PerformanceLog
from app.logs_manager.models.api_request_log import ApiRequestLog
from app.logs_manager.models.search_log import SearchLog

logger = logging.getLogger(__name__)


def get_log_summary(db: Session, days: int = 30) -> Dict[str, Any]:
    """
    Get summary of all logs in the system

    Args:
        db: Database session
        days: Number of days to analyze

    Returns:
        Dict with summary data
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Count logs by type
        user_activity_count = (
            db.query(func.count(UserActivityLog.id))
            .filter(UserActivityLog.timestamp >= start_date)
            .scalar()
            or 0
        )

        admin_activity_count = (
            db.query(func.count(AdminActivityLog.id))
            .filter(AdminActivityLog.timestamp >= start_date)
            .scalar()
            or 0
        )

        error_count = (
            db.query(func.count(ErrorLog.id))
            .filter(ErrorLog.timestamp >= start_date)
            .scalar()
            or 0
        )

        auth_count = (
            db.query(func.count(AuthenticationLog.id))
            .filter(AuthenticationLog.timestamp >= start_date)
            .scalar()
            or 0
        )

        perf_count = (
            db.query(func.count(PerformanceLog.id))
            .filter(PerformanceLog.timestamp >= start_date)
            .scalar()
            or 0
        )

        api_count = (
            db.query(func.count(ApiRequestLog.id))
            .filter(ApiRequestLog.timestamp >= start_date)
            .scalar()
            or 0
        )

        search_count = (
            db.query(func.count(SearchLog.id))
            .filter(SearchLog.timestamp >= start_date)
            .scalar()
            or 0
        )

        # Get top error levels
        error_levels = (
            db.query(ErrorLog.error_level, func.count(ErrorLog.id).label("count"))
            .filter(ErrorLog.timestamp >= start_date)
            .group_by(ErrorLog.error_level)
            .order_by(desc("count"))
            .limit(5)
            .all()
        )

        # Get top API endpoints
        top_endpoints = (
            db.query(
                ApiRequestLog.endpoint, func.count(ApiRequestLog.id).label("count")
            )
            .filter(ApiRequestLog.timestamp >= start_date)
            .group_by(ApiRequestLog.endpoint)
            .order_by(desc("count"))
            .limit(5)
            .all()
        )

        # Create summary
        return {
            "period_days": days,
            "start_date": start_date,
            "end_date": datetime.now(timezone.utc),
            "counts": {
                "user_activity_logs": user_activity_count,
                "admin_activity_logs": admin_activity_count,
                "error_logs": error_count,
                "authentication_logs": auth_count,
                "performance_logs": perf_count,
                "api_request_logs": api_count,
                "search_logs": search_count,
                "total": (
                    user_activity_count
                    + admin_activity_count
                    + error_count
                    + auth_count
                    + perf_count
                    + api_count
                    + search_count
                ),
            },
            "top_error_levels": [
                {"level": level, "count": count} for level, count in error_levels
            ],
            "top_endpoints": [
                {"endpoint": endpoint, "count": count}
                for endpoint, count in top_endpoints
            ],
        }
    except Exception as e:
        logger.error(f"Error getting log summary: {str(e)}")
        raise


def get_error_trends(
    db: Session,
    days: int = 30,
    error_level: Optional[str] = None,
    error_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get error trends by day

    Args:
        db: Database session
        days: Number of days to analyze
        error_level: Filter by error level
        error_code: Filter by error code

    Returns:
        List of dicts with error trend data
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Build query
        query = db.query(
            cast(ErrorLog.timestamp, Date).label("date"),
            func.count(ErrorLog.id).label("count"),
        ).filter(ErrorLog.timestamp >= start_date)

        # Apply filters
        if error_level:
            query = query.filter(ErrorLog.error_level == error_level)
        if error_code:
            query = query.filter(ErrorLog.error_code == error_code)

        # Group and order
        result = query.group_by("date").order_by("date").all()

        # Format result
        return [{"date": date.isoformat(), "count": count} for date, count in result]
    except Exception as e:
        logger.error(f"Error getting error trends: {str(e)}")
        raise


def get_user_activity_trends(db: Session, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get user activity trends by day

    Args:
        db: Database session
        days: Number of days to analyze

    Returns:
        List of dicts with user activity trend data
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Get activity count by day
        result = (
            db.query(
                cast(UserActivityLog.timestamp, Date).label("date"),
                func.count(UserActivityLog.id).label("count"),
            )
            .filter(UserActivityLog.timestamp >= start_date)
            .group_by("date")
            .order_by("date")
            .all()
        )

        # Format result
        return [{"date": date.isoformat(), "count": count} for date, count in result]
    except Exception as e:
        logger.error(f"Error getting user activity trends: {str(e)}")
        raise


def get_admin_activity_trends(db: Session, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get admin activity trends by day

    Args:
        db: Database session
        days: Number of days to analyze

    Returns:
        List of dicts with admin activity trend data
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Get activity count by day
        result = (
            db.query(
                cast(AdminActivityLog.timestamp, Date).label("date"),
                func.count(AdminActivityLog.id).label("count"),
            )
            .filter(AdminActivityLog.timestamp >= start_date)
            .group_by("date")
            .order_by("date")
            .all()
        )

        # Format result
        return [{"date": date.isoformat(), "count": count} for date, count in result]
    except Exception as e:
        logger.error(f"Error getting admin activity trends: {str(e)}")
        raise


def get_api_usage_trends(db: Session, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get API usage trends by day

    Args:
        db: Database session
        days: Number of days to analyze

    Returns:
        List of dicts with API usage trend data
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Get API request count by day
        result = (
            db.query(
                cast(ApiRequestLog.timestamp, Date).label("date"),
                func.count(ApiRequestLog.id).label("count"),
            )
            .filter(ApiRequestLog.timestamp >= start_date)
            .group_by("date")
            .order_by("date")
            .all()
        )

        # Format result
        return [{"date": date.isoformat(), "count": count} for date, count in result]
    except Exception as e:
        logger.error(f"Error getting API usage trends: {str(e)}")
        raise


def get_performance_trends(db: Session, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get performance trends by day (average response time)

    Args:
        db: Database session
        days: Number of days to analyze

    Returns:
        List of dicts with performance trend data
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Get average response time by day
        result = (
            db.query(
                cast(PerformanceLog.timestamp, Date).label("date"),
                func.avg(PerformanceLog.response_time).label("avg_response_time"),
                func.count(PerformanceLog.id).label("count"),
            )
            .filter(PerformanceLog.timestamp >= start_date)
            .group_by("date")
            .order_by("date")
            .all()
        )

        # Format result
        return [
            {
                "date": date.isoformat(),
                "avg_response_time": float(avg_time),
                "count": count,
            }
            for date, avg_time, count in result
        ]
    except Exception as e:
        logger.error(f"Error getting performance trends: {str(e)}")
        raise


def get_authentication_trends(db: Session, days: int = 30) -> Dict[str, Any]:
    """
    Get authentication trends

    Args:
        db: Database session
        days: Number of days to analyze

    Returns:
        Dict with authentication trend data
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Get authentication log counts by status
        status_counts = (
            db.query(
                AuthenticationLog.status,
                func.count(AuthenticationLog.id).label("count"),
            )
            .filter(AuthenticationLog.timestamp >= start_date)
            .group_by(AuthenticationLog.status)
            .all()
        )

        # Get authentication log counts by action
        action_counts = (
            db.query(
                AuthenticationLog.action,
                func.count(AuthenticationLog.id).label("count"),
            )
            .filter(AuthenticationLog.timestamp >= start_date)
            .group_by(AuthenticationLog.action)
            .all()
        )

        # Get authentication log counts by day
        daily_counts = (
            db.query(
                cast(AuthenticationLog.timestamp, Date).label("date"),
                func.count(AuthenticationLog.id).label("count"),
            )
            .filter(AuthenticationLog.timestamp >= start_date)
            .group_by("date")
            .order_by("date")
            .all()
        )

        # Format result
        return {
            "status_counts": [
                {"status": status, "count": count} for status, count in status_counts
            ],
            "action_counts": [
                {"action": action, "count": count} for action, count in action_counts
            ],
            "daily_counts": [
                {"date": date.isoformat(), "count": count}
                for date, count in daily_counts
            ],
        }
    except Exception as e:
        logger.error(f"Error getting authentication trends: {str(e)}")
        raise


def get_search_trends(db: Session, days: int = 30, limit: int = 20) -> Dict[str, Any]:
    """
    Get search trends

    Args:
        db: Database session
        days: Number of days to analyze
        limit: Maximum number of popular terms to return

    Returns:
        Dict with search trend data
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Get popular search terms
        popular_terms = (
            db.query(SearchLog.query, func.count(SearchLog.id).label("count"))
            .filter(SearchLog.timestamp >= start_date)
            .group_by(SearchLog.query)
            .order_by(desc("count"))
            .limit(limit)
            .all()
        )

        # Get search count by day
        daily_counts = (
            db.query(
                cast(SearchLog.timestamp, Date).label("date"),
                func.count(SearchLog.id).label("count"),
            )
            .filter(SearchLog.timestamp >= start_date)
            .group_by("date")
            .order_by("date")
            .all()
        )

        # Format result
        return {
            "popular_terms": [
                {"term": term, "count": count} for term, count in popular_terms
            ],
            "daily_counts": [
                {"date": date.isoformat(), "count": count}
                for date, count in daily_counts
            ],
        }
    except Exception as e:
        logger.error(f"Error getting search trends: {str(e)}")
        raise


class LogAnalysisService:
    """
    Service xử lý nghiệp vụ liên quan đến phân tích log
    """

    async def get_summary(self, db: Session, days: int = 30) -> Dict[str, Any]:
        """
        Lấy tổng quan về tất cả các log trong hệ thống

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích

        Returns:
            Dict với dữ liệu tổng quan
        """
        return get_log_summary(db, days)

    async def get_error_trends(
        self,
        db: Session,
        days: int = 30,
        error_level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lấy xu hướng lỗi theo ngày

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích
            error_level: Lọc theo mức độ lỗi

        Returns:
            Danh sách dữ liệu xu hướng lỗi
        """
        return get_error_trends(db, days, error_level)

    async def get_user_activities(
        self, db: Session, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Lấy xu hướng hoạt động của người dùng theo ngày

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích

        Returns:
            Danh sách dữ liệu xu hướng hoạt động
        """
        return get_user_activity_trends(db, days)

    async def get_admin_activities(
        self, db: Session, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Lấy xu hướng hoạt động của admin theo ngày

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích

        Returns:
            Danh sách dữ liệu xu hướng hoạt động
        """
        return get_admin_activity_trends(db, days)

    async def get_api_usage(self, db: Session, days: int = 30) -> List[Dict[str, Any]]:
        """
        Lấy xu hướng sử dụng API theo ngày

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích

        Returns:
            Danh sách dữ liệu xu hướng sử dụng API
        """
        return get_api_usage_trends(db, days)

    async def get_performance(
        self, db: Session, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Lấy xu hướng hiệu suất theo ngày

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích

        Returns:
            Danh sách dữ liệu xu hướng hiệu suất
        """
        return get_performance_trends(db, days)

    async def get_authentication(self, db: Session, days: int = 30) -> Dict[str, Any]:
        """
        Lấy xu hướng xác thực người dùng

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích

        Returns:
            Dict với dữ liệu xu hướng xác thực
        """
        return get_authentication_trends(db, days)

    async def get_search(
        self, db: Session, days: int = 30, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy xu hướng tìm kiếm

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích
            limit: Số lượng tối đa từ khóa phổ biến

        Returns:
            Dict với dữ liệu xu hướng tìm kiếm
        """
        return get_search_trends(db, days, limit)
