"""
Tác vụ kiểm tra sức khỏe hệ thống

Module này cung cấp các tác vụ liên quan đến kiểm tra sức khỏe:
- Kiểm tra kết nối database
- Kiểm tra các dịch vụ phụ thuộc
- Kiểm tra trạng thái Celery workers
"""

import datetime
import time
import socket
import os
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
    name="app.tasks.monitoring.health_check.check_system_health",
    queue="monitoring",
)
def check_system_health(self) -> Dict[str, Any]:
    """
    Kiểm tra sức khỏe tổng thể của hệ thống.

    Returns:
        Dict chứa kết quả kiểm tra
    """
    try:
        logger.info("Running system health check")

        start_time = time.time()

        # 1. Kiểm tra database
        db_status = check_database_connection()

        # 2. Kiểm tra Redis
        redis_status = check_redis_connection()

        # 3. Kiểm tra Celery workers
        celery_status = check_celery_workers()

        # 4. Kiểm tra storage
        storage_status = check_storage_health()

        # 5. Kiểm tra tài nguyên hệ thống
        system_resources = check_system_resources()

        # Kết quả tổng hợp
        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "execution_time": time.time() - start_time,
            "overall_status": "healthy",
            "checks": {
                "database": db_status,
                "redis": redis_status,
                "celery": celery_status,
                "storage": storage_status,
                "system_resources": system_resources,
            },
        }

        # Xác định trạng thái tổng thể
        if any(check.get("status") == "error" for check in result["checks"].values()):
            result["overall_status"] = "unhealthy"
        elif any(
            check.get("status") == "warning" for check in result["checks"].values()
        ):
            result["overall_status"] = "degraded"

        # Lưu kết quả kiểm tra vào database
        save_health_check_result(result)

        # Gửi cảnh báo nếu cần
        if result["overall_status"] != "healthy":
            send_health_alert(result)

        return result

    except Exception as e:
        logger.error(f"Error during system health check: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "overall_status": "error",
            "error": str(e),
        }


def check_database_connection() -> Dict[str, Any]:
    """
    Kiểm tra kết nối đến database.

    Returns:
        Dict chứa kết quả kiểm tra database
    """
    try:
        start_time = time.time()

        async def check_db():
            from sqlalchemy import text
            from app.core.db import get_session

            async with get_session() as session:
                # Thực hiện truy vấn đơn giản
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1

        # Chạy async task
        loop = asyncio.get_event_loop()
        is_connected = loop.run_until_complete(check_db())

        response_time = time.time() - start_time

        if is_connected:
            status = "healthy" if response_time < 0.5 else "warning"
            return {
                "status": status,
                "response_time": response_time,
                "message": f"Database connection successful (response time: {response_time:.3f}s)",
            }
        else:
            return {
                "status": "error",
                "response_time": response_time,
                "message": "Database connection failed",
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Database connection check failed: {str(e)}",
        }


def check_redis_connection() -> Dict[str, Any]:
    """
    Kiểm tra kết nối đến Redis.

    Returns:
        Dict chứa kết quả kiểm tra Redis
    """
    try:
        start_time = time.time()

        import redis

        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            socket_timeout=5,
        )

        # Thực hiện ping
        ping_result = redis_client.ping()
        response_time = time.time() - start_time

        if ping_result:
            status = "healthy" if response_time < 0.2 else "warning"
            return {
                "status": status,
                "response_time": response_time,
                "message": f"Redis connection successful (response time: {response_time:.3f}s)",
            }
        else:
            return {
                "status": "error",
                "response_time": response_time,
                "message": "Redis ping failed",
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Redis connection check failed: {str(e)}",
        }


def check_celery_workers() -> Dict[str, Any]:
    """
    Kiểm tra trạng thái các Celery workers.

    Returns:
        Dict chứa kết quả kiểm tra Celery
    """
    try:
        # Lấy thông tin worker từ Celery Inspect
        inspector = celery_app.control.inspect()
        active_workers = inspector.active_queues()

        if not active_workers:
            return {
                "status": "error",
                "message": "No active Celery workers found",
                "workers": [],
            }

        # Kiểm tra mỗi worker
        workers_info = []
        expected_queues = [
            "books",
            "emails",
            "recommendations",
            "monitoring",
            "default",
        ]
        missing_queues = expected_queues.copy()

        for worker_name, queues in active_workers.items():
            queue_names = [q["name"] for q in queues]

            # Cập nhật danh sách queue còn thiếu
            for queue in queue_names:
                if queue in missing_queues:
                    missing_queues.remove(queue)

            workers_info.append(
                {
                    "name": worker_name,
                    "queues": queue_names,
                    "status": "healthy",
                }
            )

        result = {
            "status": "healthy",
            "workers": workers_info,
            "active_worker_count": len(workers_info),
        }

        # Kiểm tra xem có queue nào không được phục vụ không
        if missing_queues:
            result["status"] = "warning"
            result["message"] = (
                f"Missing workers for queues: {', '.join(missing_queues)}"
            )

        return result

    except Exception as e:
        return {
            "status": "error",
            "message": f"Celery worker check failed: {str(e)}",
            "workers": [],
        }


def check_storage_health() -> Dict[str, Any]:
    """
    Kiểm tra trạng thái lưu trữ.

    Returns:
        Dict chứa kết quả kiểm tra storage
    """
    try:
        # Kiểm tra các thư mục chính
        media_root = settings.MEDIA_ROOT
        storage_paths = [
            os.path.join(media_root, "books"),
            os.path.join(media_root, "previews"),
            os.path.join(media_root, "thumbnails"),
            os.path.join(media_root, "temp"),
        ]

        storage_results = []

        for path in storage_paths:
            # Kiểm tra path tồn tại
            exists = os.path.exists(path)

            # Kiểm tra quyền ghi (thử tạo file tạm)
            writable = False
            if exists:
                try:
                    test_file = os.path.join(path, ".health_check_test")
                    with open(test_file, "w") as f:
                        f.write("test")
                    os.remove(test_file)
                    writable = True
                except:
                    writable = False

            storage_results.append(
                {
                    "path": path,
                    "exists": exists,
                    "writable": writable,
                    "status": "healthy" if (exists and writable) else "error",
                }
            )

        # Kiểm tra không gian disk
        disk_usage = psutil.disk_usage(media_root)
        disk_percent = disk_usage.percent
        disk_status = "healthy"

        if disk_percent > 90:
            disk_status = "error"
        elif disk_percent > 75:
            disk_status = "warning"

        # Tổng hợp kết quả
        result = {
            "status": "healthy",
            "storage_paths": storage_results,
            "disk_usage": {
                "total": disk_usage.total,
                "used": disk_usage.used,
                "free": disk_usage.free,
                "percent": disk_percent,
                "status": disk_status,
            },
        }

        # Cập nhật trạng thái tổng thể
        if (
            any(item["status"] == "error" for item in storage_results)
            or disk_status == "error"
        ):
            result["status"] = "error"
        elif (
            any(item["status"] == "warning" for item in storage_results)
            or disk_status == "warning"
        ):
            result["status"] = "warning"

        return result

    except Exception as e:
        return {
            "status": "error",
            "message": f"Storage health check failed: {str(e)}",
        }


def check_system_resources() -> Dict[str, Any]:
    """
    Kiểm tra tài nguyên hệ thống.

    Returns:
        Dict chứa kết quả kiểm tra tài nguyên
    """
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_status = "healthy"

        if cpu_percent > 90:
            cpu_status = "error"
        elif cpu_percent > 75:
            cpu_status = "warning"

        # Memory usage
        memory = psutil.virtual_memory()
        memory_status = "healthy"

        if memory.percent > 90:
            memory_status = "error"
        elif memory.percent > 80:
            memory_status = "warning"

        # Swap usage
        swap = psutil.swap_memory()
        swap_status = "healthy"

        if swap.percent > 90:
            swap_status = "error"
        elif swap.percent > 75:
            swap_status = "warning"

        # Tổng hợp kết quả
        result = {
            "status": "healthy",
            "cpu": {
                "percent": cpu_percent,
                "status": cpu_status,
            },
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": memory.percent,
                "status": memory_status,
            },
            "swap": {
                "total": swap.total,
                "used": swap.used,
                "free": swap.free,
                "percent": swap.percent,
                "status": swap_status,
            },
        }

        # Cập nhật trạng thái tổng thể
        statuses = [cpu_status, memory_status, swap_status]
        if "error" in statuses:
            result["status"] = "error"
        elif "warning" in statuses:
            result["status"] = "warning"

        return result

    except Exception as e:
        return {
            "status": "error",
            "message": f"System resources check failed: {str(e)}",
        }


def save_health_check_result(result: Dict[str, Any]) -> None:
    """
    Lưu kết quả kiểm tra sức khỏe vào database.

    Args:
        result: Kết quả kiểm tra
    """
    try:

        async def save_to_db():
            from app.monitoring.models.health_check import HealthCheckResult
            import json

            async with async_session() as session:
                # Chuyển result thành JSON string
                result_json = json.dumps(result)

                health_check = HealthCheckResult(
                    timestamp=datetime.datetime.now(),
                    status=result["overall_status"],
                    details=result_json,
                )

                session.add(health_check)
                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(save_to_db())

    except Exception as e:
        logger.error(f"Error saving health check result: {str(e)}")


def send_health_alert(result: Dict[str, Any]) -> None:
    """
    Gửi cảnh báo khi phát hiện vấn đề sức khỏe hệ thống.

    Args:
        result: Kết quả kiểm tra
    """
    try:
        # Chỉ gửi cảnh báo cho trạng thái không healthy
        if result["overall_status"] == "healthy":
            return

        # Tạo nội dung thông báo
        issues = []
        for check_name, check_result in result["checks"].items():
            if check_result.get("status") in ["error", "warning"]:
                issue = f"{check_name}: {check_result.get('message', check_result.get('status'))}"
                issues.append(issue)

        alert_subject = f"[{result['overall_status'].upper()}] System Health Alert"
        alert_message = "\n".join(issues)

        # Gửi email cho admin
        from app.tasks.email.send_email import send_email

        send_email(
            to_email=settings.ADMIN_EMAIL,
            subject=alert_subject,
            html_content=f"""
            <h1>System Health Alert</h1>
            <p>Status: <strong>{result['overall_status']}</strong></p>
            <p>Time: {result['timestamp']}</p>
            <h2>Issues detected:</h2>
            <ul>
                {''.join(['<li>' + issue + '</li>' for issue in issues])}
            </ul>
            <p>Please check the monitoring dashboard for more details.</p>
            """,
        )

    except Exception as e:
        logger.error(f"Error sending health alert: {str(e)}")


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.monitoring.health_check.ping_service",
    queue="monitoring",
)
def ping_service(
    self, service_name: str, host: str, port: int, timeout: int = 5
) -> Dict[str, Any]:
    """
    Kiểm tra dịch vụ bằng cách ping.

    Args:
        service_name: Tên dịch vụ
        host: Hostname hoặc IP
        port: Port
        timeout: Thời gian timeout (giây)

    Returns:
        Dict chứa kết quả ping
    """
    try:
        start_time = time.time()

        # Tạo socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        # Kết nối đến service
        result = sock.connect_ex((host, port))
        response_time = time.time() - start_time

        # Đóng socket
        sock.close()

        # Kết quả
        if result == 0:
            status = "healthy" if response_time < 1.0 else "warning"
            return {
                "service": service_name,
                "host": host,
                "port": port,
                "status": status,
                "response_time": response_time,
                "message": f"Service is reachable (response time: {response_time:.3f}s)",
            }
        else:
            return {
                "service": service_name,
                "host": host,
                "port": port,
                "status": "error",
                "response_time": None,
                "message": f"Service is unreachable (error code: {result})",
            }

    except Exception as e:
        return {
            "service": service_name,
            "host": host,
            "port": port,
            "status": "error",
            "message": f"Ping failed: {str(e)}",
        }
