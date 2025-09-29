"""
Strategy vô hiệu hóa cache dựa trên thời gian.

Chiến lược này tự động vô hiệu hóa cache sau một khoảng thời gian nhất định,
hoặc theo lịch cụ thể (ví dụ: vào cuối ngày, đầu tuần, v.v.)
"""

from datetime import datetime, timedelta
import asyncio
import threading
import time
from typing import Dict, List, Any, Optional, Union, Set, Tuple, Callable
import croniter  # For cron schedule parsing

from app.logging.setup import get_logger
from app.cache.manager import cache_manager

logger = get_logger(__name__)


class TimeBasedStrategy:
    """
    Strategy vô hiệu hóa cache dựa trên thời gian.

    Cho phép tự động vô hiệu hóa cache sau một khoảng thời gian nhất định,
    hoặc theo lịch cụ thể (ví dụ: vào cuối ngày, đầu tuần, v.v.)
    """

    def __init__(
        self,
        namespace: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        interval_seconds: Optional[
            int
        ] = None,  # Khoảng thời gian giữa các lần vô hiệu hóa
        cron_expression: Optional[str] = None,  # Biểu thức cron cho lịch vô hiệu hóa
        auto_start: bool = False,  # Tự động bắt đầu thread vô hiệu hóa
    ):
        """
        Khởi tạo strategy vô hiệu hóa dựa trên thời gian.

        Args:
            namespace: Namespace cần vô hiệu hóa
            patterns: Danh sách pattern cần vô hiệu hóa
            tags: Danh sách tags cần vô hiệu hóa
            interval_seconds: Khoảng thời gian giữa các lần vô hiệu hóa (giây)
            cron_expression: Biểu thức cron cho lịch vô hiệu hóa
            auto_start: Tự động bắt đầu thread vô hiệu hóa
        """
        self.namespace = namespace
        self.patterns = patterns or ["*"]
        self.tags = tags
        self.interval_seconds = interval_seconds
        self.cron_expression = cron_expression
        self._stop_event = threading.Event()

        # Bắt đầu thread vô hiệu hóa nếu cần
        if auto_start:
            self.start()

    def start(self) -> None:
        """
        Bắt đầu thread vô hiệu hóa.
        """
        if self.interval_seconds:
            thread = threading.Thread(target=self._invalidate_interval)
            thread.daemon = True
            thread.start()

        elif self.cron_expression:
            thread = threading.Thread(target=self._invalidate_cron)
            thread.daemon = True
            thread.start()

    def stop(self) -> None:
        """
        Dừng thread vô hiệu hóa.
        """
        self._stop_event.set()

    def _invalidate_interval(self) -> None:
        """
        Vô hiệu hóa cache theo khoảng thời gian.
        """
        while not self._stop_event.is_set():
            # Chờ đến thời điểm kế tiếp
            for _ in range(self.interval_seconds):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

            # Vô hiệu hóa cache
            self._perform_invalidation()

    def _invalidate_cron(self) -> None:
        """
        Vô hiệu hóa cache theo lịch cron.
        """
        try:
            import pytz

            # Lịch vô hiệu hóa
            tz = pytz.timezone("Asia/Ho_Chi_Minh")  # Timezone Việt Nam
            base = datetime.now(tz)
            iter = croniter(self.cron_expression, base)

            while not self._stop_event.is_set():
                # Thời điểm vô hiệu hóa kế tiếp
                next_time = iter.get_next(datetime)

                # Tính thời gian chờ (giây)
                now = datetime.now(tz)
                wait_seconds = (next_time - now).total_seconds()

                # Chờ đến thời điểm kế tiếp
                for _ in range(int(wait_seconds)):
                    if self._stop_event.is_set():
                        return
                    time.sleep(1)

                # Vô hiệu hóa cache
                self._perform_invalidation()

        except ImportError:
            logger.error("Cần cài đặt croniter và pytz để sử dụng cron invalidation")

    def _perform_invalidation(self) -> None:
        """
        Thực hiện vô hiệu hóa cache.
        """
        # Tạo event loop mới nếu cần
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Vô hiệu hóa theo namespace
        if self.namespace:
            asyncio.run(cache_manager.invalidate_namespace(self.namespace))
            logger.info(f"Đã vô hiệu hóa namespace: {self.namespace}")

        # Vô hiệu hóa theo patterns
        if self.patterns:
            for pattern in self.patterns:
                count = asyncio.run(cache_manager.clear(pattern, self.namespace))
                logger.info(f"Đã vô hiệu hóa {count} keys theo pattern: {pattern}")

        # Vô hiệu hóa theo tags
        if self.tags:
            count = asyncio.run(cache_manager.invalidate_by_tags(self.tags))
            logger.info(
                f"Đã vô hiệu hóa {count} keys theo tags: {', '.join(self.tags)}"
            )

    def schedule_one_time(self, delay_seconds: int = 0) -> None:
        """
        Lập lịch vô hiệu hóa một lần sau một khoảng thời gian.

        Args:
            delay_seconds: Thời gian chờ trước khi vô hiệu hóa (giây)
        """

        def delayed_invalidation():
            time.sleep(delay_seconds)
            self._perform_invalidation()

        thread = threading.Thread(target=delayed_invalidation)
        thread.daemon = True
        thread.start()

    @classmethod
    def create_daily(
        cls,
        hour: int = 0,
        minute: int = 0,
        namespace: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        auto_start: bool = True,
    ) -> "TimeBasedStrategy":
        """
        Tạo strategy vô hiệu hóa hàng ngày.

        Args:
            hour: Giờ vô hiệu hóa (0-23)
            minute: Phút vô hiệu hóa (0-59)
            namespace: Namespace cần vô hiệu hóa
            patterns: Danh sách pattern cần vô hiệu hóa
            tags: Danh sách tags cần vô hiệu hóa
            auto_start: Tự động bắt đầu thread vô hiệu hóa

        Returns:
            TimeBasedStrategy instance
        """
        cron = f"{minute} {hour} * * *"  # Mỗi ngày vào giờ, phút chỉ định
        return cls(
            namespace=namespace,
            patterns=patterns,
            tags=tags,
            cron_expression=cron,
            auto_start=auto_start,
        )

    @classmethod
    def create_weekly(
        cls,
        day_of_week: int = 0,  # 0 = Thứ Hai, 6 = Chủ Nhật
        hour: int = 0,
        minute: int = 0,
        namespace: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        auto_start: bool = True,
    ) -> "TimeBasedStrategy":
        """
        Tạo strategy vô hiệu hóa hàng tuần.

        Args:
            day_of_week: Ngày trong tuần (0 = Thứ Hai, 6 = Chủ Nhật)
            hour: Giờ vô hiệu hóa (0-23)
            minute: Phút vô hiệu hóa (0-59)
            namespace: Namespace cần vô hiệu hóa
            patterns: Danh sách pattern cần vô hiệu hóa
            tags: Danh sách tags cần vô hiệu hóa
            auto_start: Tự động bắt đầu thread vô hiệu hóa

        Returns:
            TimeBasedStrategy instance
        """
        # Chuyển đổi từ 0-6 (Thứ Hai - Chủ Nhật) sang 1-7 (cron format)
        dow = (day_of_week % 7) + 1
        cron = f"{minute} {hour} * * {dow}"  # Mỗi tuần vào ngày, giờ, phút chỉ định
        return cls(
            namespace=namespace,
            patterns=patterns,
            tags=tags,
            cron_expression=cron,
            auto_start=auto_start,
        )
