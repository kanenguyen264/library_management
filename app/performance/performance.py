"""
Performance utilities for query tracking and monitoring.
"""

from app.performance.profiling import profile_code_block
from app.logging.setup import get_logger
from typing import Dict, Any, Optional

logger = get_logger(__name__)


def query_performance_tracker(
    query_name: str, metadata: Optional[Dict[str, Any]] = None
):
    """
    Context manager để theo dõi hiệu suất của các truy vấn.

    Args:
        query_name: Tên của truy vấn cần theo dõi
        metadata: Thông tin bổ sung về truy vấn (tùy chọn)

    Returns:
        Context manager để theo dõi hiệu suất của truy vấn

    Example:
        ```python
        with query_performance_tracker("find_user", {"user_id": 123}):
            user = await db.query(User).filter(User.id == 123).first()
        ```
    """
    # Log thông tin truy vấn
    if metadata:
        logger.debug(f"Bắt đầu theo dõi truy vấn {query_name} với metadata: {metadata}")
    else:
        logger.debug(f"Bắt đầu theo dõi truy vấn {query_name}")

    # Sử dụng profile_code_block từ profiling module
    return profile_code_block(name=f"query:{query_name}", threshold=0.1)
