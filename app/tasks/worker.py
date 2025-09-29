"""
Khởi tạo Celery worker

Module này thiết lập Celery worker để xử lý các tác vụ bất đồng bộ.
"""

import os
import sys
from celery import Celery
from celery.signals import worker_init, worker_ready, worker_shutdown
from celery.schedules import crontab

from app.core.config import get_settings
from app.logging.setup import get_logger, setup_celery_logging
from app.tasks.base_task import BaseTask

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)

# Thiết lập URL kết nối Redis
redis_url = settings.get_redis_url()

# Khởi tạo Celery
celery_app = Celery(
    "app", broker=redis_url, backend=redis_url, broker_connection_retry_on_startup=True
)

# Thiết lập cấu hình
celery_app.conf.update(
    # Task routes - phân chia các task vào các queue khác nhau
    task_routes={
        "app.tasks.book.*": {"queue": "books"},
        "app.tasks.email.*": {"queue": "emails"},
        "app.tasks.monitoring.*": {"queue": "monitoring"},
        "app.tasks.system.*": {"queue": "system"},
    },
    # Tùy chỉnh serializer
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone và enable UTC
    enable_utc=True,
    timezone="Asia/Ho_Chi_Minh",
    # Cấu hình worker - adjust dựa trên cấu hình autoscaling
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    worker_max_tasks_per_child=1000,
    # Task default
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    # Result backend
    result_expires=3600,  # 1 giờ
    result_persistent=True,
    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    # Logging
    worker_hijack_root_logger=False,
    worker_log_color=True if not settings.is_production() else False,
    # Task hard time limit
    task_time_limit=3600,  # 1 giờ
    task_soft_time_limit=1800,  # 30 phút
    # Thêm timestamp vào tên task
    worker_proc_alive_timeout=30,
    # Security settings
    task_create_missing_queues=True,
    # Bật các tính năng mới (depends on Celery version)
    task_remote_tracebacks=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
)

# Thiết lập task base
celery_app.Task = BaseTask


@worker_init.connect
def worker_init_handler(sender=None, conf=None, **kwargs):
    """
    Xử lý sự kiện worker khởi động.

    Args:
        sender: Worker sender
        conf: Worker config
        **kwargs: Arguments bổ sung
    """
    # Thiết lập logging cho Celery
    setup_celery_logging()

    # Ghi log
    logger.info(f"Celery worker initializing. Queues: {sender.queues}")

    # Khởi tạo kết nối tới database
    # Import động ở đây để tránh circular imports
    from app.db.session import engine, Base

    try:
        # Khởi tạo kết nối
        logger.info("Initializing database connection for worker")
        with engine.begin() as conn:
            conn.execute("SELECT 1")
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}")

    # Khởi tạo Redis connection pool
    logger.info("Initializing Redis connection for worker")


@worker_ready.connect
def worker_ready_handler(**kwargs):
    """
    Xử lý sự kiện worker sẵn sàng.

    Args:
        **kwargs: Arguments
    """
    logger.info("Celery worker is ready and waiting for tasks")

    # Có thể thêm code để báo hiệu worker đã sẵn sàng


@worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    """
    Xử lý sự kiện worker đóng.

    Args:
        **kwargs: Arguments
    """
    logger.info("Celery worker shutting down")

    # Đóng các kết nối
    from app.db.session import engine

    try:
        logger.info("Closing database connections")
        engine.dispose()
    except Exception as e:
        logger.error(f"Error closing database connections: {str(e)}")


def start_worker(queue_names="default", concurrency=None, loglevel="INFO"):
    """
    Khởi động worker từ code (thay vì command line).

    Args:
        queue_names: Danh sách queue phân tách bởi dấu phẩy
        concurrency: Số lượng worker process
        loglevel: Log level
    """
    # Thiết lập logging
    setup_celery_logging()

    # Thiết lập concurrency
    if concurrency is None:
        import multiprocessing

        concurrency = multiprocessing.cpu_count()

    # Command line arguments
    argv = [
        "worker",
        "--queues",
        queue_names,
        "--concurrency",
        str(concurrency),
        "--loglevel",
        loglevel,
    ]

    # Nếu là môi trường production, thêm tham số cho daemon
    if settings.is_production():
        argv.extend(
            [
                "--detach",  # Chạy nền
                "--logfile",
                "logs/celery_%n.log",  # File log
                "--pidfile",
                "pids/celery_%n.pid",  # File pid
            ]
        )

    # Khởi động worker
    celery_app.worker_main(argv)


if __name__ == "__main__":
    # Được gọi khi chạy trực tiếp file này
    start_worker()
