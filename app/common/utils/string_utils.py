"""
String manipulation utility functions.
"""

import re
import string
import random
from typing import Optional


def slugify(text: str) -> str:
    """
    Convert text to slug format (lowercase, hyphens instead of spaces, alphanumeric chars only).
    """
    # Convert to lowercase
    text = text.lower()
    # Replace spaces with hyphens
    text = re.sub(r"\s+", "-", text)
    # Remove non-alphanumeric characters
    text = re.sub(r"[^a-z0-9\-]", "", text)
    # Remove duplicate hyphens
    text = re.sub(r"\-+", "-", text)
    # Remove leading/trailing hyphens
    return text.strip("-")


def truncate(text: str, length: int, suffix: str = "...") -> str:
    """
    Truncate text to specified length and add suffix if truncated.
    """
    if len(text) <= length:
        return text
    return text[:length].rstrip() + suffix


def generate_random_string(length: int = 10) -> str:
    """
    Generate a random string of specified length.
    """
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def is_valid_email(email: str) -> bool:
    """
    Check if string is a valid email address.
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))
