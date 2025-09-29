"""
Scheduler cho các tác vụ định kỳ

Module này thiết lập lịch tự động chạy các tác vụ theo định kỳ.
"""

import os
import json
import datetime
import functools
from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

from celery.schedules import crontab
from app.core.config import get_settings
from app.logging.setup import get_logger

# Import worker để tránh circular imports
from app.tasks.worker import celery_app

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)


class ScheduleType(str, Enum):
    """Loại lịch."""

    CRONTAB = "crontab"
    INTERVAL = "interval"
    ONE_TIME = "one_time"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class TaskSchedule:
    """
    Lịch chạy task.
    """

    task: str
    schedule_type: ScheduleType
    enabled: bool = True
    args: List = field(default_factory=list)
    kwargs: Dict = field(default_factory=dict)
    options: Dict = field(default_factory=dict)
    name: Optional[str] = None
    description: Optional[str] = None

    # Cho crontab
    minute: Union[str, int, List[int]] = "*"
    hour: Union[str, int, List[int]] = "*"
    day_of_week: Union[str, int, List[int]] = "*"
    day_of_month: Union[str, int, List[int]] = "*"
    month_of_year: Union[str, int, List[int]] = "*"

    # Cho interval
    seconds: Optional[int] = None
    minutes: Optional[int] = None
    hours: Optional[int] = None
    days: Optional[int] = None

    # Cho one_time
    start_time: Optional[datetime.datetime] = None

    def get_schedule(self) -> Any:
        """
        Lấy đối tượng schedule cho celery.

        Returns:
            Celery schedule object
        """
        if self.schedule_type == ScheduleType.CRONTAB:
            return crontab(
                minute=self.minute,
                hour=self.hour,
                day_of_week=self.day_of_week,
                day_of_month=self.day_of_month,
                month_of_year=self.month_of_year,
            )
        elif self.schedule_type == ScheduleType.INTERVAL:
            from celery.schedules import schedule

            # Tính tổng số giây
            total_seconds = 0
            if self.seconds:
                total_seconds += self.seconds
            if self.minutes:
                total_seconds += self.minutes * 60
            if self.hours:
                total_seconds += self.hours * 3600
            if self.days:
                total_seconds += self.days * 86400

            return schedule(total_seconds)
        elif self.schedule_type == ScheduleType.ONE_TIME:
            # One-time schedule using ETA
            self.options["eta"] = self.start_time
            return None
        elif self.schedule_type == ScheduleType.DAILY:
            # Daily schedule using crontab
            return crontab(minute=self.minute, hour=self.hour)
        elif self.schedule_type == ScheduleType.WEEKLY:
            # Weekly schedule using crontab
            return crontab(
                minute=self.minute, hour=self.hour, day_of_week=self.day_of_week
            )
        elif self.schedule_type == ScheduleType.MONTHLY:
            # Monthly schedule using crontab
            return crontab(
                minute=self.minute, hour=self.hour, day_of_month=self.day_of_month
            )
        else:
            raise ValueError(f"Không hỗ trợ loại lịch: {self.schedule_type}")


# Danh sách các lịch task
_task_schedules: List[TaskSchedule] = []


def register_scheduled_task(
    task: str,
    schedule_type: ScheduleType,
    name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: bool = True,
    **kwargs,
) -> TaskSchedule:
    """
    Đăng ký một task chạy theo lịch.

    Args:
        task: Tên task
        schedule_type: Loại lịch
        name: Tên lịch
        description: Mô tả
        enabled: Trạng thái bật/tắt
        **kwargs: Các tham số khác cho TaskSchedule

    Returns:
        TaskSchedule vừa tạo
    """
    # Tạo task schedule
    task_schedule = TaskSchedule(
        task=task,
        schedule_type=schedule_type,
        name=name,
        description=description,
        enabled=enabled,
        **kwargs,
    )

    # Thêm vào danh sách
    _task_schedules.append(task_schedule)

    return task_schedule


def get_schedule_tasks() -> List[Dict]:
    """
    Lấy danh sách các lịch task.

    Returns:
        Danh sách dict mô tả các lịch
    """
    return [asdict(task) for task in _task_schedules]


def enable_schedule(name: str) -> bool:
    """
    Bật lịch theo tên.

    Args:
        name: Tên lịch

    Returns:
        True nếu thành công
    """
    for task in _task_schedules:
        if task.name == name:
            task.enabled = True
            return True
    return False


def disable_schedule(name: str) -> bool:
    """
    Tắt lịch theo tên.

    Args:
        name: Tên lịch

    Returns:
        True nếu thành công
    """
    for task in _task_schedules:
        if task.name == name:
            task.enabled = False
            return True
    return False


def setup_scheduler() -> None:
    """
    Thiết lập scheduler.
    """
    # Khởi tạo tác vụ mặc định
    register_default_tasks()

    # Convert các task schedule thành beat schedule
    beat_schedule = {}

    for task_schedule in _task_schedules:
        if not task_schedule.enabled:
            continue

        if task_schedule.schedule_type == ScheduleType.ONE_TIME:
            # Không cần thêm vào beat_schedule, sẽ được lên lịch riêng
            logger.info(f"Scheduling one-time task: {task_schedule.task}")

            # Apply task với ETA
            celery_app.send_task(
                task_schedule.task,
                args=task_schedule.args,
                kwargs=task_schedule.kwargs,
                **task_schedule.options,
            )
        else:
            # Thêm vào beat_schedule
            schedule_key = (
                task_schedule.name or f"{task_schedule.task}_{id(task_schedule)}"
            )

            beat_schedule[schedule_key] = {
                "task": task_schedule.task,
                "schedule": task_schedule.get_schedule(),
                "args": task_schedule.args,
                "kwargs": task_schedule.kwargs,
                "options": task_schedule.options,
            }

    # Cập nhật beat_schedule của celery
    celery_app.conf.beat_schedule = beat_schedule

    logger.info(f"Scheduler setup complete. {len(beat_schedule)} tasks scheduled.")


def register_default_tasks() -> None:
    """
    Đăng ký các tác vụ mặc định.
    """
    # Tác vụ giám sát - Health check (5 phút/lần)
    register_scheduled_task(
        task="app.tasks.monitoring.health_check.check_system_health",
        schedule_type=ScheduleType.INTERVAL,
        minutes=5,
        name="health_check_system",
        description="Kiểm tra sức khỏe hệ thống mỗi 5 phút",
        options={"queue": "monitoring"},
    )

    # Tác vụ giám sát - Log metrics (mỗi giờ)
    register_scheduled_task(
        task="app.tasks.monitoring.metrics.log_system_metrics",
        schedule_type=ScheduleType.HOURLY,
        name="log_hourly_metrics",
        description="Ghi lại metrics hệ thống mỗi giờ",
        options={"queue": "monitoring"},
    )

    # Tác vụ dọn dẹp - Xóa file tạm (mỗi ngày lúc 1 giờ sáng)
    register_scheduled_task(
        task="app.tasks.system.cleanup.clean_temporary_files",
        schedule_type=ScheduleType.DAILY,
        hour=1,
        minute=0,
        name="daily_temp_cleanup",
        description="Dọn dẹp file tạm mỗi ngày lúc 1 giờ sáng",
        options={"queue": "system"},
    )

    # Tác vụ dọn dẹp - Xóa token hết hạn (mỗi ngày lúc 2 giờ sáng)
    register_scheduled_task(
        task="app.tasks.system.cleanup.clean_expired_tokens",
        schedule_type=ScheduleType.DAILY,
        hour=2,
        minute=0,
        name="daily_token_cleanup",
        description="Dọn dẹp token hết hạn mỗi ngày lúc 2 giờ sáng",
        options={"queue": "system"},
    )

    # Tác vụ sao lưu - Tạo backup (mỗi ngày lúc 3 giờ sáng)
    register_scheduled_task(
        task="app.tasks.system.backups.create_database_backup",
        schedule_type=ScheduleType.DAILY,
        hour=3,
        minute=0,
        name="daily_database_backup",
        description="Tạo backup cơ sở dữ liệu mỗi ngày lúc 3 giờ sáng",
        options={"queue": "system"},
    )

    # Tác vụ phân tích sách - Phân tích dữ liệu (mỗi tuần vào Chủ Nhật lúc 4 giờ sáng)
    register_scheduled_task(
        task="app.tasks.book.analytics.analyze_reading_trends",
        schedule_type=ScheduleType.WEEKLY,
        day_of_week=0,  # 0 = Chủ Nhật, 6 = Thứ Bảy
        hour=4,
        minute=0,
        name="weekly_reading_analytics",
        description="Phân tích xu hướng đọc sách hàng tuần vào Chủ Nhật lúc 4 giờ sáng",
        options={"queue": "books"},
    )

    # Tác vụ gợi ý sách - Cập nhật gợi ý (mỗi ngày lúc 5 giờ sáng)
    register_scheduled_task(
        task="app.tasks.book.recommendations.generate_recommendations",
        schedule_type=ScheduleType.DAILY,
        hour=5,
        minute=0,
        name="daily_recommendations_update",
        description="Cập nhật gợi ý sách mỗi ngày lúc 5 giờ sáng",
        options={"queue": "books"},
    )


def scheduled_task(
    schedule_type: ScheduleType,
    name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: bool = True,
    **kwargs,
) -> Callable:
    """
    Decorator để đăng ký task có lịch.

    Args:
        schedule_type: Loại lịch
        name: Tên lịch
        description: Mô tả
        enabled: Trạng thái bật/tắt
        **kwargs: Các tham số khác cho TaskSchedule

    Returns:
        Decorator
    """

    def decorator(func):
        # Lấy task path
        task_path = f"{func.__module__}.{func.__name__}"

        # Đăng ký task
        register_scheduled_task(
            task=task_path,
            schedule_type=schedule_type,
            name=name or func.__name__,
            description=description or func.__doc__,
            enabled=enabled,
            **kwargs,
        )

        # Không thay đổi function
        return func

    return decorator
