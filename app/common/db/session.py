"""
Session handling for database operations.
This module provides compatibility with code that imports get_db.
"""

from app.core.db import get_session

# Compatible with legacy code
get_db = get_session
