import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for sending notifications and password reset emails."""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_tls = settings.SMTP_TLS

    def _send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """Send email using SMTP."""
        if not all([self.smtp_host, self.smtp_username, self.smtp_password]):
            logger.warning("Email configuration incomplete, skipping email send")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_username
            msg["To"] = to_email

            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_tls:
                    server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def send_password_reset_email(
        self, to_email: str, reset_token: str, user_name: str
    ) -> bool:
        """Send password reset email."""
        # In a real app, this would be a proper frontend URL
        reset_url = f"http://localhost:5173/reset-password?token={reset_token}"

        subject = "Password Reset Request - Book Reading Platform"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Password Reset</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; text-align: center; border-radius: 8px; }}
                .content {{ padding: 20px; }}
                .button {{ display: inline-block; padding: 12px 24px; background-color: #007bff; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }}
                .footer {{ font-size: 12px; color: #666; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                <div class="content">
                    <p>Hello {user_name},</p>
                    <p>We received a request to reset your password for your Book Reading Platform account.</p>
                    <p>Click the button below to reset your password:</p>
                    <a href="{reset_url}" class="button">Reset Password</a>
                    <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                    <p><a href="{reset_url}">{reset_url}</a></p>
                    <p>This link will expire in 1 hour for security reasons.</p>
                    <p>If you didn't request this password reset, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>Best regards,<br>Book Reading Platform Team</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(to_email, subject, html_content)

    def send_welcome_email(self, to_email: str, user_name: str) -> bool:
        """Send welcome email to new users."""
        subject = "Welcome to Book Reading Platform"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Welcome</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; text-align: center; border-radius: 8px; }}
                .content {{ padding: 20px; }}
                .footer {{ font-size: 12px; color: #666; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to Book Reading Platform!</h1>
                </div>
                <div class="content">
                    <p>Hello {user_name},</p>
                    <p>Welcome to our Book Reading Platform! We're excited to have you join our community of book lovers.</p>
                    <p>You can now:</p>
                    <ul>
                        <li>Browse our extensive book collection</li>
                        <li>Track your reading progress</li>
                        <li>Discover new authors and categories</li>
                        <li>Connect with other readers</li>
                    </ul>
                    <p>Happy reading!</p>
                </div>
                <div class="footer">
                    <p>Best regards,<br>Book Reading Platform Team</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(to_email, subject, html_content)


# Create a singleton instance
email_service = EmailService()
