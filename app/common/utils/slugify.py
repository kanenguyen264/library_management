"""
Slugify utilities for text conversion.
"""

import re
import unicodedata
from typing import Optional, Dict
import string
import random

# Ánh xạ dấu tiếng Việt sang không dấu
vietnamese_map = {
    "à": "a",
    "á": "a",
    "ả": "a",
    "ã": "a",
    "ạ": "a",
    "ă": "a",
    "ằ": "a",
    "ắ": "a",
    "ẳ": "a",
    "ẵ": "a",
    "ặ": "a",
    "â": "a",
    "ầ": "a",
    "ấ": "a",
    "ẩ": "a",
    "ẫ": "a",
    "ậ": "a",
    "đ": "d",
    "è": "e",
    "é": "e",
    "ẻ": "e",
    "ẽ": "e",
    "ẹ": "e",
    "ê": "e",
    "ề": "e",
    "ế": "e",
    "ể": "e",
    "ễ": "e",
    "ệ": "e",
    "ì": "i",
    "í": "i",
    "ỉ": "i",
    "ĩ": "i",
    "ị": "i",
    "ò": "o",
    "ó": "o",
    "ỏ": "o",
    "õ": "o",
    "ọ": "o",
    "ô": "o",
    "ồ": "o",
    "ố": "o",
    "ổ": "o",
    "ỗ": "o",
    "ộ": "o",
    "ơ": "o",
    "ờ": "o",
    "ớ": "o",
    "ở": "o",
    "ỡ": "o",
    "ợ": "o",
    "ù": "u",
    "ú": "u",
    "ủ": "u",
    "ũ": "u",
    "ụ": "u",
    "ư": "u",
    "ừ": "u",
    "ứ": "u",
    "ử": "u",
    "ữ": "u",
    "ự": "u",
    "ỳ": "y",
    "ý": "y",
    "ỷ": "y",
    "ỹ": "y",
    "ỵ": "y",
}


def slugify(text: str, max_length: int = 100, separator: str = "-") -> str:
    """
    Chuyển đổi text thành slug (dạng URL-friendly).

    Args:
        text: Văn bản cần chuyển đổi
        max_length: Độ dài tối đa của slug
        separator: Ký tự phân cách (mặc định là dấu gạch ngang)

    Returns:
        Chuỗi slug
    """
    # Thay thế các ký tự tiếng Việt
    for key, value in vietnamese_map.items():
        text = text.replace(key, value)
        text = text.replace(key.upper(), value.upper())

    # Chuẩn hóa unicode
    text = unicodedata.normalize("NFKD", text)

    # Chuyển thành chữ thường
    text = text.lower()

    # Xóa ký tự không phải chữ cái, số hoặc ký tự phân cách
    text = re.sub(r"[^\w\s-]", "", text)

    # Thay thế khoảng trắng bằng ký tự phân cách
    text = re.sub(r"[\s_-]+", separator, text)

    # Xóa ký tự phân cách ở đầu và cuối
    text = text.strip(separator)

    # Giới hạn độ dài
    if max_length and len(text) > max_length:
        text = text[:max_length].rstrip(separator)

    return text


def slugify_unicode(text: str, max_length: int = 100) -> str:
    """
    Phiên bản của slugify bảo toàn các ký tự unicode.

    Args:
        text: Văn bản cần chuyển đổi
        max_length: Độ dài tối đa của slug

    Returns:
        Chuỗi slug
    """
    # Chuyển thành chữ thường
    text = text.lower()

    # Loại bỏ ký tự đặc biệt
    text = re.sub(r"[^\w\s-]", "", text)

    # Thay thế khoảng trắng bằng dấu gạch ngang
    text = re.sub(r"[\s]+", "-", text)

    # Loại bỏ các dấu gạch ngang liên tiếp
    text = re.sub(r"-+", "-", text)

    # Loại bỏ dấu gạch ngang ở đầu và cuối
    text = text.strip("-")

    # Giới hạn độ dài
    if max_length and len(text) > max_length:
        text = text[:max_length].rstrip("-")

    return text


def slugify_filename(filename: str) -> str:
    """
    Tạo tên file an toàn từ tên file đầu vào.

    Args:
        filename: Tên file cần chuyển đổi

    Returns:
        Tên file an toàn
    """
    # Tách phần tên và phần mở rộng
    name, ext = "", ""
    if "." in filename:
        parts = filename.rsplit(".", 1)
        name, ext = parts[0], parts[1]
    else:
        name = filename

    # Slugify phần tên
    name = slugify(name)

    # Loại bỏ ký tự đặc biệt từ phần mở rộng
    ext = re.sub(r"[^\w]", "", ext)

    # Tạo tên file mới
    if ext:
        return f"{name}.{ext}"
    return name
