"""
Module mã hóa (Encryption) - Cung cấp các giải pháp mã hóa dữ liệu và lưu trữ.

Module này cung cấp:
- Mã hóa trường dữ liệu trong cơ sở dữ liệu
- Mã hóa file và dữ liệu lưu trữ
- Các loại dữ liệu mã hóa cho SQLAlchemy
"""

from app.security.encryption.field_encryption import (
    EncryptedType,
    EncryptedDict,
    EncryptedList,
    EncryptedString,
    EncryptedInteger,
    EncryptedMixin,
    get_cipher,
    get_encryption_key,
    encrypt_sensitive_data,
    decrypt_sensitive_data,
    decrypt_sensitive_content,
)

from app.security.encryption.storage_encryption import FileEncryption

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo singleton FileEncryption
_file_encryption = None


def get_file_encryption():
    """
    Lấy hoặc khởi tạo singleton FileEncryption.

    Returns:
        FileEncryption instance
    """
    global _file_encryption
    if _file_encryption is None:
        _file_encryption = FileEncryption()
        logger.info("Đã khởi tạo File Encryption")

    return _file_encryption


def encrypt_file(input_file, output_file=None):
    """
    Mã hóa một file.

    Args:
        input_file: Đường dẫn file hoặc file-like object
        output_file: Đường dẫn file output (tùy chọn)

    Returns:
        Đường dẫn file đã mã hóa
    """
    encryption = get_file_encryption()
    return encryption.encrypt_file(input_file, output_file)


def decrypt_file(input_file, output_file=None):
    """
    Giải mã một file.

    Args:
        input_file: Đường dẫn file hoặc file-like object
        output_file: Đường dẫn file output (tùy chọn)

    Returns:
        Đường dẫn file đã giải mã
    """
    encryption = get_file_encryption()
    return encryption.decrypt_file(input_file, output_file)


# Export các components
__all__ = [
    "EncryptedType",
    "EncryptedDict",
    "EncryptedList",
    "EncryptedString",
    "EncryptedInteger",
    "EncryptedMixin",
    "get_cipher",
    "get_encryption_key",
    "FileEncryption",
    "get_file_encryption",
    "encrypt_file",
    "decrypt_file",
    "encrypt_sensitive_data",
    "decrypt_sensitive_data",
    "decrypt_sensitive_content",
]
