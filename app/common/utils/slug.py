"""
Slug generation and processing utilities.
"""

import re
import unicodedata
from typing import Optional
import random
import string


def generate_slug(text: str, max_length: int = 100) -> str:
    """
    Tạo slug từ text input.

    Args:
        text: Văn bản đầu vào để tạo slug
        max_length: Độ dài tối đa của slug

    Returns:
        Chuỗi slug (lowercase, hyphenated)
    """
    # Chuẩn hóa unicode về dạng tổng hợp
    text = unicodedata.normalize("NFKD", text)

    # Chuyển thành chữ thường
    text = text.lower()

    # Thay thế các ký tự không phải chữ cái hoặc số bằng dấu gạch ngang
    text = re.sub(r"[^\w\s-]", "", text)

    # Thay thế các khoảng trắng bằng dấu gạch ngang
    text = re.sub(r"[\s]+", "-", text)

    # Loại bỏ các dấu gạch ngang liên tiếp
    text = re.sub(r"-+", "-", text)

    # Loại bỏ dấu gạch ngang ở đầu và cuối
    text = text.strip("-")

    # Giới hạn độ dài
    return text[:max_length].rstrip("-")


def generate_unique_slug(
    text: str, check_exists_func, max_length: int = 100, model_id: Optional[int] = None
) -> str:
    """
    Tạo slug duy nhất từ text input.

    Args:
        text: Văn bản đầu vào để tạo slug
        check_exists_func: Hàm kiểm tra xem slug đã tồn tại chưa
        max_length: Độ dài tối đa của slug
        model_id: ID của model hiện tại (để bỏ qua khi kiểm tra trùng lặp)

    Returns:
        Chuỗi slug duy nhất
    """
    # Tạo slug ban đầu
    slug = generate_slug(text, max_length=max_length)

    # Kiểm tra xem slug đã tồn tại chưa
    original_slug = slug
    counter = 1

    # Giới hạn độ dài của slug để thêm suffix nếu cần
    max_original_length = max_length - 10  # Để đủ chỗ cho -number
    if len(original_slug) > max_original_length:
        original_slug = original_slug[:max_original_length]

    # Thử cho đến khi tìm được slug duy nhất
    while check_exists_func(slug, model_id):
        slug = f"{original_slug}-{counter}"
        counter += 1

    return slug


def is_valid_slug(slug: str) -> bool:
    """
    Kiểm tra xem một chuỗi có phải là slug hợp lệ hay không.

    Args:
        slug: Chuỗi cần kiểm tra

    Returns:
        True nếu là slug hợp lệ, False nếu không
    """
    # Một slug hợp lệ chỉ chứa ký tự alphanumeric và dấu gạch ngang
    pattern = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    return bool(re.match(pattern, slug))


def random_slug(length: int = 8) -> str:
    """
    Tạo một slug ngẫu nhiên.

    Args:
        length: Độ dài của slug

    Returns:
        Chuỗi slug ngẫu nhiên
    """
    # Chỉ sử dụng chữ cái thường và số
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))
