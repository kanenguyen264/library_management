"""
Xác thực CAPTCHA - Cung cấp các hàm xác thực CAPTCHA từ các nhà cung cấp khác nhau.
"""

import aiohttp
import json
from typing import Dict, Any, Optional, Tuple
import asyncio
import logging
from fastapi import HTTPException, status

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)


async def verify_captcha(
    token: str, ip_address: Optional[str] = None, action: Optional[str] = None
) -> bool:
    """
    Xác thực token CAPTCHA.

    Args:
        token: Token CAPTCHA cần xác thực
        ip_address: Địa chỉ IP người dùng (nếu có)
        action: Hành động đang được thực hiện (cho reCAPTCHA v3)

    Returns:
        bool: True nếu xác thực thành công, False nếu thất bại
    """
    if not settings.CAPTCHA_ENABLED:
        logger.debug("Captcha verification skipped (disabled in settings)")
        return True

    captcha_type = getattr(settings, "CAPTCHA_TYPE", "recaptcha")

    try:
        if captcha_type.lower() == "recaptcha":
            return await verify_recaptcha(token, ip_address, action)
        elif captcha_type.lower() == "hcaptcha":
            return await verify_hcaptcha(token, ip_address)
        elif captcha_type.lower() == "custom":
            return await verify_custom_captcha(token, ip_address)
        else:
            logger.warning(f"Không hỗ trợ loại captcha: {captcha_type}")
            # Trong môi trường production, không nên cho qua nếu cấu hình sai
            if settings.APP_ENV == "production":
                return False
            return True
    except Exception as e:
        logger.error(f"Lỗi khi xác thực captcha: {str(e)}")
        # Trong môi trường development, bỏ qua lỗi captcha để dễ phát triển
        if settings.APP_ENV == "development":
            return True
        return False


async def verify_recaptcha(
    token: str, ip_address: Optional[str] = None, action: Optional[str] = None
) -> bool:
    """
    Xác thực Google reCAPTCHA.

    Args:
        token: reCAPTCHA token
        ip_address: Địa chỉ IP người dùng
        action: Hành động đang được thực hiện (cho reCAPTCHA v3)

    Returns:
        bool: True nếu xác thực thành công, False nếu thất bại
    """
    # Lấy secret key từ cấu hình
    secret_key = getattr(settings, "RECAPTCHA_SECRET_KEY", "")
    v3_min_score = getattr(settings, "RECAPTCHA_V3_MIN_SCORE", 0.5)

    if not secret_key:
        logger.error("Thiếu RECAPTCHA_SECRET_KEY trong cấu hình")
        return False

    # Chuẩn bị dữ liệu gửi đến API Google
    data = {"secret": secret_key, "response": token}

    if ip_address:
        data["remoteip"] = ip_address

    # Gọi API Google reCAPTCHA
    verify_url = "https://www.google.com/recaptcha/api/siteverify"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(verify_url, data=data) as response:
                result = await response.json()

                if not result.get("success", False):
                    error_codes = result.get("error-codes", [])
                    logger.warning(f"reCAPTCHA xác thực thất bại: {error_codes}")
                    return False

                # Kiểm tra score cho reCAPTCHA v3
                score = result.get("score", 1.0)
                if "score" in result and score < v3_min_score:
                    logger.warning(
                        f"reCAPTCHA v3 score quá thấp: {score} < {v3_min_score}"
                    )
                    return False

                # Kiểm tra action nếu có
                if action and "action" in result and result["action"] != action:
                    logger.warning(
                        f"reCAPTCHA action không khớp: {result['action']} != {action}"
                    )
                    return False

                return True
    except Exception as e:
        logger.error(f"Lỗi khi gọi API reCAPTCHA: {str(e)}")
        return False


async def verify_hcaptcha(token: str, ip_address: Optional[str] = None) -> bool:
    """
    Xác thực hCaptcha.

    Args:
        token: hCaptcha token
        ip_address: Địa chỉ IP người dùng

    Returns:
        bool: True nếu xác thực thành công, False nếu thất bại
    """
    # Lấy secret key từ cấu hình
    secret_key = getattr(settings, "HCAPTCHA_SECRET_KEY", "")

    if not secret_key:
        logger.error("Thiếu HCAPTCHA_SECRET_KEY trong cấu hình")
        return False

    # Chuẩn bị dữ liệu gửi đến API hCaptcha
    data = {"secret": secret_key, "response": token}

    if ip_address:
        data["remoteip"] = ip_address

    # Gọi API hCaptcha
    verify_url = "https://hcaptcha.com/siteverify"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(verify_url, data=data) as response:
                result = await response.json()

                if not result.get("success", False):
                    error_codes = result.get("error-codes", [])
                    logger.warning(f"hCaptcha xác thực thất bại: {error_codes}")
                    return False

                return True
    except Exception as e:
        logger.error(f"Lỗi khi gọi API hCaptcha: {str(e)}")
        return False


async def verify_custom_captcha(token: str, ip_address: Optional[str] = None) -> bool:
    """
    Xác thực captcha tùy chỉnh (triển khai theo nhu cầu).

    Args:
        token: Custom captcha token
        ip_address: Địa chỉ IP người dùng

    Returns:
        bool: True nếu xác thực thành công, False nếu thất bại
    """
    # Đây là triển khai mẫu, cần cập nhật dựa trên hệ thống captcha tùy chỉnh
    logger.info(f"Xác thực captcha tùy chỉnh cho token: {token[:10]}...")

    # Trong môi trường phát triển, luôn trả về True
    if settings.APP_ENV == "development":
        return True

    # Ví dụ về triển khai, gọi API nội bộ để xác thực token
    custom_verify_url = getattr(settings, "CUSTOM_CAPTCHA_VERIFY_URL", "")

    if not custom_verify_url:
        logger.error("Thiếu CUSTOM_CAPTCHA_VERIFY_URL trong cấu hình")
        return False

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                custom_verify_url, json={"token": token, "ip": ip_address}
            ) as response:
                if response.status != 200:
                    return False

                result = await response.json()
                return result.get("valid", False)
    except Exception as e:
        logger.error(f"Lỗi khi xác thực captcha tùy chỉnh: {str(e)}")
        return False
