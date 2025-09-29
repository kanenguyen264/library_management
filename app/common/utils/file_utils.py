"""
File operation utilities.
"""

import os
import shutil
import mimetypes
from typing import Optional, List, Tuple


def get_file_extension(filename: str) -> str:
    """
    Get the extension of a file.

    Args:
        filename: Name of the file

    Returns:
        The file extension without the dot
    """
    return os.path.splitext(filename)[1][1:].lower()


def get_mime_type(filename: str) -> str:
    """
    Get the MIME type of a file based on its extension.

    Args:
        filename: Name of the file

    Returns:
        The MIME type or 'application/octet-stream' if unknown
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def ensure_directory_exists(directory_path: str) -> None:
    """
    Create directory if it doesn't exist.

    Args:
        directory_path: Path to the directory
    """
    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)


def list_files(
    directory_path: str, extensions: Optional[List[str]] = None
) -> List[str]:
    """
    List all files in a directory, optionally filtering by extensions.

    Args:
        directory_path: Path to the directory
        extensions: List of extensions to filter by (without the dot)

    Returns:
        List of filenames
    """
    if not os.path.exists(directory_path):
        return []

    files = []
    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        if os.path.isfile(file_path):
            if extensions is None or get_file_extension(filename) in extensions:
                files.append(filename)
    return files


def safe_delete_file(file_path: str) -> bool:
    """
    Safely delete a file if it exists.

    Args:
        file_path: Path to the file

    Returns:
        True if file was deleted, False otherwise
    """
    if os.path.exists(file_path) and os.path.isfile(file_path):
        os.remove(file_path)
        return True
    return False
