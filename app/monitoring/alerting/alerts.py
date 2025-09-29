from typing import Dict, List, Any, Optional, Union, Set, Tuple, Callable
import logging
import time
import asyncio
import threading
from enum import Enum
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import json

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)


class AlertSeverity(str, Enum):
    """Mức độ nghiêm trọng của cảnh báo."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AlertChannel(str, Enum):
    """Kênh gửi cảnh báo."""

    EMAIL = "email"
    SLACK = "slack"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"
    SMS = "sms"
    LOG = "log"


class AlertingSystem:
    """
    Hệ thống cảnh báo ứng dụng.
    Phát hiện và gửi thông báo khi có sự cố.
    """

    def __init__(self):
        """Khởi tạo hệ thống cảnh báo."""
        # Cấu hình cảnh báo
        self.enabled = settings.ALERTING_ENABLED
        self.default_channels = [AlertChannel.LOG]

        if settings.ALERTING_EMAIL_ENABLED:
            self.default_channels.append(AlertChannel.EMAIL)

        if settings.ALERTING_SLACK_ENABLED:
            self.default_channels.append(AlertChannel.SLACK)

        # Threshold cho rate limiting
        self.rate_limit_seconds = settings.ALERTING_RATE_LIMIT_SECONDS

        # Cache để tránh gửi cùng một cảnh báo nhiều lần
        self.alert_cache = {}

        logger.info(
            f"Khởi tạo AlertingSystem, enabled={self.enabled}, channels={self.default_channels}"
        )

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.ERROR,
        channels: Optional[List[AlertChannel]] = None,
        tags: Optional[List[str]] = None,
        group: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        rate_limit_key: Optional[str] = None,
    ) -> bool:
        """
        Gửi cảnh báo.

        Args:
            title: Tiêu đề cảnh báo
            message: Nội dung cảnh báo
            severity: Mức độ nghiêm trọng
            channels: Kênh gửi cảnh báo
            tags: Tags cho cảnh báo
            group: Nhóm cảnh báo
            metadata: Metadata bổ sung
            rate_limit_key: Khóa để giới hạn tần suất gửi

        Returns:
            True nếu gửi thành công
        """
        if not self.enabled:
            logger.debug(f"AlertingSystem đã bị tắt, không gửi cảnh báo: {title}")
            return False

        # Kiểm tra rate limiting
        if rate_limit_key:
            cache_key = f"{rate_limit_key}:{severity}"
            last_sent = self.alert_cache.get(cache_key, 0)
            now = time.time()

            if now - last_sent < self.rate_limit_seconds:
                logger.debug(f"Rate limit cho cảnh báo: {title} ({rate_limit_key})")
                return False

            # Cập nhật thời gian gửi gần nhất
            self.alert_cache[cache_key] = now

        # Sử dụng channels mặc định nếu không có
        if channels is None:
            channels = self.default_channels

        # Chuẩn bị metadata
        full_metadata = {
            "timestamp": time.time(),
            "severity": severity,
            "tags": tags or [],
            "group": group,
        }

        if metadata:
            full_metadata.update(metadata)

        # Gửi qua các kênh
        success = True

        for channel in channels:
            try:
                if channel == AlertChannel.EMAIL:
                    await self._send_email_alert(
                        title, message, severity, full_metadata
                    )
                elif channel == AlertChannel.SLACK:
                    await self._send_slack_alert(
                        title, message, severity, full_metadata
                    )
                elif channel == AlertChannel.TELEGRAM:
                    await self._send_telegram_alert(
                        title, message, severity, full_metadata
                    )
                elif channel == AlertChannel.WEBHOOK:
                    await self._send_webhook_alert(
                        title, message, severity, full_metadata
                    )
                elif channel == AlertChannel.SMS:
                    await self._send_sms_alert(title, message, severity, full_metadata)
                elif channel == AlertChannel.LOG:
                    self._send_log_alert(title, message, severity, full_metadata)
                else:
                    logger.warning(f"Kênh cảnh báo không hỗ trợ: {channel}")
                    success = False
            except Exception as e:
                logger.error(f"Lỗi khi gửi cảnh báo qua {channel}: {str(e)}")
                success = False

        return success

    async def _send_email_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        Gửi cảnh báo qua email.

        Args:
            title: Tiêu đề cảnh báo
            message: Nội dung cảnh báo
            severity: Mức độ nghiêm trọng
            metadata: Metadata bổ sung

        Returns:
            True nếu gửi thành công
        """
        if not settings.ALERTING_EMAIL_ENABLED:
            return False

        try:
            # Tạo email
            msg = MIMEMultipart()
            msg["From"] = settings.SMTP_FROM_EMAIL
            msg["To"] = ", ".join(settings.ALERTING_EMAIL_RECIPIENTS)
            msg["Subject"] = f"[{severity.upper()}] {title}"

            # Tạo nội dung
            html = f"""
            <html>
            <head></head>
            <body>
                <h2 style="color: {'red' if severity == AlertSeverity.CRITICAL else 'orange' if severity == AlertSeverity.ERROR else 'blue'}">{title}</h2>
                <p>{message}</p>
                <hr>
                <h3>Metadata:</h3>
                <ul>
            """

            for key, value in metadata.items():
                html += f"<li><strong>{key}:</strong> {value}</li>"

            html += """
                </ul>
            </body>
            </html>
            """

            # Thêm nội dung vào email
            msg.attach(MIMEText(html, "html"))

            # Gửi email
            loop = asyncio.get_event_loop()

            await loop.run_in_executor(None, self._send_email, msg)

            return True

        except Exception as e:
            logger.error(f"Lỗi khi gửi email cảnh báo: {str(e)}")
            return False

    def _send_email(self, msg: MIMEMultipart):
        """
        Gửi email (sync).

        Args:
            msg: Email message
        """
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_TLS:
                server.starttls()

            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

            server.send_message(msg)

    async def _send_slack_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        Gửi cảnh báo qua Slack.

        Args:
            title: Tiêu đề cảnh báo
            message: Nội dung cảnh báo
            severity: Mức độ nghiêm trọng
            metadata: Metadata bổ sung

        Returns:
            True nếu gửi thành công
        """
        if not settings.ALERTING_SLACK_ENABLED:
            return False

        try:
            # Chọn màu theo severity
            color = {
                AlertSeverity.CRITICAL: "#FF0000",  # Đỏ
                AlertSeverity.ERROR: "#FF9900",  # Cam
                AlertSeverity.WARNING: "#FFCC00",  # Vàng
                AlertSeverity.INFO: "#3AA3E3",  # Xanh
            }.get(severity, "#3AA3E3")

            # Tạo fields từ metadata
            fields = []

            for key, value in metadata.items():
                if key in ["timestamp", "tags", "group"]:
                    # Xử lý đặc biệt
                    if key == "timestamp":
                        value = time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime(value)
                        )
                    elif key == "tags":
                        value = ", ".join(value)

                    fields.append(
                        {"title": key.capitalize(), "value": value, "short": True}
                    )

            # Tạo payload
            payload = {
                "attachments": [
                    {
                        "fallback": f"[{severity.upper()}] {title}",
                        "color": color,
                        "title": title,
                        "text": message,
                        "fields": fields,
                        "footer": "API Reading Book Alert System",
                        "ts": int(time.time()),
                    }
                ]
            }

            # Gửi webhook
            async with requests.AsyncSession() as session:
                async with session.post(
                    settings.ALERTING_SLACK_WEBHOOK_URL, json=payload, timeout=5
                ) as response:
                    return response.status_code == 200

        except Exception as e:
            logger.error(f"Lỗi khi gửi Slack cảnh báo: {str(e)}")
            return False

    async def _send_telegram_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        Gửi cảnh báo qua Telegram.

        Args:
            title: Tiêu đề cảnh báo
            message: Nội dung cảnh báo
            severity: Mức độ nghiêm trọng
            metadata: Metadata bổ sung

        Returns:
            True nếu gửi thành công
        """
        if not settings.ALERTING_TELEGRAM_ENABLED:
            return False

        try:
            # Tạo nội dung tin nhắn
            text = f"*[{severity.upper()}] {title}*\n\n{message}\n\n"

            # Thêm metadata
            text += "*Metadata:*\n"

            for key, value in metadata.items():
                if key == "timestamp":
                    value = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))
                elif key == "tags":
                    value = ", ".join(value)

                text += f"- {key.capitalize()}: {value}\n"

            # Gửi webhook
            url = f"https://api.telegram.org/bot{settings.ALERTING_TELEGRAM_BOT_TOKEN}/sendMessage"

            payload = {
                "chat_id": settings.ALERTING_TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
            }

            async with requests.AsyncSession() as session:
                async with session.post(url, json=payload, timeout=5) as response:
                    return response.status_code == 200

        except Exception as e:
            logger.error(f"Lỗi khi gửi Telegram cảnh báo: {str(e)}")
            return False

    async def _send_webhook_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        Gửi cảnh báo qua webhook.

        Args:
            title: Tiêu đề cảnh báo
            message: Nội dung cảnh báo
            severity: Mức độ nghiêm trọng
            metadata: Metadata bổ sung

        Returns:
            True nếu gửi thành công
        """
        if not settings.ALERTING_WEBHOOK_ENABLED:
            return False

        try:
            # Tạo payload
            payload = {
                "title": title,
                "message": message,
                "severity": severity,
                "metadata": metadata,
            }

            # Gửi webhook
            async with requests.AsyncSession() as session:
                async with session.post(
                    settings.ALERTING_WEBHOOK_URL, json=payload, timeout=5
                ) as response:
                    return response.status_code == 200

        except Exception as e:
            logger.error(f"Lỗi khi gửi webhook cảnh báo: {str(e)}")
            return False

    async def _send_sms_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        Gửi cảnh báo qua SMS.

        Args:
            title: Tiêu đề cảnh báo
            message: Nội dung cảnh báo
            severity: Mức độ nghiêm trọng
            metadata: Metadata bổ sung

        Returns:
            True nếu gửi thành công
        """
        if not settings.ALERTING_SMS_ENABLED:
            return False

        # TODO: Implement SMS integration
        logger.warning("Gửi SMS cảnh báo chưa được triển khai")
        return False

    def _send_log_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        Ghi cảnh báo vào log.

        Args:
            title: Tiêu đề cảnh báo
            message: Nội dung cảnh báo
            severity: Mức độ nghiêm trọng
            metadata: Metadata bổ sung

        Returns:
            True
        """
        # Chọn log level dựa vào severity
        log_func = {
            AlertSeverity.CRITICAL: logger.critical,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.INFO: logger.info,
        }.get(severity, logger.error)

        # Ghi log
        log_func(f"ALERT [{severity.upper()}] {title} - {message}")

        return True

    async def create_threshold_alert(
        self,
        metric_name: str,
        current_value: float,
        threshold: float,
        comparison: str,
        title: Optional[str] = None,
        message: Optional[str] = None,
        severity: AlertSeverity = AlertSeverity.WARNING,
        channels: Optional[List[AlertChannel]] = None,
        tags: Optional[List[str]] = None,
        group: Optional[str] = None,
        rate_limit_key: Optional[str] = None,
    ) -> bool:
        """
        Tạo cảnh báo dựa trên threshold.

        Args:
            metric_name: Tên metric
            current_value: Giá trị hiện tại
            threshold: Ngưỡng so sánh
            comparison: Loại so sánh (>, <, >=, <=, ==, !=)
            title: Tiêu đề cảnh báo
            message: Nội dung cảnh báo
            severity: Mức độ nghiêm trọng
            channels: Kênh gửi cảnh báo
            tags: Tags cho cảnh báo
            group: Nhóm cảnh báo
            rate_limit_key: Khóa để giới hạn tần suất gửi

        Returns:
            True nếu gửi thành công
        """
        # Kiểm tra threshold
        alert_triggered = False

        if comparison == ">" and current_value > threshold:
            alert_triggered = True
        elif comparison == "<" and current_value < threshold:
            alert_triggered = True
        elif comparison == ">=" and current_value >= threshold:
            alert_triggered = True
        elif comparison == "<=" and current_value <= threshold:
            alert_triggered = True
        elif comparison == "==" and current_value == threshold:
            alert_triggered = True
        elif comparison == "!=" and current_value != threshold:
            alert_triggered = True

        if not alert_triggered:
            return False

        # Tạo tiêu đề nếu chưa có
        if not title:
            title = f"Metric {metric_name} {comparison} {threshold}"

        # Tạo nội dung nếu chưa có
        if not message:
            message = f"Metric {metric_name} has value {current_value} which is {comparison} threshold {threshold}"

        # Tạo metadata
        metadata = {
            "metric_name": metric_name,
            "current_value": current_value,
            "threshold": threshold,
            "comparison": comparison,
        }

        # Tạo key giới hạn tần suất nếu chưa có
        if not rate_limit_key:
            rate_limit_key = f"threshold:{metric_name}:{comparison}:{threshold}"

        # Gửi cảnh báo
        return await self.send_alert(
            title=title,
            message=message,
            severity=severity,
            channels=channels,
            tags=tags,
            group=group,
            metadata=metadata,
            rate_limit_key=rate_limit_key,
        )


# Sử dụng Singleton pattern để khởi tạo lazy
_alerting_instance = None


def get_alerting_system() -> AlertingSystem:
    """
    Trả về instance singleton của AlertingSystem.
    Khởi tạo lazy để tránh lỗi khi khởi động.

    Returns:
        AlertingSystem: Instance của hệ thống cảnh báo
    """
    global _alerting_instance
    if _alerting_instance is None:
        _alerting_instance = AlertingSystem()
    return _alerting_instance


# Để compatibility với code đang dùng alerting trực tiếp
alerting = get_alerting_system()


# Decorators tiện ích
def alert_on_exception(
    title: Optional[str] = None,
    severity: AlertSeverity = AlertSeverity.ERROR,
    channels: Optional[List[AlertChannel]] = None,
    tags: Optional[List[str]] = None,
    group: Optional[str] = None,
    rate_limit_key: Optional[str] = None,
):
    """
    Decorator để gửi cảnh báo khi có exception.

    Args:
        title: Tiêu đề cảnh báo
        severity: Mức độ nghiêm trọng
        channels: Kênh gửi cảnh báo
        tags: Tags cho cảnh báo
        group: Nhóm cảnh báo
        rate_limit_key: Khóa để giới hạn tần suất gửi

    Returns:
        Decorator
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Tạo tiêu đề nếu chưa có
                alert_title = title or f"Exception in {func.__qualname__}"

                # Tạo nội dung
                message = f"Exception: {type(e).__name__}: {str(e)}"

                # Tạo metadata
                metadata = {
                    "function": func.__qualname__,
                    "exception_type": type(e).__name__,
                    "exception_args": str(args),
                    "exception_kwargs": str(kwargs),
                }

                # Tạo key giới hạn tần suất nếu chưa có
                alert_rate_limit_key = (
                    rate_limit_key
                    or f"exception:{func.__qualname__}:{type(e).__name__}"
                )

                # Gửi cảnh báo
                await alerting.send_alert(
                    title=alert_title,
                    message=message,
                    severity=severity,
                    channels=channels,
                    tags=tags or ["exception"],
                    group=group or "exceptions",
                    metadata=metadata,
                    rate_limit_key=alert_rate_limit_key,
                )

                # Re-raise exception
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Tạo tiêu đề nếu chưa có
                alert_title = title or f"Exception in {func.__qualname__}"

                # Tạo nội dung
                message = f"Exception: {type(e).__name__}: {str(e)}"

                # Tạo metadata
                metadata = {
                    "function": func.__qualname__,
                    "exception_type": type(e).__name__,
                    "exception_args": str(args),
                    "exception_kwargs": str(kwargs),
                }

                # Tạo key giới hạn tần suất nếu chưa có
                alert_rate_limit_key = (
                    rate_limit_key
                    or f"exception:{func.__qualname__}:{type(e).__name__}"
                )

                # Tạo task để gửi cảnh báo
                loop = asyncio.get_event_loop()

                loop.create_task(
                    alerting.send_alert(
                        title=alert_title,
                        message=message,
                        severity=severity,
                        channels=channels,
                        tags=tags or ["exception"],
                        group=group or "exceptions",
                        metadata=metadata,
                        rate_limit_key=alert_rate_limit_key,
                    )
                )

                # Re-raise exception
                raise

        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
