"""
Module bảo mật CAPTCHA - Cung cấp các tính năng xác minh CAPTCHA.

Module này cung cấp:
- Xác thực Google reCAPTCHA
- Xác thực hCaptcha
- Xác thực tự tạo / captcha tùy chỉnh
"""

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Import functions
from app.security.captcha.verifier import verify_captcha
