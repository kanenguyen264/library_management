"""
Tác vụ gửi email

Module này cung cấp các tác vụ liên quan đến gửi email:
- Gửi email chào mừng
- Gửi email thông báo
- Gửi email đặt lại mật khẩu
"""

import os
import datetime
import time
import asyncio
from typing import Dict, Any, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import jinja2

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.tasks.worker import celery_app
from app.tasks.base_task import BaseTask
from app.core.db import async_session

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)

# Thiết lập Jinja2 environment
template_dir = os.path.join(os.path.dirname(__file__), "templates")
template_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(template_dir),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.email.send_email.send_welcome_email",
    queue="emails",
    max_retries=3,
)
def send_welcome_email(
    self, user_id: int, email: str, first_name: str
) -> Dict[str, Any]:
    """
    Gửi email chào mừng khi người dùng đăng ký.

    Args:
        user_id: ID của người dùng
        email: Địa chỉ email
        first_name: Tên người dùng

    Returns:
        Dict chứa kết quả gửi email
    """
    try:
        logger.info(f"Sending welcome email to user_id={user_id} ({email})")

        # Nạp template
        template = template_env.get_template("welcome.html")

        # Chuẩn bị dữ liệu
        context = {
            "first_name": first_name,
            "app_name": settings.APP_NAME,
            "year": datetime.datetime.now().year,
            "login_url": f"{settings.FRONTEND_URL}/login",
            "help_url": f"{settings.FRONTEND_URL}/help",
        }

        # Tạo nội dung email
        html_content = template.render(**context)

        # Gửi email
        result = send_email(
            to_email=email,
            subject=f"Chào mừng đến với {settings.APP_NAME}!",
            html_content=html_content,
        )

        # Lưu nhật ký gửi email
        log_email_sent(user_id, "welcome", result["success"])

        return result

    except Exception as e:
        logger.error(f"Error sending welcome email to {email}: {str(e)}")
        self.retry(exc=e, countdown=60)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.email.send_email.send_notification_email",
    queue="emails",
    max_retries=3,
)
def send_notification_email(
    self,
    user_id: int,
    email: str,
    subject: str,
    notification_type: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Gửi email thông báo.

    Args:
        user_id: ID của người dùng
        email: Địa chỉ email
        subject: Tiêu đề email
        notification_type: Loại thông báo (new_book, reading_reminder, ...)
        data: Dữ liệu cho thông báo

    Returns:
        Dict chứa kết quả gửi email
    """
    try:
        logger.info(f"Sending notification email to user_id={user_id} ({email})")

        # Nạp template
        template = template_env.get_template("notification.html")

        # Thêm thông tin chung vào dữ liệu
        context = {
            "app_name": settings.APP_NAME,
            "year": datetime.datetime.now().year,
            "notification_type": notification_type,
            "notification_date": datetime.datetime.now().strftime("%d/%m/%Y"),
            "unsubscribe_url": f"{settings.FRONTEND_URL}/settings/notifications",
            **data,
        }

        # Tạo nội dung email
        html_content = template.render(**context)

        # Gửi email
        result = send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
        )

        # Lưu nhật ký gửi email
        log_email_sent(user_id, f"notification_{notification_type}", result["success"])

        return result

    except Exception as e:
        logger.error(f"Error sending notification email to {email}: {str(e)}")
        self.retry(exc=e, countdown=60)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.email.send_email.send_password_reset_email",
    queue="emails",
    max_retries=3,
)
def send_password_reset_email(
    self, user_id: int, email: str, reset_token: str, first_name: str
) -> Dict[str, Any]:
    """
    Gửi email đặt lại mật khẩu.

    Args:
        user_id: ID của người dùng
        email: Địa chỉ email
        reset_token: Token đặt lại mật khẩu
        first_name: Tên người dùng

    Returns:
        Dict chứa kết quả gửi email
    """
    try:
        logger.info(f"Sending password reset email to user_id={user_id} ({email})")

        # Nạp template
        template = template_env.get_template("reset_password.html")

        # Chuẩn bị dữ liệu
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        context = {
            "first_name": first_name,
            "reset_url": reset_url,
            "app_name": settings.APP_NAME,
            "year": datetime.datetime.now().year,
            "expiry_hours": 24,  # Token hết hạn sau 24 giờ
        }

        # Tạo nội dung email
        html_content = template.render(**context)

        # Gửi email
        result = send_email(
            to_email=email,
            subject=f"Đặt lại mật khẩu cho tài khoản {settings.APP_NAME}",
            html_content=html_content,
        )

        # Lưu nhật ký gửi email
        log_email_sent(user_id, "password_reset", result["success"])

        return result

    except Exception as e:
        logger.error(f"Error sending password reset email to {email}: {str(e)}")
        self.retry(exc=e, countdown=60)


def send_email(to_email: str, subject: str, html_content: str) -> Dict[str, Any]:
    """
    Gửi email.

    Args:
        to_email: Địa chỉ email người nhận
        subject: Tiêu đề email
        html_content: Nội dung HTML

    Returns:
        Dict chứa kết quả gửi email
    """
    try:
        # Tạo message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USERNAME
        msg["To"] = to_email

        # Thêm nội dung HTML
        part = MIMEText(html_content, "html")
        msg.attach(part)

        # Kết nối đến SMTP server
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

        # Gửi email
        server.sendmail(settings.SMTP_USERNAME, to_email, msg.as_string())
        server.quit()

        logger.info(f"Email sent successfully to {to_email}")
        return {
            "success": True,
            "to_email": to_email,
            "subject": subject,
            "sent_at": datetime.datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {str(e)}")
        return {
            "success": False,
            "to_email": to_email,
            "subject": subject,
            "error": str(e),
        }


def log_email_sent(user_id: int, email_type: str, success: bool) -> None:
    """
    Lưu nhật ký gửi email.

    Args:
        user_id: ID của người dùng
        email_type: Loại email
        success: Trạng thái gửi
    """
    try:

        async def save_log():
            from app.user_site.models.email_log import EmailLog

            async with async_session() as session:
                log = EmailLog(
                    user_id=user_id,
                    email_type=email_type,
                    status="success" if success else "failed",
                    sent_at=datetime.datetime.now(),
                )
                session.add(log)
                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(save_log())

    except Exception as e:
        logger.error(f"Error logging email: {str(e)}")
