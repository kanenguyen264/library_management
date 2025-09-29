"""
Module tasks - Quản lý các tác vụ nền và lập lịch

Module này cung cấp các tác vụ nền cho ứng dụng, bao gồm:
- Các tác vụ xử lý sách và gợi ý
- Gửi email
- Giám sát hệ thống
- Tác vụ bảo trì và sao lưu
"""

# Import common modules needed by most tasks
import asyncio
import datetime
from typing import Dict, Any, List, Optional

# Import application-specific modules
from app.core.config import get_settings
from app.logging.setup import get_logger
from app.tasks.worker import celery_app
from app.tasks.scheduler import setup_scheduler, register_scheduled_task
from app.tasks.base_task import BaseTask
from app.core.db import async_session

# Import các submodule
from app.tasks import book
from app.tasks import email
from app.tasks import monitoring
from app.tasks import system

# Danh sách các task thường dùng để public API
from app.tasks.book.recommendations import (
    generate_recommendations,
    generate_trending_books,
)
from app.tasks.book.processing import process_book_upload, generate_book_preview
from app.tasks.email.send_email import (
    send_welcome_email,
    send_notification_email,
    send_password_reset_email,
)
from app.tasks.system.backups import create_database_backup
from app.tasks.system.cleanup import clean_old_files, clean_expired_tokens

# Khởi tạo schedule khi import
setup_scheduler()

# Common settings and loggers used by tasks
settings = get_settings()
logger = get_logger(__name__)

__all__ = [
    "celery_app",
    "setup_scheduler",
    "register_scheduled_task",
    "BaseTask",
    "book",
    "email",
    "monitoring",
    "system",
    # Common tasks
    "generate_recommendations",
    "generate_trending_books",
    "process_book_upload",
    "generate_book_preview",
    "send_welcome_email",
    "send_notification_email",
    "send_password_reset_email",
    "create_database_backup",
    "clean_old_files",
    "clean_expired_tokens",
]
