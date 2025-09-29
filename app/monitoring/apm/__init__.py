"""
Application Performance Monitoring (APM) - Giám sát hiệu suất ứng dụng.

Module này cung cấp:
- Theo dõi hiệu suất của các API endpoint
- Đo thời gian xử lý các thao tác quan trọng
- Ghi nhận và theo dõi các ngoại lệ (exception)
- Hỗ trợ nhiều APM backend khác nhau (Elastic APM, New Relic, Datadog)
"""

from app.monitoring.apm.apm_agent import (
    APMAgent,
    initialize_apm,
    trace_function,
    DummyTransaction,
)

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo APM agent singleton
apm_agent = APMAgent()


def setup_apm(app=None):
    """
    Thiết lập và khởi tạo APM agent cho ứng dụng.

    Args:
        app: Ứng dụng FastAPI (tùy chọn)
    """
    try:
        # Khởi tạo APM agent nếu được cấu hình
        if settings.APM_ENABLED:
            # Khởi tạo agent với cấu hình từ settings
            initialize_apm(service_name=settings.SERVICE_NAME, env=settings.APP_ENV)

            logger.info(
                f"Đã khởi tạo APM agent cho service '{settings.SERVICE_NAME}' ở môi trường '{settings.APP_ENV}'"
            )

            # Nếu có app FastAPI, gắn middleware và hooks
            if app:
                # Thêm middleware và hooks nếu cần
                @app.on_event("startup")
                async def startup_apm():
                    # Bắt đầu transaction cho startup
                    with apm_agent.start_transaction("app.startup", "app-lifecycle"):
                        logger.info("APM đang theo dõi quá trình khởi động ứng dụng")

                @app.on_event("shutdown")
                async def shutdown_apm():
                    # Đóng APM agent
                    logger.info("Đang dừng APM agent")

        else:
            logger.info("APM đã bị tắt trong cấu hình")

    except Exception as e:
        logger.error(f"Lỗi khi khởi tạo APM: {str(e)}")


# Export các biến, hàm và class
__all__ = [
    "apm_agent",
    "setup_apm",
    "APMAgent",
    "initialize_apm",
    "trace_function",
    "DummyTransaction",
]
