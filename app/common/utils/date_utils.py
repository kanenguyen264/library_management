"""
Date and time utility functions.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Union


def now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def format_date(date: datetime, format_str: str = "%Y-%m-%d") -> str:
    """Format a datetime object to string."""
    return date.strftime(format_str)


def parse_date(date_str: str, format_str: str = "%Y-%m-%d") -> Optional[datetime]:
    """Parse a string to datetime object."""
    try:
        return datetime.strptime(date_str, format_str)
    except ValueError:
        return None


def add_days(date: datetime, days: int) -> datetime:
    """Add days to a datetime."""
    return date + timedelta(days=days)


def date_diff_days(date1: datetime, date2: datetime) -> int:
    """Calculate difference in days between two dates."""
    delta = date2 - date1
    return delta.days
