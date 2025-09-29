"""
Tác vụ bảo trì hệ thống

Module này cung cấp các tác vụ liên quan đến bảo trì hệ thống:
- Tối ưu hóa database
- Chỉ mục lại full-text search
- Phân tích dữ liệu
"""

import os
import datetime
import time
import subprocess
import psutil
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
    name="app.tasks.system.maintenance.optimize_database",
    queue="system",
)
def optimize_database(self) -> Dict[str, Any]:
    """
    Tối ưu hóa database: VACUUM, ANALYZE, REINDEX.

    Returns:
        Dict chứa kết quả tối ưu hóa
    """
    try:
        logger.info("Starting database optimization")

        # Kết quả tổng hợp
        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "success": True,
            "operations": {},
        }

        # Thực hiện VACUUM
        vacuum_result = run_vacuum()
        result["operations"]["vacuum"] = vacuum_result

        # Thực hiện ANALYZE
        analyze_result = run_analyze()
        result["operations"]["analyze"] = analyze_result

        # Thực hiện REINDEX
        reindex_result = run_reindex()
        result["operations"]["reindex"] = reindex_result

        # Kiểm tra kết quả
        if (
            not vacuum_result["success"]
            or not analyze_result["success"]
            or not reindex_result["success"]
        ):
            result["success"] = False

        logger.info(f"Database optimization completed: {result['success']}")
        return result

    except Exception as e:
        logger.error(f"Error optimizing database: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "success": False,
            "error": str(e),
        }


def run_vacuum() -> Dict[str, Any]:
    """
    Thực hiện VACUUM trên database.

    Returns:
        Dict chứa kết quả VACUUM
    """
    try:
        logger.info("Running VACUUM on database")
        start_time = time.time()

        # Lấy thông tin kết nối database từ settings
        db_host = settings.DB_HOST
        db_port = settings.DB_PORT
        db_name = settings.DB_NAME
        db_user = settings.DB_USER
        db_password = settings.DB_PASSWORD

        # Tạo command để chạy VACUUM
        vacuum_cmd = [
            "psql",
            f"--host={db_host}",
            f"--port={db_port}",
            f"--username={db_user}",
            f"--dbname={db_name}",
            "--command=VACUUM VERBOSE;",
        ]

        # Thiết lập biến môi trường cho mật khẩu
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        # Chạy command
        proc = subprocess.Popen(
            vacuum_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Đợi process hoàn thành
        stdout, stderr = proc.communicate()

        # Kiểm tra kết quả
        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"VACUUM failed with code {proc.returncode}: {stderr.decode('utf-8')}",
                "duration_seconds": time.time() - start_time,
            }

        # Xử lý output
        output = stdout.decode("utf-8")

        return {
            "success": True,
            "output": output,
            "duration_seconds": time.time() - start_time,
        }

    except Exception as e:
        logger.error(f"Error running VACUUM: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


def run_analyze() -> Dict[str, Any]:
    """
    Thực hiện ANALYZE trên database.

    Returns:
        Dict chứa kết quả ANALYZE
    """
    try:
        logger.info("Running ANALYZE on database")
        start_time = time.time()

        # Lấy thông tin kết nối database từ settings
        db_host = settings.DB_HOST
        db_port = settings.DB_PORT
        db_name = settings.DB_NAME
        db_user = settings.DB_USER
        db_password = settings.DB_PASSWORD

        # Tạo command để chạy ANALYZE
        analyze_cmd = [
            "psql",
            f"--host={db_host}",
            f"--port={db_port}",
            f"--username={db_user}",
            f"--dbname={db_name}",
            "--command=ANALYZE VERBOSE;",
        ]

        # Thiết lập biến môi trường cho mật khẩu
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        # Chạy command
        proc = subprocess.Popen(
            analyze_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Đợi process hoàn thành
        stdout, stderr = proc.communicate()

        # Kiểm tra kết quả
        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"ANALYZE failed with code {proc.returncode}: {stderr.decode('utf-8')}",
                "duration_seconds": time.time() - start_time,
            }

        # Xử lý output
        output = stdout.decode("utf-8")

        return {
            "success": True,
            "output": output,
            "duration_seconds": time.time() - start_time,
        }

    except Exception as e:
        logger.error(f"Error running ANALYZE: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


def run_reindex() -> Dict[str, Any]:
    """
    Thực hiện REINDEX trên database.

    Returns:
        Dict chứa kết quả REINDEX
    """
    try:
        logger.info("Running REINDEX on database")
        start_time = time.time()

        # Lấy thông tin kết nối database từ settings
        db_host = settings.DB_HOST
        db_port = settings.DB_PORT
        db_name = settings.DB_NAME
        db_user = settings.DB_USER
        db_password = settings.DB_PASSWORD

        # Tạo command để chạy REINDEX
        reindex_cmd = [
            "psql",
            f"--host={db_host}",
            f"--port={db_port}",
            f"--username={db_user}",
            f"--dbname={db_name}",
            "--command=REINDEX DATABASE VERBOSE;",
        ]

        # Thiết lập biến môi trường cho mật khẩu
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        # Chạy command
        proc = subprocess.Popen(
            reindex_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Đợi process hoàn thành
        stdout, stderr = proc.communicate()

        # Kiểm tra kết quả
        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"REINDEX failed with code {proc.returncode}: {stderr.decode('utf-8')}",
                "duration_seconds": time.time() - start_time,
            }

        # Xử lý output
        output = stdout.decode("utf-8")

        return {
            "success": True,
            "output": output,
            "duration_seconds": time.time() - start_time,
        }

    except Exception as e:
        logger.error(f"Error running REINDEX: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.system.maintenance.rebuild_search_index",
    queue="system",
)
def rebuild_search_index(self) -> Dict[str, Any]:
    """
    Xây dựng lại chỉ mục tìm kiếm full-text.

    Returns:
        Dict chứa kết quả xây dựng lại chỉ mục
    """
    try:
        logger.info("Starting search index rebuild")

        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "success": True,
            "indexes": {},
        }

        # Xây dựng lại chỉ mục cho sách
        books_result = rebuild_books_search_index()
        result["indexes"]["books"] = books_result

        # Xây dựng lại chỉ mục cho tác giả
        authors_result = rebuild_authors_search_index()
        result["indexes"]["authors"] = authors_result

        # Xây dựng lại chỉ mục cho nội dung sách
        content_result = rebuild_book_content_search_index()
        result["indexes"]["book_content"] = content_result

        # Kiểm tra kết quả
        if (
            not books_result["success"]
            or not authors_result["success"]
            or not content_result["success"]
        ):
            result["success"] = False

        logger.info(f"Search index rebuild completed: {result['success']}")
        return result

    except Exception as e:
        logger.error(f"Error rebuilding search index: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "success": False,
            "error": str(e),
        }


def rebuild_books_search_index() -> Dict[str, Any]:
    """
    Xây dựng lại chỉ mục tìm kiếm cho sách.

    Returns:
        Dict chứa kết quả xây dựng lại chỉ mục
    """
    try:
        start_time = time.time()

        async def rebuild_index():
            from app.user_site.models.book import Book
            from sqlalchemy import text

            async with async_session() as session:
                # Thực hiện truy vấn để xây dựng lại chỉ mục
                query = """
                UPDATE books SET search_vector = 
                setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(author_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(description, '')), 'C')
                """

                result = await session.execute(text(query))
                await session.commit()

                # Lấy số lượng sách
                count_query = "SELECT COUNT(*) FROM books"
                count_result = await session.execute(text(count_query))
                count = count_result.scalar()

                return {
                    "success": True,
                    "indexed_count": count,
                    "duration_seconds": time.time() - start_time,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(rebuild_index())

    except Exception as e:
        logger.error(f"Error rebuilding books search index: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "duration_seconds": (
                time.time() - start_time if "start_time" in locals() else 0
            ),
        }


def rebuild_authors_search_index() -> Dict[str, Any]:
    """
    Xây dựng lại chỉ mục tìm kiếm cho tác giả.

    Returns:
        Dict chứa kết quả xây dựng lại chỉ mục
    """
    try:
        start_time = time.time()

        async def rebuild_index():
            from app.user_site.models.author import Author
            from sqlalchemy import text

            async with async_session() as session:
                # Thực hiện truy vấn để xây dựng lại chỉ mục
                query = """
                UPDATE authors SET search_vector = 
                setweight(to_tsvector('english', COALESCE(name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(bio, '')), 'C')
                """

                result = await session.execute(text(query))
                await session.commit()

                # Lấy số lượng tác giả
                count_query = "SELECT COUNT(*) FROM authors"
                count_result = await session.execute(text(count_query))
                count = count_result.scalar()

                return {
                    "success": True,
                    "indexed_count": count,
                    "duration_seconds": time.time() - start_time,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(rebuild_index())

    except Exception as e:
        logger.error(f"Error rebuilding authors search index: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "duration_seconds": (
                time.time() - start_time if "start_time" in locals() else 0
            ),
        }


def rebuild_book_content_search_index() -> Dict[str, Any]:
    """
    Xây dựng lại chỉ mục tìm kiếm cho nội dung sách.

    Returns:
        Dict chứa kết quả xây dựng lại chỉ mục
    """
    try:
        start_time = time.time()

        async def rebuild_index():
            from app.user_site.models.book_content import BookContent
            from sqlalchemy import text

            async with async_session() as session:
                # Thực hiện truy vấn để xây dựng lại chỉ mục
                query = """
                UPDATE book_contents SET search_vector = 
                to_tsvector('english', COALESCE(content, ''))
                """

                result = await session.execute(text(query))
                await session.commit()

                # Lấy số lượng nội dung
                count_query = "SELECT COUNT(*) FROM book_contents"
                count_result = await session.execute(text(count_query))
                count = count_result.scalar()

                return {
                    "success": True,
                    "indexed_count": count,
                    "duration_seconds": time.time() - start_time,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(rebuild_index())

    except Exception as e:
        logger.error(f"Error rebuilding book content search index: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "duration_seconds": (
                time.time() - start_time if "start_time" in locals() else 0
            ),
        }


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.system.maintenance.analyze_statistics",
    queue="system",
)
def analyze_statistics(self) -> Dict[str, Any]:
    """
    Phân tích thống kê hệ thống.

    Returns:
        Dict chứa kết quả phân tích
    """
    try:
        logger.info("Starting statistics analysis")

        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "success": True,
            "statistics": {},
        }

        # Phân tích thống kê database
        db_stats = analyze_database_stats()
        result["statistics"]["database"] = db_stats

        # Phân tích thống kê storage
        storage_stats = analyze_storage_stats()
        result["statistics"]["storage"] = storage_stats

        # Phân tích thống kê người dùng
        user_stats = analyze_user_stats()
        result["statistics"]["users"] = user_stats

        # Kiểm tra kết quả
        if (
            not db_stats["success"]
            or not storage_stats["success"]
            or not user_stats["success"]
        ):
            result["success"] = False

        # Lưu thống kê vào database
        save_statistics(result)

        logger.info(f"Statistics analysis completed: {result['success']}")
        return result

    except Exception as e:
        logger.error(f"Error analyzing statistics: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "success": False,
            "error": str(e),
        }


def analyze_database_stats() -> Dict[str, Any]:
    """
    Phân tích thống kê database.

    Returns:
        Dict chứa thống kê database
    """
    try:

        async def get_stats():
            from sqlalchemy import text

            async with async_session() as session:
                # Lấy kích thước database
                size_query = """
                SELECT pg_size_pretty(pg_database_size(current_database())) as size,
                       pg_database_size(current_database()) as bytes
                """
                size_result = await session.execute(text(size_query))
                size_row = size_result.fetchone()
                db_size = size_row[0]
                db_size_bytes = size_row[1]

                # Lấy thống kê bảng
                tables_query = """
                SELECT relname as table_name,
                       pg_size_pretty(pg_total_relation_size(C.oid)) as total_size,
                       pg_total_relation_size(C.oid) as bytes,
                       pg_size_pretty(pg_relation_size(C.oid)) as table_size,
                       pg_relation_size(C.oid) as table_bytes,
                       pg_size_pretty(pg_total_relation_size(C.oid) - pg_relation_size(C.oid)) as index_size,
                       pg_total_relation_size(C.oid) - pg_relation_size(C.oid) as index_bytes,
                       reltuples as row_estimate
                FROM pg_class C
                LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace)
                WHERE nspname NOT IN ('pg_catalog', 'information_schema')
                  AND C.relkind = 'r'
                ORDER BY pg_total_relation_size(C.oid) DESC
                LIMIT 20
                """
                tables_result = await session.execute(text(tables_query))
                tables = [dict(row._mapping) for row in tables_result]

                # Lấy thông tin các chỉ mục lớn nhất
                indexes_query = """
                SELECT
                    i.relname as index_name,
                    t.relname as table_name,
                    pg_size_pretty(pg_relation_size(i.oid)) as index_size,
                    pg_relation_size(i.oid) as index_bytes
                FROM pg_index x
                JOIN pg_class i ON i.oid = x.indexrelid
                JOIN pg_class t ON t.oid = x.indrelid
                JOIN pg_namespace n ON n.oid = i.relnamespace
                WHERE nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY pg_relation_size(i.oid) DESC
                LIMIT 10
                """
                indexes_result = await session.execute(text(indexes_query))
                indexes = [dict(row._mapping) for row in indexes_result]

                # Lấy số lượng bản ghi trong các bảng chính
                tables_count_query = """
                SELECT 'books' as table_name, COUNT(*) as count FROM books
                UNION ALL
                SELECT 'users' as table_name, COUNT(*) as count FROM users
                UNION ALL
                SELECT 'reading_sessions' as table_name, COUNT(*) as count FROM reading_sessions
                UNION ALL
                SELECT 'authors' as table_name, COUNT(*) as count FROM authors
                """
                tables_count_result = await session.execute(text(tables_count_query))
                tables_count = [dict(row._mapping) for row in tables_count_result]

                return {
                    "success": True,
                    "database_size": db_size,
                    "database_size_bytes": db_size_bytes,
                    "tables": tables,
                    "indexes": indexes,
                    "record_counts": tables_count,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_stats())

    except Exception as e:
        logger.error(f"Error analyzing database statistics: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


def analyze_storage_stats() -> Dict[str, Any]:
    """
    Phân tích thống kê lưu trữ.

    Returns:
        Dict chứa thống kê lưu trữ
    """
    try:
        # Thống kê các thư mục
        media_root = settings.MEDIA_ROOT
        dirs_to_analyze = [
            os.path.join(media_root, "books"),
            os.path.join(media_root, "previews"),
            os.path.join(media_root, "thumbnails"),
            os.path.join(media_root, "temp"),
            os.path.join(settings.BACKUP_DIR, "database"),
            os.path.join(settings.BACKUP_DIR, "files"),
        ]

        dir_stats = []
        total_size = 0
        total_files = 0

        # Phân tích từng thư mục
        for directory in dirs_to_analyze:
            if os.path.exists(directory):
                dir_size, file_count = get_directory_size(directory)
                total_size += dir_size
                total_files += file_count

                dir_stats.append(
                    {
                        "path": directory,
                        "size_bytes": dir_size,
                        "size_pretty": format_size(dir_size),
                        "file_count": file_count,
                    }
                )

        # Thống kê disk
        disk_usage = psutil.disk_usage(media_root)

        return {
            "success": True,
            "total_size_bytes": total_size,
            "total_size_pretty": format_size(total_size),
            "total_files": total_files,
            "directories": dir_stats,
            "disk_usage": {
                "total": disk_usage.total,
                "used": disk_usage.used,
                "free": disk_usage.free,
                "percent": disk_usage.percent,
                "total_pretty": format_size(disk_usage.total),
                "used_pretty": format_size(disk_usage.used),
                "free_pretty": format_size(disk_usage.free),
            },
        }

    except Exception as e:
        logger.error(f"Error analyzing storage statistics: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


def get_directory_size(path: str) -> tuple:
    """
    Tính kích thước và số lượng file trong thư mục.

    Args:
        path: Đường dẫn thư mục

    Returns:
        Tuple (kích thước (bytes), số lượng file)
    """
    total_size = 0
    file_count = 0

    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
                file_count += 1

    return total_size, file_count


def format_size(size_bytes: int) -> str:
    """
    Định dạng kích thước thành chuỗi dễ đọc.

    Args:
        size_bytes: Kích thước (bytes)

    Returns:
        Chuỗi định dạng kích thước
    """
    # Đơn vị
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0

    # Chuyển đổi đơn vị
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.2f} {units[unit_index]}"


def analyze_user_stats() -> Dict[str, Any]:
    """
    Phân tích thống kê người dùng.

    Returns:
        Dict chứa thống kê người dùng
    """
    try:

        async def get_stats():
            from sqlalchemy import text

            async with async_session() as session:
                # Tổng số người dùng và phân bố
                users_query = """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN is_active = true THEN 1 ELSE 0 END) as active,
                       SUM(CASE WHEN is_admin = true THEN 1 ELSE 0 END) as admins,
                       SUM(CASE WHEN created_at >= NOW() - INTERVAL '30 days' THEN 1 ELSE 0 END) as new_last_30d
                FROM users
                """
                users_result = await session.execute(text(users_query))
                users_stats = dict(users_result.fetchone()._mapping)

                # Thống kê phiên đọc
                reading_query = """
                SELECT COUNT(*) as total_sessions,
                       SUM(duration_minutes) as total_minutes,
                       COUNT(DISTINCT user_id) as unique_readers,
                       COUNT(DISTINCT book_id) as unique_books,
                       AVG(duration_minutes) as avg_duration
                FROM reading_sessions
                WHERE start_time >= NOW() - INTERVAL '30 days'
                """
                reading_result = await session.execute(text(reading_query))
                reading_stats = dict(reading_result.fetchone()._mapping)

                # Top sách được đọc nhiều nhất
                popular_books_query = """
                SELECT b.id, b.title, COUNT(rs.id) as session_count
                FROM reading_sessions rs
                JOIN books b ON rs.book_id = b.id
                WHERE rs.start_time >= NOW() - INTERVAL '30 days'
                GROUP BY b.id, b.title
                ORDER BY session_count DESC
                LIMIT 10
                """
                popular_books_result = await session.execute(text(popular_books_query))
                popular_books = [dict(row._mapping) for row in popular_books_result]

                # Thống kê đăng nhập
                login_query = """
                SELECT COUNT(*) as total_logins,
                       COUNT(DISTINCT user_id) as unique_users,
                       COUNT(CASE WHEN login_time >= NOW() - INTERVAL '7 days' THEN 1 ELSE NULL END) as logins_last_7d
                FROM login_history
                WHERE login_time >= NOW() - INTERVAL '30 days'
                """
                login_result = await session.execute(text(login_query))
                login_stats = dict(login_result.fetchone()._mapping)

                return {
                    "success": True,
                    "users": users_stats,
                    "reading": reading_stats,
                    "popular_books": popular_books,
                    "logins": login_stats,
                }

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_stats())

    except Exception as e:
        logger.error(f"Error analyzing user statistics: {str(e)}")
        return {
            "success": False,
            "error": str(e),
        }


def save_statistics(stats: Dict[str, Any]) -> None:
    """
    Lưu thống kê vào database.

    Args:
        stats: Thống kê hệ thống
    """
    try:

        async def save_to_db():
            from app.monitoring.models.statistics import SystemStatistics
            import json

            async with async_session() as session:
                # Lưu thống kê
                system_stats = SystemStatistics(
                    timestamp=datetime.datetime.now(),
                    details=json.dumps(stats),
                )

                session.add(system_stats)
                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(save_to_db())

    except Exception as e:
        logger.error(f"Error saving statistics: {str(e)}")
