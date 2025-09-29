import logging
import logging.handlers
import os
import socket
import time
from typing import Dict, Any, Optional
import json
import requests
from app.core.config import get_settings

settings = get_settings()


class RotatingSecureFileHandler(logging.handlers.RotatingFileHandler):
    """
    Rotating file handler với bảo mật tăng cường:
    - Tạo file và thư mục với quyền hạn phù hợp
    - Kiểm tra và tạo file backup với file permissions chính xác
    """

    def __init__(
        self,
        filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
        permissions=0o600,  # Chỉ owner đọc/ghi
        dir_permissions=0o700,  # Chỉ owner đọc/ghi/execute
    ):
        self.permissions = permissions
        self.dir_permissions = dir_permissions

        # Đảm bảo thư mục tồn tại với quyền hạn chính xác
        log_dir = os.path.dirname(filename)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, mode=dir_permissions)
        elif log_dir and os.path.exists(log_dir):
            os.chmod(log_dir, dir_permissions)

        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)

    def _open(self):
        """Mở file với quyền hạn giới hạn."""
        stream = super()._open()

        # Set file permissions
        if self.permissions:
            os.chmod(self.baseFilename, self.permissions)

        return stream

    def doRollover(self):
        """Xử lý rollover với quyền hạn chính xác."""
        super().doRollover()

        # Đảm bảo backup files có cùng permissions
        if self.backupCount > 0:
            for i in range(1, self.backupCount + 1):
                backup_file = f"{self.baseFilename}.{i}"
                if os.path.exists(backup_file):
                    os.chmod(backup_file, self.permissions)


class SlackHandler(logging.Handler):
    """
    Handler gửi log quan trọng tới Slack channel.
    Hữu ích cho các cảnh báo bảo mật trong thời gian thực.
    """

    def __init__(
        self, webhook_url: str, channel: str = "#alerts", username: str = "Security Bot"
    ):
        super().__init__()
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.hostname = socket.gethostname()

    def emit(self, record: logging.LogRecord):
        """
        Emit log record to Slack.

        Args:
            record: Log record to emit
        """
        try:
            # Skip debug messages for Slack
            if record.levelno < logging.WARNING:
                return

            # Format the message
            message = self.format(record)

            # Prepare payload
            payload = {
                "channel": self.channel,
                "username": self.username,
                "text": f"*{record.levelname}* on `{self.hostname}`: {message}",
                "icon_emoji": (
                    ":warning:"
                    if record.levelno == logging.WARNING
                    else ":rotating_light:"
                ),
            }

            # Add exception details if any
            if record.exc_info:
                payload["text"] += f"\n```{self.formatException(record.exc_info)}```"

            # Send to Slack
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            response.raise_for_status()

        except Exception as e:
            # Don't crash on error, just write to stderr
            import sys

            print(f"Error sending to Slack: {e}", file=sys.stderr)


class DatabaseHandler(logging.Handler):
    """
    Handler lưu log vào cơ sở dữ liệu.
    Hữu ích cho log security và audit trails có cấu trúc, dễ truy vấn.
    """

    def __init__(self, session_maker):
        super().__init__()
        self.session_maker = session_maker

    def emit(self, record: logging.LogRecord):
        """
        Emit log record to database.

        Args:
            record: Log record to emit
        """
        try:
            try:
                # Thử import models
                from app.logs_manager.models.error_log import ErrorLog
                from app.logs_manager.models.authentication_log import AuthenticationLog
            except ImportError:
                import sys

                print("Warning: Could not import log models.", file=sys.stderr)
                return

            from sqlalchemy.orm import Session
            import json

            message = self.format(record)

            # Extract extra data if available
            extra_data = {}
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "exc_info",
                    "exc_text",
                    "lineno",
                    "funcName",
                    "created",
                    "asctime",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                ]:
                    extra_data[key] = str(value)

            # Handle different log types
            if record.name.startswith("app.security"):
                with Session(self.session_maker) as session:
                    log_entry = AuthenticationLog(
                        action=record.funcName,
                        status=record.levelname,
                        ip_address=extra_data.get("ip_address"),
                        user_agent=extra_data.get("user_agent"),
                        user_id=extra_data.get("user_id"),
                        admin_id=extra_data.get("admin_id"),
                        details=json.dumps(extra_data),
                    )
                    session.add(log_entry)
                    session.commit()

            elif record.levelno >= logging.ERROR:
                with Session(self.session_maker) as session:
                    log_entry = ErrorLog(
                        error_level=record.levelname,
                        error_message=message,
                        stack_trace=(
                            self.formatException(record.exc_info)
                            if record.exc_info
                            else None
                        ),
                        source=record.module,
                        user_id=extra_data.get("user_id"),
                        admin_id=extra_data.get("admin_id"),
                        ip_address=extra_data.get("ip_address"),
                        user_agent=extra_data.get("user_agent"),
                        request_data=json.dumps(extra_data) if extra_data else None,
                    )
                    session.add(log_entry)
                    session.commit()

        except Exception as e:
            # Don't crash on error, just write to stderr
            import sys

            print(f"Error logging to database: {e}", file=sys.stderr)
