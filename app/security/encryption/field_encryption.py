from cryptography.fernet import Fernet, InvalidToken
from typing import Any, Optional, Dict, Union, List, Type, TypeVar
import base64
import os
import json
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.types import TypeDecorator, String, LargeBinary
from sqlalchemy.ext.mutable import MutableDict, MutableList
from app.core.config import get_settings
from pathlib import Path
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

# Type variable for generic functions
T = TypeVar("T")

# Store both current and old keys
ENCRYPTION_KEYS = []
CURRENT_KEY_INDEX = 0


def load_encryption_keys():
    """Load encryption keys from file or environment."""
    global ENCRYPTION_KEYS, CURRENT_KEY_INDEX

    # Clear existing keys
    ENCRYPTION_KEYS = []

    # Try to load from environment variable first
    env_key = os.environ.get("ENCRYPTION_KEY")
    if env_key:
        ENCRYPTION_KEYS.append(env_key.encode())
        CURRENT_KEY_INDEX = 0
        return

    # Check if key file exists
    key_file_path = getattr(
        settings, "KEY_FILE", os.path.join(os.path.dirname(__file__), "keys.txt")
    )
    key_file = Path(key_file_path)
    if key_file.exists():
        with open(key_file, "r") as f:
            keys_data = f.read().strip().split("\n")
            for key in keys_data:
                if key and not key.startswith("#"):
                    ENCRYPTION_KEYS.append(key.encode())

            # The first non-comment line is the current key
            CURRENT_KEY_INDEX = 0

    # Generate new key if none found
    if not ENCRYPTION_KEYS:
        new_key = Fernet.generate_key()
        ENCRYPTION_KEYS.append(new_key)
        CURRENT_KEY_INDEX = 0

        # Save the new key
        key_file.parent.mkdir(parents=True, exist_ok=True)
        with open(key_file, "w") as f:
            f.write(new_key.decode())

        print("Generated new encryption key")


# Initialize keys when module is loaded
load_encryption_keys()


def get_encryption_key():
    """
    Get the current encryption key.

    For backward compatibility with existing code.

    Returns:
        bytes: The current encryption key
    """
    global ENCRYPTION_KEYS, CURRENT_KEY_INDEX

    if not ENCRYPTION_KEYS:
        load_encryption_keys()

    return ENCRYPTION_KEYS[CURRENT_KEY_INDEX]


def get_current_cipher():
    """Get the current Fernet cipher for encryption."""
    if not ENCRYPTION_KEYS:
        load_encryption_keys()
    return Fernet(ENCRYPTION_KEYS[CURRENT_KEY_INDEX])


# For backward compatibility
def get_cipher():
    """Alias for get_current_cipher() for backward compatibility."""
    return get_current_cipher()


def get_all_ciphers():
    """
    Get all available Fernet ciphers.

    Returns a list of all available ciphers, with the current (newest) one first.
    This is used for key rotation - when decrypting, we try the current key first,
    then fall back to older keys if needed.
    """
    global ENCRYPTION_KEYS, CURRENT_KEY_INDEX

    if not ENCRYPTION_KEYS:
        load_encryption_keys()

    ciphers = []

    # Add current key first
    current_key = ENCRYPTION_KEYS[CURRENT_KEY_INDEX]
    if current_key:
        ciphers.append(Fernet(current_key))

    # Add all other keys
    for key in ENCRYPTION_KEYS:
        # Skip the current key as we already added it
        if key == current_key:
            continue
        try:
            ciphers.append(Fernet(key))
        except Exception as e:
            if settings.DEBUG:
                print(f"Error creating cipher with key: {e}")

    return ciphers


def encrypt_sensitive_data(data: T) -> str:
    """Encrypt sensitive data using the current key."""
    if data is None:
        return None

    # Convert to JSON string if not already a string
    if not isinstance(data, str):
        data_str = json.dumps(data)
    else:
        data_str = data

    # Encrypt and return as base64 string
    cipher = get_current_cipher()
    encrypted_data = cipher.encrypt(data_str.encode())
    return base64.b64encode(encrypted_data).decode()


def decrypt_sensitive_data(encrypted_data: str) -> Any:
    """Decrypt sensitive data trying all available keys."""
    if not encrypted_data:
        return None

    # Decode from base64
    binary_data = base64.b64decode(encrypted_data)

    # Try decryption with all available keys
    ciphers = get_all_ciphers()
    last_error = None

    for cipher in ciphers:
        try:
            decrypted_data = cipher.decrypt(binary_data)
            decrypted_str = decrypted_data.decode()

            # Try to parse as JSON first
            try:
                return json.loads(decrypted_str)
            except json.JSONDecodeError:
                # If not valid JSON, return as string
                return decrypted_str
        except Exception as e:
            last_error = e

    # If we get here, all decryption attempts failed
    if settings.DEBUG:
        print(f"Decryption failed: {last_error}")
    return None


def decrypt_sensitive_content(content: str) -> str:
    """
    Giải mã nội dung đã được mã hóa.

    Args:
        content: Nội dung đã mã hóa dưới dạng string

    Returns:
        Nội dung đã được giải mã

    Raises:
        Exception: Nếu không thể giải mã nội dung
    """
    if not content:
        return content

    try:
        cipher = get_current_cipher()
        # Thử giải mã trực tiếp
        if isinstance(content, str):
            try:
                # Kiểm tra xem nội dung có base64 encoded không
                if content.startswith("gAAAAAB"):
                    decrypted_bytes = cipher.decrypt(content.encode())
                else:
                    # Nếu không, giả định nó đã được base64 encoded
                    encrypted_bytes = base64.b64decode(content)
                    decrypted_bytes = cipher.decrypt(encrypted_bytes)

                return decrypted_bytes.decode()
            except Exception:
                # Nếu không thể giải mã trực tiếp, thử giải mã từ base64
                try:
                    encrypted_bytes = base64.b64decode(content)
                    decrypted_bytes = cipher.decrypt(encrypted_bytes)
                    return decrypted_bytes.decode()
                except Exception:
                    # Nếu vẫn không được, trả về nội dung gốc
                    return content
    except Exception as e:
        # Nếu có lỗi trong quá trình giải mã, trả về nội dung gốc
        return content


class EncryptedType(TypeDecorator):
    """SQLAlchemy type for encrypted data."""

    impl = String
    cache_ok = True

    def __init__(self, type_in=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type_in = type_in
        self.json_type = type_in in (dict, list)
        self.is_dict = type_in == dict
        self.is_list = type_in == list

    def process_bind_param(self, value, dialect):
        """Encrypt data before storing in DB."""
        if value is not None:
            # Convert to JSON if needed
            if not isinstance(value, str):
                value = json.dumps(value)

            cipher = get_current_cipher()
            # Encrypt
            encrypted = cipher.encrypt(value.encode())
            return base64.b64encode(encrypted).decode()
        return None

    def _decrypt(self, value):
        """Decrypt value trying all available ciphers."""
        if not value:
            return None

        # Decode from base64
        binary_data = base64.b64decode(value)

        # Try all available ciphers
        for cipher in get_all_ciphers():
            try:
                decrypted = cipher.decrypt(binary_data)
                return decrypted
            except InvalidToken:
                # Try next key
                continue

        # If we get here, no cipher could decrypt the data
        raise InvalidToken("Could not decrypt with any available key")

    def process_result_value(self, value, dialect):
        """Decrypt the value when loading from the database."""
        if value is None:
            return None

        try:
            decrypt_value = self._decrypt(value)
            if isinstance(decrypt_value, bytes):
                decrypt_value = decrypt_value.decode("utf-8")

            if self.json_type:
                try:
                    decrypt_value = json.loads(decrypt_value)
                except (TypeError, json.JSONDecodeError) as e:
                    logger.error(f"Error parsing JSON: {str(e)}")
                    return None

            return decrypt_value
        except InvalidToken:
            # Log more detailed error information to help with debugging
            class_name = self.__class__.__name__
            type_info = f"type_in={self.type_in}" if hasattr(self, "type_in") else ""
            logger.warning(
                f"Error decrypting value with instance of {class_name} [{type_info}]. "
                f"This could indicate an encryption key rotation issue."
            )

            # Return appropriate default value based on expected type
            if self.json_type:
                if self.is_dict:
                    return {}
                elif self.is_list:
                    return []
            return None
        except Exception as e:
            logger.error(f"Error decrypting value: {str(e)}")
            return None


class EncryptedDict(EncryptedType):
    """Type for encrypted dictionary."""

    def __init__(self, **kwargs):
        super(EncryptedDict, self).__init__(type_in=dict, **kwargs)


class EncryptedList(EncryptedType):
    """Type for encrypted list."""

    def __init__(self, **kwargs):
        super(EncryptedList, self).__init__(type_in=list, **kwargs)


class EncryptedString(EncryptedType):
    """Type for encrypted string."""

    def __init__(self, **kwargs):
        super(EncryptedString, self).__init__(**kwargs)


class EncryptedInteger(EncryptedType):
    """Type for encrypted integer."""

    def process_result_value(self, value, dialect):
        """Decrypt and convert to int."""
        decrypted = super().process_result_value(value, dialect)
        if decrypted is not None:
            return int(decrypted)
        return None


class EncryptedMixin:
    """Mixin for models with encrypted fields."""

    @declared_attr
    def __encrypted_fields__(cls):
        """List of fields that should be encrypted."""
        return []

    def __setattr__(self, key, value):
        """Intercept attribute setting to encrypt specified fields."""
        if hasattr(self, "__encrypted_fields__") and key in self.__encrypted_fields__:
            # Apply encryption here if needed for non-SQLAlchemy fields
            pass
        super().__setattr__(key, value)
