"""
Tác vụ thu thập metrics

Module này cung cấp các tác vụ liên quan đến thu thập chỉ số:
- Thu thập chỉ số hệ thống
- Thu thập chỉ số hoạt động
- Thu thập chỉ số người dùng
"""

import datetime
import time
import os
import psutil
import json
import asyncio
from typing import Dict, Any, List, Optional

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.tasks.worker import celery_app
from app.tasks.base_task import BaseTask
from app.core.db import async_session

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.monitoring.metrics.collect_system_metrics",
    queue="monitoring",
)
def collect_system_metrics(self) -> Dict[str, Any]:
    """
    Thu thập các chỉ số hệ thống như CPU, bộ nhớ, disk.

    Returns:
        Dict chứa các chỉ số thu thập được
    """
    try:
        logger.info("Collecting system metrics")

        timestamp = datetime.datetime.now()

        # Thu thập chỉ số CPU
        cpu_metrics = {
            "usage_percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(logical=True),
            "physical_count": psutil.cpu_count(logical=False),
            "load_avg": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        }

        # Thu thập chỉ số bộ nhớ
        memory = psutil.virtual_memory()
        memory_metrics = {
            "total": memory.total,
            "available": memory.available,
            "used": memory.used,
            "percent": memory.percent,
        }

        # Thu thập chỉ số swap
        swap = psutil.swap_memory()
        swap_metrics = {
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
            "percent": swap.percent,
        }

        # Thu thập chỉ số disk
        disk = psutil.disk_usage(settings.MEDIA_ROOT)
        disk_metrics = {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        }

        # Thu thập chỉ số network
        net_io_counters = psutil.net_io_counters()
        network_metrics = {
            "bytes_sent": net_io_counters.bytes_sent,
            "bytes_recv": net_io_counters.bytes_recv,
            "packets_sent": net_io_counters.packets_sent,
            "packets_recv": net_io_counters.packets_recv,
            "errin": net_io_counters.errin,
            "errout": net_io_counters.errout,
            "dropin": net_io_counters.dropin,
            "dropout": net_io_counters.dropout,
        }

        # Tổng hợp kết quả
        metrics = {
            "timestamp": timestamp.isoformat(),
            "cpu": cpu_metrics,
            "memory": memory_metrics,
            "swap": swap_metrics,
            "disk": disk_metrics,
            "network": network_metrics,
        }

        # Lưu metrics vào database
        save_system_metrics(timestamp, metrics)

        return metrics

    except Exception as e:
        logger.error(f"Error collecting system metrics: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e),
        }


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.monitoring.metrics.collect_application_metrics",
    queue="monitoring",
)
def collect_application_metrics(self) -> Dict[str, Any]:
    """
    Thu thập các chỉ số ứng dụng như số lượng request, thời gian phản hồi.

    Returns:
        Dict chứa các chỉ số thu thập được
    """
    try:
        logger.info("Collecting application metrics")

        timestamp = datetime.datetime.now()

        # Thu thập performance metrics từ database
        request_metrics = get_request_metrics()

        # Thu thập chỉ số Celery
        celery_metrics = get_celery_metrics()

        # Thu thập số lượng lỗi từ log
        error_metrics = get_error_metrics()

        # Thu thập thời gian phản hồi API
        api_response_metrics = get_api_response_metrics()

        # Tổng hợp kết quả
        metrics = {
            "timestamp": timestamp.isoformat(),
            "requests": request_metrics,
            "celery": celery_metrics,
            "errors": error_metrics,
            "api_response": api_response_metrics,
        }

        # Lưu metrics vào database
        save_application_metrics(timestamp, metrics)

        return metrics

    except Exception as e:
        logger.error(f"Error collecting application metrics: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e),
        }


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.monitoring.metrics.collect_user_metrics",
    queue="monitoring",
)
def collect_user_metrics(self) -> Dict[str, Any]:
    """
    Thu thập các chỉ số người dùng như số lượng đăng nhập, đăng ký mới.

    Returns:
        Dict chứa các chỉ số thu thập được
    """
    try:
        logger.info("Collecting user metrics")

        timestamp = datetime.datetime.now()

        # Lấy chỉ số người dùng từ database
        user_metrics = get_user_metrics()

        # Lấy chỉ số phiên đọc sách
        reading_metrics = get_reading_metrics()

        # Lấy chỉ số tìm kiếm
        search_metrics = get_search_metrics()

        # Tổng hợp kết quả
        metrics = {
            "timestamp": timestamp.isoformat(),
            "users": user_metrics,
            "reading": reading_metrics,
            "search": search_metrics,
        }

        # Lưu metrics vào database
        save_user_metrics(timestamp, metrics)

        return metrics

    except Exception as e:
        logger.error(f"Error collecting user metrics: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e),
        }


def save_system_metrics(timestamp: datetime.datetime, metrics: Dict[str, Any]) -> None:
    """
    Lưu chỉ số hệ thống vào database.

    Args:
        timestamp: Thời điểm thu thập
        metrics: Chỉ số thu thập được
    """
    try:

        async def save_to_db():
            from app.monitoring.models.metrics import SystemMetrics

            async with async_session() as session:
                # Lưu system metrics
                system_metrics = SystemMetrics(
                    timestamp=timestamp,
                    cpu_usage=metrics["cpu"]["usage_percent"],
                    memory_usage=metrics["memory"]["percent"],
                    disk_usage=metrics["disk"]["percent"],
                    details=json.dumps(metrics),
                )

                session.add(system_metrics)
                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(save_to_db())

    except Exception as e:
        logger.error(f"Error saving system metrics: {str(e)}")


def save_application_metrics(
    timestamp: datetime.datetime, metrics: Dict[str, Any]
) -> None:
    """
    Lưu chỉ số ứng dụng vào database.

    Args:
        timestamp: Thời điểm thu thập
        metrics: Chỉ số thu thập được
    """
    try:

        async def save_to_db():
            from app.monitoring.models.metrics import ApplicationMetrics

            async with async_session() as session:
                # Lưu application metrics
                app_metrics = ApplicationMetrics(
                    timestamp=timestamp,
                    request_count=metrics["requests"].get("total_count", 0),
                    error_count=metrics["errors"].get("total_count", 0),
                    avg_response_time=metrics["api_response"].get("avg_time", 0),
                    details=json.dumps(metrics),
                )

                session.add(app_metrics)
                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(save_to_db())

    except Exception as e:
        logger.error(f"Error saving application metrics: {str(e)}")


def save_user_metrics(timestamp: datetime.datetime, metrics: Dict[str, Any]) -> None:
    """
    Lưu chỉ số người dùng vào database.

    Args:
        timestamp: Thời điểm thu thập
        metrics: Chỉ số thu thập được
    """
    try:

        async def save_to_db():
            from app.monitoring.models.metrics import UserMetrics

            async with async_session() as session:
                # Lưu user metrics
                user_metrics = UserMetrics(
                    timestamp=timestamp,
                    active_users=metrics["users"].get("active_users", 0),
                    new_registrations=metrics["users"].get("new_registrations", 0),
                    reading_sessions=metrics["reading"].get("total_sessions", 0),
                    details=json.dumps(metrics),
                )

                session.add(user_metrics)
                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(save_to_db())

    except Exception as e:
        logger.error(f"Error saving user metrics: {str(e)}")


def get_request_metrics() -> Dict[str, Any]:
    """
    Lấy thống kê request từ middleware và logs.

    Returns:
        Dict chứa thống kê request
    """
    try:

        async def get_from_db():
            from app.monitoring.models.request_log import RequestLog
            from sqlalchemy import func, select, and_

            async with async_session() as session:
                # Thời gian để lấy metrics (1 giờ trước)
                one_hour_ago = datetime.datetime.now() - datetime.timedelta(hours=1)

                # Tổng số request
                stmt_count = select(func.count(RequestLog.id)).where(
                    RequestLog.timestamp >= one_hour_ago
                )
                result_count = await session.execute(stmt_count)
                total_count = result_count.scalar() or 0

                # Số lượng theo endpoint
                stmt_endpoint = (
                    select(
                        RequestLog.endpoint, func.count(RequestLog.id).label("count")
                    )
                    .where(RequestLog.timestamp >= one_hour_ago)
                    .group_by(RequestLog.endpoint)
                    .order_by(func.count(RequestLog.id).desc())
                )

                result_endpoint = await session.execute(stmt_endpoint)
                endpoints = [
                    {"endpoint": row[0], "count": row[1]} for row in result_endpoint
                ]

                # Số lượng theo mã trạng thái
                stmt_status = (
                    select(
                        RequestLog.status_code, func.count(RequestLog.id).label("count")
                    )
                    .where(RequestLog.timestamp >= one_hour_ago)
                    .group_by(RequestLog.status_code)
                    .order_by(RequestLog.status_code)
                )

                result_status = await session.execute(stmt_status)
                status_codes = [
                    {"status_code": row[0], "count": row[1]} for row in result_status
                ]

                return {
                    "total_count": total_count,
                    "by_endpoint": endpoints,
                    "by_status_code": status_codes,
                    "time_period": "last_hour",
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_from_db())

    except Exception as e:
        logger.error(f"Error getting request metrics: {str(e)}")
        return {"total_count": 0, "error": str(e)}


def get_celery_metrics() -> Dict[str, Any]:
    """
    Lấy thống kê Celery từ flower hoặc Redis.

    Returns:
        Dict chứa thống kê Celery
    """
    try:
        # Lấy thông tin từ Celery inspect
        inspector = celery_app.control.inspect()

        # Các tác vụ đang chạy
        active_tasks = inspector.active() or {}
        total_active = sum(len(tasks) for tasks in active_tasks.values())

        # Các tác vụ đang chờ
        reserved_tasks = inspector.reserved() or {}
        total_reserved = sum(len(tasks) for tasks in reserved_tasks.values())

        # Thống kê theo queue
        stats_by_queue = {}
        for worker, tasks in active_tasks.items():
            for task in tasks:
                queue = task.get("delivery_info", {}).get("routing_key", "default")
                if queue in stats_by_queue:
                    stats_by_queue[queue]["active"] += 1
                else:
                    stats_by_queue[queue] = {"active": 1, "reserved": 0}

        for worker, tasks in reserved_tasks.items():
            for task in tasks:
                queue = task.get("delivery_info", {}).get("routing_key", "default")
                if queue in stats_by_queue:
                    stats_by_queue[queue]["reserved"] += 1
                else:
                    stats_by_queue[queue] = {"active": 0, "reserved": 1}

        return {
            "active_tasks": total_active,
            "reserved_tasks": total_reserved,
            "total_workers": len(active_tasks),
            "by_queue": [{"queue": q, "stats": s} for q, s in stats_by_queue.items()],
        }

    except Exception as e:
        logger.error(f"Error getting Celery metrics: {str(e)}")
        return {"active_tasks": 0, "reserved_tasks": 0, "error": str(e)}


def get_error_metrics() -> Dict[str, Any]:
    """
    Lấy thống kê lỗi từ logs.

    Returns:
        Dict chứa thống kê lỗi
    """
    try:

        async def get_from_db():
            from app.logging.models.error_log import ErrorLog
            from sqlalchemy import func, select, and_

            async with async_session() as session:
                # Thời gian để lấy metrics (24 giờ trước)
                one_day_ago = datetime.datetime.now() - datetime.timedelta(days=1)

                # Tổng số lỗi
                stmt_count = select(func.count(ErrorLog.id)).where(
                    ErrorLog.timestamp >= one_day_ago
                )
                result_count = await session.execute(stmt_count)
                total_count = result_count.scalar() or 0

                # Số lượng theo mức độ nghiêm trọng
                stmt_level = (
                    select(ErrorLog.level, func.count(ErrorLog.id).label("count"))
                    .where(ErrorLog.timestamp >= one_day_ago)
                    .group_by(ErrorLog.level)
                    .order_by(ErrorLog.level)
                )

                result_level = await session.execute(stmt_level)
                by_level = [{"level": row[0], "count": row[1]} for row in result_level]

                # Số lượng theo module
                stmt_module = (
                    select(ErrorLog.module, func.count(ErrorLog.id).label("count"))
                    .where(ErrorLog.timestamp >= one_day_ago)
                    .group_by(ErrorLog.module)
                    .order_by(func.count(ErrorLog.id).desc())
                )

                result_module = await session.execute(stmt_module)
                by_module = [
                    {"module": row[0], "count": row[1]} for row in result_module
                ]

                return {
                    "total_count": total_count,
                    "by_level": by_level,
                    "by_module": by_module,
                    "time_period": "last_24h",
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_from_db())

    except Exception as e:
        logger.error(f"Error getting error metrics: {str(e)}")
        return {"total_count": 0, "error": str(e)}


def get_api_response_metrics() -> Dict[str, Any]:
    """
    Lấy thống kê thời gian phản hồi API.

    Returns:
        Dict chứa thống kê thời gian phản hồi
    """
    try:

        async def get_from_db():
            from app.monitoring.models.request_log import RequestLog
            from sqlalchemy import func, select, and_

            async with async_session() as session:
                # Thời gian để lấy metrics (1 giờ trước)
                one_hour_ago = datetime.datetime.now() - datetime.timedelta(hours=1)

                # Thời gian phản hồi trung bình
                stmt_avg = select(func.avg(RequestLog.response_time)).where(
                    RequestLog.timestamp >= one_hour_ago
                )
                result_avg = await session.execute(stmt_avg)
                avg_time = result_avg.scalar() or 0

                # Thời gian phản hồi theo endpoint
                stmt_endpoint = (
                    select(
                        RequestLog.endpoint,
                        func.avg(RequestLog.response_time).label("avg_time"),
                        func.min(RequestLog.response_time).label("min_time"),
                        func.max(RequestLog.response_time).label("max_time"),
                    )
                    .where(RequestLog.timestamp >= one_hour_ago)
                    .group_by(RequestLog.endpoint)
                    .order_by(func.avg(RequestLog.response_time).desc())
                )

                result_endpoint = await session.execute(stmt_endpoint)
                by_endpoint = [
                    {
                        "endpoint": row[0],
                        "avg_time": row[1],
                        "min_time": row[2],
                        "max_time": row[3],
                    }
                    for row in result_endpoint
                ]

                return {
                    "avg_time": avg_time,
                    "by_endpoint": by_endpoint,
                    "time_period": "last_hour",
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_from_db())

    except Exception as e:
        logger.error(f"Error getting API response metrics: {str(e)}")
        return {"avg_time": 0, "error": str(e)}


def get_user_metrics() -> Dict[str, Any]:
    """
    Lấy thống kê người dùng từ database.

    Returns:
        Dict chứa thống kê người dùng
    """
    try:

        async def get_from_db():
            from app.user_site.models.user import User
            from app.security.models.login_history import LoginHistory
            from sqlalchemy import func, select, and_

            async with async_session() as session:
                # Thời gian để lấy metrics
                now = datetime.datetime.now()
                one_day_ago = now - datetime.timedelta(days=1)
                one_week_ago = now - datetime.timedelta(days=7)
                one_month_ago = now - datetime.timedelta(days=30)

                # Tổng số người dùng
                stmt_total = select(func.count(User.id))
                result_total = await session.execute(stmt_total)
                total_users = result_total.scalar() or 0

                # Người dùng mới trong 24 giờ qua
                stmt_new_day = select(func.count(User.id)).where(
                    User.created_at >= one_day_ago
                )
                result_new_day = await session.execute(stmt_new_day)
                new_users_day = result_new_day.scalar() or 0

                # Người dùng mới trong 7 ngày qua
                stmt_new_week = select(func.count(User.id)).where(
                    User.created_at >= one_week_ago
                )
                result_new_week = await session.execute(stmt_new_week)
                new_users_week = result_new_week.scalar() or 0

                # Người dùng hoạt động trong 24 giờ qua
                stmt_active_day = select(
                    func.count(func.distinct(LoginHistory.user_id))
                ).where(LoginHistory.login_time >= one_day_ago)
                result_active_day = await session.execute(stmt_active_day)
                active_users_day = result_active_day.scalar() or 0

                # Người dùng hoạt động trong 7 ngày qua
                stmt_active_week = select(
                    func.count(func.distinct(LoginHistory.user_id))
                ).where(LoginHistory.login_time >= one_week_ago)
                result_active_week = await session.execute(stmt_active_week)
                active_users_week = result_active_week.scalar() or 0

                return {
                    "total_users": total_users,
                    "new_registrations": new_users_day,
                    "new_users_last_7_days": new_users_week,
                    "active_users": active_users_day,
                    "active_users_last_7_days": active_users_week,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_from_db())

    except Exception as e:
        logger.error(f"Error getting user metrics: {str(e)}")
        return {"total_users": 0, "error": str(e)}


def get_reading_metrics() -> Dict[str, Any]:
    """
    Lấy thống kê phiên đọc sách từ database.

    Returns:
        Dict chứa thống kê phiên đọc sách
    """
    try:

        async def get_from_db():
            from app.user_site.models.reading_session import ReadingSession
            from app.user_site.models.book import Book
            from sqlalchemy import func, select, and_, desc

            async with async_session() as session:
                # Thời gian để lấy metrics
                now = datetime.datetime.now()
                one_day_ago = now - datetime.timedelta(days=1)

                # Tổng số phiên đọc trong 24 giờ qua
                stmt_sessions = select(func.count(ReadingSession.id)).where(
                    ReadingSession.start_time >= one_day_ago
                )
                result_sessions = await session.execute(stmt_sessions)
                total_sessions = result_sessions.scalar() or 0

                # Tổng thời gian đọc trong 24 giờ qua (tính bằng phút)
                stmt_duration = select(func.sum(ReadingSession.duration_minutes)).where(
                    ReadingSession.start_time >= one_day_ago
                )
                result_duration = await session.execute(stmt_duration)
                total_duration = result_duration.scalar() or 0

                # Số người dùng đọc sách trong 24 giờ qua
                stmt_readers = select(
                    func.count(func.distinct(ReadingSession.user_id))
                ).where(ReadingSession.start_time >= one_day_ago)
                result_readers = await session.execute(stmt_readers)
                total_readers = result_readers.scalar() or 0

                # Sách được đọc nhiều nhất trong 24 giờ qua
                stmt_popular = (
                    select(
                        ReadingSession.book_id,
                        Book.title,
                        func.count(ReadingSession.id).label("session_count"),
                    )
                    .join(Book, ReadingSession.book_id == Book.id)
                    .where(ReadingSession.start_time >= one_day_ago)
                    .group_by(ReadingSession.book_id, Book.title)
                    .order_by(desc("session_count"))
                    .limit(5)
                )

                result_popular = await session.execute(stmt_popular)
                popular_books = [
                    {
                        "book_id": row[0],
                        "title": row[1],
                        "session_count": row[2],
                    }
                    for row in result_popular
                ]

                return {
                    "total_sessions": total_sessions,
                    "total_duration_minutes": total_duration,
                    "average_duration": (
                        total_duration / total_sessions if total_sessions > 0 else 0
                    ),
                    "total_readers": total_readers,
                    "popular_books": popular_books,
                    "time_period": "last_24h",
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_from_db())

    except Exception as e:
        logger.error(f"Error getting reading metrics: {str(e)}")
        return {"total_sessions": 0, "error": str(e)}


def get_search_metrics() -> Dict[str, Any]:
    """
    Lấy thống kê tìm kiếm từ database.

    Returns:
        Dict chứa thống kê tìm kiếm
    """
    try:

        async def get_from_db():
            from app.user_site.models.search_log import SearchLog
            from sqlalchemy import func, select, and_, desc

            async with async_session() as session:
                # Thời gian để lấy metrics
                now = datetime.datetime.now()
                one_day_ago = now - datetime.timedelta(days=1)

                # Tổng số tìm kiếm trong 24 giờ qua
                stmt_count = select(func.count(SearchLog.id)).where(
                    SearchLog.timestamp >= one_day_ago
                )
                result_count = await session.execute(stmt_count)
                total_searches = result_count.scalar() or 0

                # Số người dùng tìm kiếm trong 24 giờ qua
                stmt_users = select(func.count(func.distinct(SearchLog.user_id))).where(
                    SearchLog.timestamp >= one_day_ago
                )
                result_users = await session.execute(stmt_users)
                total_users = result_users.scalar() or 0

                # Từ khóa phổ biến nhất trong 24 giờ qua
                stmt_terms = (
                    select(
                        SearchLog.query, func.count(SearchLog.id).label("search_count")
                    )
                    .where(SearchLog.timestamp >= one_day_ago)
                    .group_by(SearchLog.query)
                    .order_by(desc("search_count"))
                    .limit(10)
                )

                result_terms = await session.execute(stmt_terms)
                popular_terms = [
                    {
                        "term": row[0],
                        "count": row[1],
                    }
                    for row in result_terms
                ]

                return {
                    "total_searches": total_searches,
                    "unique_users": total_users,
                    "popular_terms": popular_terms,
                    "time_period": "last_24h",
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_from_db())

    except Exception as e:
        logger.error(f"Error getting search metrics: {str(e)}")
        return {"total_searches": 0, "error": str(e)}
