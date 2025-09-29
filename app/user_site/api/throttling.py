from functools import wraps
from typing import Callable, Optional
import time
import logging
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def throttle_requests(
    max_requests: int = 60,
    window_seconds: Optional[int] = None,
    per_seconds: Optional[int] = None,
    action: Optional[str] = None,
    limit: Optional[int] = None,
    period: Optional[int] = None,
):
    """
    Decorator để giới hạn số lượng request cho một endpoint.
    Hỗ trợ cả hai format parameter:
    - max_requests + window_seconds/per_seconds (format mới)
    - action + limit + period (format cũ)

    Args:
        max_requests: Số lượng request tối đa trong khoảng thời gian
        window_seconds: Khoảng thời gian tính bằng giây
        per_seconds: Alias cho window_seconds để tương thích với các file khác
        action: Tên hành động cần giới hạn (dành cho format cũ)
        limit: Số lượng request tối đa (dành cho format cũ)
        period: Khoảng thời gian tính bằng giây (dành cho format cũ)
    """

    # Xác định các tham số dựa trên cả hai format
    def resolve_parameters():
        nonlocal action, limit, period

        # Xác định cửa sổ thời gian từ window_seconds hoặc per_seconds
        time_window = window_seconds or per_seconds or 3600

        # Chuyển đổi format mới sang format cũ
        actual_action = action or f"throttle_{time.time()}"
        actual_limit = limit or max_requests
        actual_period = period or time_window

        return actual_action, actual_limit, actual_period

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Import các dependencies tại đây để tránh circular import
            from app.common.db.session import get_db
            from app.user_site.api.deps import get_current_active_user
            from app.user_site.models.user import User
            from app.user_site.services.auth_service import AuthService

            request = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            current_user = kwargs.get("current_user")
            if not current_user:
                for arg in args:
                    if isinstance(arg, User):
                        current_user = arg
                        break

            db = kwargs.get("db")
            if not db:
                for arg in args:
                    if isinstance(arg, AsyncSession):
                        db = arg
                        break

            # Nếu không có db hoặc current_user, lấy từ dependency
            if not db:
                db = await get_db()

            if not current_user:
                current_user = await get_current_active_user(db=db)

            # Lấy các tham số đã được xử lý
            actual_action, actual_limit, actual_period = resolve_parameters()

            # Kiểm tra giới hạn request
            auth_service = AuthService(db)
            client_ip = request.client.host if request else None

            current_count, time_reset = await auth_service.check_rate_limit(
                user_id=current_user.id,
                action=actual_action,
                limit=actual_limit,
                period=actual_period,
                ip=client_ip,
            )

            # Nếu vượt quá giới hạn
            if current_count > actual_limit:
                # Tính thời gian còn lại để reset giới hạn
                retry_after = time_reset - int(time.time())
                if retry_after < 0:
                    retry_after = actual_period

                logger.warning(
                    f"Rate limit exceeded: User {current_user.id} for action {actual_action}. "
                    f"Count: {current_count}/{actual_limit}, Reset in {retry_after}s"
                )

                from app.core.exceptions import RateLimitException

                raise RateLimitException(
                    detail=f"Vượt quá giới hạn cho phép. Vui lòng thử lại sau.",
                    retry_after=retry_after,
                )

            # Gọi hàm gốc nếu không vượt quá giới hạn
            return await func(*args, **kwargs)

        return wrapper

    return decorator
