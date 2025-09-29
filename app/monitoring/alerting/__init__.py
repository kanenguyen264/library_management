"""
Module cảnh báo (Alerting) - Hệ thống gửi cảnh báo khi có sự cố hoặc vượt ngưỡng.

Module này cung cấp:
- Hệ thống gửi cảnh báo qua nhiều kênh (email, Slack, Telegram...)
- Cảnh báo theo ngưỡng cho metrics
- Decorator để tự động bắt và cảnh báo khi có exception
"""

from app.monitoring.alerting.alerts import (
    AlertSeverity,
    AlertChannel,
    get_alerting_system,
    alert_on_exception,
)
from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Compatibility với code cũ
alerting = get_alerting_system()


def initialize_alert_channels():
    """
    Khởi tạo các kênh cảnh báo dựa trên cấu hình.
    Gọi hàm này trong quá trình khởi động ứng dụng.
    """
    # Đơn giản hóa cấu hình để tránh lỗi
    try:
        logger.info(
            f"Khởi tạo hệ thống cảnh báo với cấu hình: enabled={settings.ALERTING_ENABLED}"
        )

        # Ghi log các kênh cảnh báo đã được cấu hình
        if settings.ALERTING_EMAIL_ENABLED:
            logger.info("Kênh cảnh báo Email đã được cấu hình")

        if settings.ALERTING_SLACK_ENABLED:
            logger.info("Kênh cảnh báo Slack đã được cấu hình")

        # Luôn bật cảnh báo qua log
        logger.info("Kênh cảnh báo Log luôn được bật mặc định")
    except Exception as e:
        logger.error(f"Lỗi khi khởi tạo hệ thống cảnh báo: {str(e)}")


async def send_alert(
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.ERROR,
    channels: list = None,
) -> bool:
    """
    Gửi cảnh báo sử dụng hệ thống cảnh báo.

    Args:
        title: Tiêu đề cảnh báo
        message: Nội dung cảnh báo
        severity: Mức độ nghiêm trọng
        channels: Danh sách kênh cảnh báo (nếu None, gửi đến tất cả)

    Returns:
        True nếu gửi thành công, False nếu thất bại
    """
    return await alerting.send_alert(
        title=title, message=message, severity=severity, channels=channels
    )


# Export các biến, hàm, class
__all__ = [
    "alerting",
    "initialize_alert_channels",
    "send_alert",
    "AlertSeverity",
    "AlertChannel",
    "alert_on_exception",
]
