"""
Tác vụ dọn dẹp hệ thống

Module này cung cấp các tác vụ liên quan đến dọn dẹp hệ thống:
- Dọn dẹp file tạm thời
- Dọn dẹp log cũ
- Dọn dẹp dữ liệu không sử dụng
"""

import os
import datetime
import time
import shutil
import glob
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
    name="app.tasks.system.cleanup.cleanup_temp_files",
    queue="system",
)
def cleanup_temp_files(self, days_old: int = 1) -> Dict[str, Any]:
    """
    Dọn dẹp các file tạm thời.

    Args:
        days_old: Số ngày cũ (file cũ hơn số ngày này sẽ bị xóa)

    Returns:
        Dict chứa kết quả dọn dẹp
    """
    try:
        logger.info(f"Cleaning up temporary files older than {days_old} days")

        # Thời gian cũ nhất được giữ lại
        cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days_old)
        cutoff_timestamp = cutoff_time.timestamp()

        # Thư mục chứa file tạm
        temp_dirs = [
            os.path.join(settings.MEDIA_ROOT, "temp"),
            os.path.join(settings.MEDIA_ROOT, "uploads"),
        ]

        deleted_files = []
        total_size = 0

        for temp_dir in temp_dirs:
            # Kiểm tra thư mục tồn tại
            if not os.path.exists(temp_dir):
                continue

            # Duyệt qua tất cả file trong thư mục
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)

                    # Lấy thời gian sửa đổi của file
                    try:
                        file_mtime = os.path.getmtime(file_path)

                        # Nếu file cũ hơn cutoff time
                        if file_mtime < cutoff_timestamp:
                            # Lấy kích thước file
                            file_size = os.path.getsize(file_path)
                            total_size += file_size

                            # Xóa file
                            os.remove(file_path)

                            # Lưu thông tin
                            deleted_files.append(
                                {
                                    "path": file_path,
                                    "size": file_size,
                                    "mtime": datetime.datetime.fromtimestamp(
                                        file_mtime
                                    ).isoformat(),
                                }
                            )
                    except Exception as e:
                        logger.warning(f"Error processing file {file_path}: {str(e)}")

        # Kết quả
        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "days_old": days_old,
            "deleted_count": len(deleted_files),
            "total_size_bytes": total_size,
            "deleted_files": deleted_files[:100],  # Giới hạn số lượng file hiển thị
        }

        logger.info(
            f"Cleaned up {len(deleted_files)} temporary files ({total_size} bytes)"
        )
        return result

    except Exception as e:
        logger.error(f"Error cleaning up temporary files: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e),
        }


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.system.cleanup.cleanup_old_logs",
    queue="system",
)
def cleanup_old_logs(self, days_old: int = 30) -> Dict[str, Any]:
    """
    Dọn dẹp log cũ.

    Args:
        days_old: Số ngày cũ (log cũ hơn số ngày này sẽ bị xóa)

    Returns:
        Dict chứa kết quả dọn dẹp
    """
    try:
        logger.info(f"Cleaning up logs older than {days_old} days")

        # Thời gian cũ nhất để giữ lại
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_old)

        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "days_old": days_old,
            "deleted_count": {
                "request_logs": 0,
                "error_logs": 0,
                "auth_logs": 0,
                "health_checks": 0,
                "metrics": 0,
            },
        }

        # Dọn dẹp log từ database
        db_result = cleanup_db_logs(cutoff_date)
        result["deleted_count"].update(db_result)

        # Dọn dẹp file log
        file_result = cleanup_log_files(cutoff_date)
        result["deleted_count"]["log_files"] = file_result["deleted_count"]
        result["deleted_files"] = file_result["deleted_files"]

        logger.info(f"Cleaned up old logs: {result['deleted_count']}")
        return result

    except Exception as e:
        logger.error(f"Error cleaning up old logs: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e),
        }


def cleanup_db_logs(cutoff_date: datetime.datetime) -> Dict[str, int]:
    """
    Dọn dẹp log cũ từ database.

    Args:
        cutoff_date: Thời gian cắt (log cũ hơn thời gian này sẽ bị xóa)

    Returns:
        Dict chứa số lượng bản ghi đã xóa
    """
    try:
        result = {
            "request_logs": 0,
            "error_logs": 0,
            "auth_logs": 0,
            "health_checks": 0,
            "metrics": 0,
        }

        async def cleanup_logs():
            # Import các model
            from app.monitoring.models.request_log import RequestLog
            from app.logging.models.error_log import ErrorLog
            from app.security.models.auth_log import AuthLog
            from app.monitoring.models.health_check import HealthCheckResult
            from app.monitoring.models.metrics import (
                SystemMetrics,
                ApplicationMetrics,
                UserMetrics,
            )
            from sqlalchemy import delete

            async with async_session() as session:
                # Xóa request logs
                stmt = delete(RequestLog).where(RequestLog.timestamp < cutoff_date)
                result_request = await session.execute(stmt)
                result["request_logs"] = result_request.rowcount

                # Xóa error logs
                stmt = delete(ErrorLog).where(ErrorLog.timestamp < cutoff_date)
                result_error = await session.execute(stmt)
                result["error_logs"] = result_error.rowcount

                # Xóa auth logs
                stmt = delete(AuthLog).where(AuthLog.timestamp < cutoff_date)
                result_auth = await session.execute(stmt)
                result["auth_logs"] = result_auth.rowcount

                # Xóa health checks
                stmt = delete(HealthCheckResult).where(
                    HealthCheckResult.timestamp < cutoff_date
                )
                result_health = await session.execute(stmt)
                result["health_checks"] = result_health.rowcount

                # Xóa metrics
                stmt = delete(SystemMetrics).where(
                    SystemMetrics.timestamp < cutoff_date
                )
                result_metrics_sys = await session.execute(stmt)

                stmt = delete(ApplicationMetrics).where(
                    ApplicationMetrics.timestamp < cutoff_date
                )
                result_metrics_app = await session.execute(stmt)

                stmt = delete(UserMetrics).where(UserMetrics.timestamp < cutoff_date)
                result_metrics_user = await session.execute(stmt)

                result["metrics"] = (
                    result_metrics_sys.rowcount
                    + result_metrics_app.rowcount
                    + result_metrics_user.rowcount
                )

                # Commit changes
                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(cleanup_logs())

        return result

    except Exception as e:
        logger.error(f"Error cleaning up database logs: {str(e)}")
        return {
            "request_logs": 0,
            "error_logs": 0,
            "auth_logs": 0,
            "health_checks": 0,
            "metrics": 0,
        }


def cleanup_log_files(cutoff_date: datetime.datetime) -> Dict[str, Any]:
    """
    Dọn dẹp file log cũ.

    Args:
        cutoff_date: Thời gian cắt (file cũ hơn thời gian này sẽ bị xóa)

    Returns:
        Dict chứa kết quả dọn dẹp
    """
    try:
        # Thư mục log
        log_dir = settings.LOG_DIR

        # Định dạng tên file log
        log_pattern = os.path.join(log_dir, "*.log")

        deleted_files = []
        deleted_count = 0

        # Chuyển cutoff_date thành timestamp
        cutoff_timestamp = cutoff_date.timestamp()

        # Duyệt qua tất cả file log
        for log_file in glob.glob(log_pattern):
            # Lấy thời gian sửa đổi của file
            file_mtime = os.path.getmtime(log_file)

            # Nếu file cũ hơn cutoff date
            if file_mtime < cutoff_timestamp:
                # Lấy kích thước file
                file_size = os.path.getsize(log_file)

                # Xóa file
                os.remove(log_file)

                # Lưu thông tin
                deleted_files.append(
                    {
                        "path": log_file,
                        "size": file_size,
                        "mtime": datetime.datetime.fromtimestamp(
                            file_mtime
                        ).isoformat(),
                    }
                )

                deleted_count += 1

        return {
            "deleted_count": deleted_count,
            "deleted_files": deleted_files,
        }

    except Exception as e:
        logger.error(f"Error cleaning up log files: {str(e)}")
        return {
            "deleted_count": 0,
            "deleted_files": [],
        }


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.system.cleanup.cleanup_unused_data",
    queue="system",
)
def cleanup_unused_data(self) -> Dict[str, Any]:
    """
    Dọn dẹp dữ liệu không sử dụng.

    Returns:
        Dict chứa kết quả dọn dẹp
    """
    try:
        logger.info("Cleaning up unused data")

        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "deleted_count": {
                "orphaned_files": 0,
                "expired_tokens": 0,
                "abandoned_carts": 0,
                "inactive_users": 0,
            },
        }

        # Dọn dẹp file mồ côi (không có liên kết trong database)
        orphaned_result = cleanup_orphaned_files()
        result["deleted_count"]["orphaned_files"] = orphaned_result["deleted_count"]

        # Dọn dẹp token hết hạn
        token_result = cleanup_expired_tokens()
        result["deleted_count"]["expired_tokens"] = token_result["deleted_count"]

        # Dọn dẹp giỏ hàng bị bỏ quên
        cart_result = cleanup_abandoned_carts()
        result["deleted_count"]["abandoned_carts"] = cart_result["deleted_count"]

        # Vô hiệu hóa người dùng không hoạt động
        user_result = mark_inactive_users()
        result["deleted_count"]["inactive_users"] = user_result["marked_count"]

        logger.info(f"Cleaned up unused data: {result['deleted_count']}")
        return result

    except Exception as e:
        logger.error(f"Error cleaning up unused data: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e),
        }


def cleanup_orphaned_files() -> Dict[str, Any]:
    """
    Dọn dẹp các file mồ côi (không có liên kết trong database).

    Returns:
        Dict chứa kết quả dọn dẹp
    """
    try:
        # Các thư mục cần kiểm tra
        media_dirs = [
            os.path.join(settings.MEDIA_ROOT, "books"),
            os.path.join(settings.MEDIA_ROOT, "previews"),
            os.path.join(settings.MEDIA_ROOT, "thumbnails"),
        ]

        deleted_files = []
        deleted_count = 0

        # Lấy danh sách book_id từ database
        async def get_book_ids():
            from app.user_site.models.book import Book
            from sqlalchemy import select

            async with async_session() as session:
                # Lấy tất cả book_id
                stmt = select(Book.id)
                result = await session.execute(stmt)
                return [row[0] for row in result]

        # Chạy async task
        loop = asyncio.get_event_loop()
        valid_book_ids = loop.run_until_complete(get_book_ids())

        # Duyệt qua các thư mục media
        for media_dir in media_dirs:
            if not os.path.exists(media_dir):
                continue

            # Lấy danh sách thư mục con (thư mục theo book_id)
            for item in os.listdir(media_dir):
                item_path = os.path.join(media_dir, item)

                # Chỉ xử lý thư mục
                if os.path.isdir(item_path):
                    try:
                        # Kiểm tra xem book_id có tồn tại trong database không
                        book_id = int(item)
                        if book_id not in valid_book_ids:
                            # Lấy kích thước thư mục
                            dir_size = get_dir_size(item_path)

                            # Xóa thư mục
                            shutil.rmtree(item_path)

                            # Lưu thông tin
                            deleted_files.append(
                                {
                                    "path": item_path,
                                    "size": dir_size,
                                    "book_id": book_id,
                                }
                            )

                            deleted_count += 1
                    except ValueError:
                        # Bỏ qua nếu tên thư mục không phải số
                        pass

        return {
            "deleted_count": deleted_count,
            "deleted_files": deleted_files,
        }

    except Exception as e:
        logger.error(f"Error cleaning up orphaned files: {str(e)}")
        return {
            "deleted_count": 0,
            "deleted_files": [],
        }


def get_dir_size(path: str) -> int:
    """
    Tính tổng kích thước của thư mục.

    Args:
        path: Đường dẫn thư mục

    Returns:
        Kích thước thư mục (bytes)
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
    return total_size


def cleanup_expired_tokens() -> Dict[str, Any]:
    """
    Dọn dẹp các token hết hạn.

    Returns:
        Dict chứa kết quả dọn dẹp
    """
    try:

        async def cleanup_tokens():
            from app.security.models.token import Token
            from sqlalchemy import delete

            # Thời điểm hiện tại
            now = datetime.datetime.now()

            async with async_session() as session:
                # Xóa các token đã hết hạn
                stmt = delete(Token).where(Token.expires_at < now)
                result = await session.execute(stmt)
                deleted_count = result.rowcount

                # Commit changes
                await session.commit()

                return {
                    "deleted_count": deleted_count,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(cleanup_tokens())

    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {str(e)}")
        return {
            "deleted_count": 0,
        }


def cleanup_abandoned_carts() -> Dict[str, Any]:
    """
    Dọn dẹp các giỏ hàng bị bỏ quên.

    Returns:
        Dict chứa kết quả dọn dẹp
    """
    try:

        async def cleanup_carts():
            from app.user_site.models.cart import Cart
            from sqlalchemy import delete

            # Thời điểm cắt (30 ngày trước)
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=30)

            async with async_session() as session:
                # Xóa các giỏ hàng cũ
                stmt = delete(Cart).where(Cart.updated_at < cutoff_date)
                result = await session.execute(stmt)
                deleted_count = result.rowcount

                # Commit changes
                await session.commit()

                return {
                    "deleted_count": deleted_count,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(cleanup_carts())

    except Exception as e:
        logger.error(f"Error cleaning up abandoned carts: {str(e)}")
        return {
            "deleted_count": 0,
        }


def mark_inactive_users() -> Dict[str, Any]:
    """
    Đánh dấu người dùng không hoạt động.

    Returns:
        Dict chứa kết quả đánh dấu
    """
    try:

        async def mark_users():
            from app.user_site.models.user import User
            from app.security.models.login_history import LoginHistory
            from sqlalchemy import select, update, and_, or_

            # Thời điểm cắt (1 năm trước)
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=365)

            async with async_session() as session:
                # Lấy danh sách user_id có đăng nhập gần đây
                stmt_active = (
                    select(LoginHistory.user_id)
                    .where(LoginHistory.login_time >= cutoff_date)
                    .distinct()
                )
                result_active = await session.execute(stmt_active)
                active_user_ids = [row[0] for row in result_active]

                # Đánh dấu người dùng không hoạt động
                stmt = (
                    update(User)
                    .where(
                        and_(
                            (
                                User.id.notin_(active_user_ids)
                                if active_user_ids
                                else True
                            ),
                            User.created_at < cutoff_date,
                            User.is_active == True,
                        )
                    )
                    .values(is_active=False)
                )

                result = await session.execute(stmt)
                marked_count = result.rowcount

                # Commit changes
                await session.commit()

                return {
                    "marked_count": marked_count,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(mark_users())

    except Exception as e:
        logger.error(f"Error marking inactive users: {str(e)}")
        return {
            "marked_count": 0,
        }
