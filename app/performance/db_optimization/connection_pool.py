from typing import Dict, List, Any, Optional, Tuple, Union
import logging
import time
import asyncio
import threading
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.pool import QueuePool
from prometheus_client import Gauge, Histogram, Counter
from contextlib import contextmanager

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

try:
    ASYNC_SQLALCHEMY_AVAILABLE = True
except ImportError:
    ASYNC_SQLALCHEMY_AVAILABLE = False

    # Mock classes
    def create_async_engine(*args, **kwargs):
        raise ImportError("sqlalchemy.ext.asyncio không được cài đặt")

    class AsyncSession:
        pass


# Prometheus metrics
DB_POOL_SIZE = Gauge(
    "db_pool_size", "Kích thước pool kết nối cơ sở dữ liệu", ["database", "pool_type"]
)

DB_POOL_CONNECTIONS = Gauge(
    "db_pool_connections",
    "Số lượng kết nối trong pool",
    ["database", "status"],  # status: in_use, available, overflow
)

DB_CONNECTION_TIME = Histogram(
    "db_connection_time_seconds",
    "Thời gian lấy kết nối từ pool",
    ["database"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
)

DB_CONNECTION_ERRORS = Counter(
    "db_connection_errors", "Số lỗi kết nối cơ sở dữ liệu", ["database", "error_type"]
)


class ConnectionPoolManager:
    """
    Quản lý pool kết nối cơ sở dữ liệu.
    Cung cấp:
    - Giám sát và thu thập metrics của pool
    - Tối ưu kích thước pool dựa trên tải
    - Theo dõi thời gian chờ kết nối
    - Xử lý các kết nối treo (stale connections)
    """

    def __init__(
        self,
        pool_size: Optional[int] = None,
        max_overflow: Optional[int] = None,
        pool_timeout: Optional[float] = None,
        pool_recycle: Optional[int] = None,
        pool_pre_ping: bool = True,
        auto_adjust: bool = True,
        check_interval: int = 60,
        connection_timeout_threshold: float = 0.5,
        database_url: Optional[str] = None,
    ):
        """
        Khởi tạo connection pool manager.

        Args:
            pool_size: Kích thước pool cơ bản
            max_overflow: Số kết nối tối đa vượt quá pool_size
            pool_timeout: Thời gian timeout lấy kết nối (giây)
            pool_recycle: Thời gian tái sử dụng kết nối (giây)
            pool_pre_ping: Kiểm tra kết nối trước khi sử dụng
            auto_adjust: Tự động điều chỉnh kích thước pool
            check_interval: Khoảng thời gian kiểm tra pool (giây)
            connection_timeout_threshold: Ngưỡng cảnh báo thời gian lấy kết nối
            database_url: URL kết nối cơ sở dữ liệu
        """
        # Database connection settings
        self.database_url = database_url or getattr(
            settings, "DATABASE_URL", "postgresql://localhost/db"
        )
        self.database_name = self._extract_db_name(self.database_url)

        # Pool parameters with defaults from settings
        self.pool_size = pool_size or getattr(settings, "DATABASE_POOL_SIZE", 20)
        self.max_overflow = max_overflow or getattr(
            settings, "DATABASE_MAX_OVERFLOW", 10
        )
        self.pool_timeout = pool_timeout or 30.0  # 30 seconds default
        self.pool_recycle = pool_recycle or 1800  # 30 minutes default
        self.pool_pre_ping = pool_pre_ping

        # Pool management
        self.auto_adjust = auto_adjust
        self.check_interval = check_interval
        self.connection_timeout_threshold = connection_timeout_threshold

        # Stats tracking
        self.connection_times = []
        self.max_connection_time = 0
        self.connection_errors = 0
        self.last_adjustment_time = time.time()
        self.peak_connection_usage = 0

        # Engine instance
        self.engine = None

        # Periodic task
        self._stop_event = threading.Event()
        self._monitor_task = None

        logger.info(
            f"Khởi tạo connection pool với size={self.pool_size}, "
            f"max_overflow={self.max_overflow}, timeout={self.pool_timeout}s"
        )

    def _extract_db_name(self, url: str) -> str:
        """
        Trích xuất tên cơ sở dữ liệu từ URL.

        Args:
            url: Database URL

        Returns:
            Tên cơ sở dữ liệu
        """
        try:
            # Extract database name from URL
            parts = url.split("/")
            return parts[-1].split("?")[0]
        except Exception:
            return "unknown"

    def create_engine(self) -> AsyncEngine:
        """
        Tạo và cấu hình SQLAlchemy engine với pool kết nối được tối ưu.

        Returns:
            SQLAlchemy AsyncEngine
        """
        if self.engine:
            return self.engine

        try:
            # Đảm bảo database_url là string
            db_url = (
                str(self.database_url)
                if not isinstance(self.database_url, str)
                else self.database_url
            )

            self.engine = create_async_engine(
                db_url,
                echo=getattr(settings, "DEBUG", False),
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=self.pool_pre_ping,
                connect_args={
                    "server_settings": {"application_name": "api_readingbook"}
                },
            )

            # Khởi tạo metrics
            DB_POOL_SIZE.labels(database=self.database_name, pool_type="base").set(
                self.pool_size
            )

            DB_POOL_SIZE.labels(database=self.database_name, pool_type="overflow").set(
                self.max_overflow
            )

            # Bắt đầu monitoring nếu được cấu hình
            if self.auto_adjust:
                self._start_monitoring()

            logger.info(f"Đã tạo SQLAlchemy engine với pool size {self.pool_size}")
            return self.engine

        except Exception as e:
            logger.error(f"Lỗi khi tạo SQLAlchemy engine: {str(e)}")
            DB_CONNECTION_ERRORS.labels(
                database=self.database_name, error_type="engine_creation"
            ).inc()
            raise

    async def _get_pool_stats(self) -> Dict[str, Any]:
        """
        Lấy thống kê hiện tại của connection pool.

        Returns:
            Dict chứa thống kê của pool
        """
        if not self.engine:
            return {}

        try:
            # Get pool from engine
            pool = self.engine.pool

            # Get stats
            size = pool.size()
            checkedin = pool.checkedin()
            checkedout = pool.checkedout()
            overflow = pool.overflow()

            # Update metrics
            DB_POOL_CONNECTIONS.labels(
                database=self.database_name, status="in_use"
            ).set(checkedout)

            DB_POOL_CONNECTIONS.labels(
                database=self.database_name, status="available"
            ).set(checkedin)

            DB_POOL_CONNECTIONS.labels(
                database=self.database_name, status="overflow"
            ).set(overflow)

            # Track peak usage
            self.peak_connection_usage = max(
                self.peak_connection_usage, checkedout + overflow
            )

            return {
                "size": size,
                "checkedin": checkedin,
                "checkedout": checkedout,
                "overflow": overflow,
                "total": checkedin + checkedout + overflow,
                "utilization": (checkedout / size) if size > 0 else 0,
            }

        except Exception as e:
            logger.error(f"Lỗi khi lấy thống kê pool: {str(e)}")
            return {}

    async def _monitor_pool(self) -> None:
        """Task định kỳ để giám sát và điều chỉnh connection pool."""
        try:
            # Get current pool stats
            stats = await self._get_pool_stats()

            if not stats:
                return

            # Log current stats
            logger.debug(
                f"Thống kê pool: {stats['checkedout']}/{stats['size']} kết nối đang sử dụng, "
                f"{stats['overflow']} kết nối overflow, "
                f"utilization: {stats['utilization']:.2%}"
            )

            # Check if we need to adjust the pool size
            current_time = time.time()
            if (
                self.auto_adjust and (current_time - self.last_adjustment_time) > 300
            ):  # 5 minutes
                utilization = stats["utilization"]
                overflow = stats["overflow"]

                # If utilization is high with overflow, increase pool size
                if utilization > 0.8 and overflow > 0:
                    new_pool_size = min(self.pool_size + 5, 50)  # Limit to 50
                    if new_pool_size > self.pool_size:
                        logger.info(
                            f"Tăng kích thước pool từ {self.pool_size} lên {new_pool_size} "
                            f"(utilization: {utilization:.2%}, overflow: {overflow})"
                        )
                        self.pool_size = new_pool_size
                        self.last_adjustment_time = current_time

                        # Update metrics
                        DB_POOL_SIZE.labels(
                            database=self.database_name, pool_type="base"
                        ).set(self.pool_size)

                # If utilization is low for a while, decrease pool size
                elif utilization < 0.3 and self.pool_size > 10 and overflow == 0:
                    new_pool_size = max(self.pool_size - 5, 10)  # Minimum 10
                    if new_pool_size < self.pool_size:
                        logger.info(
                            f"Giảm kích thước pool từ {self.pool_size} xuống {new_pool_size} "
                            f"(utilization: {utilization:.2%})"
                        )
                        self.pool_size = new_pool_size
                        self.last_adjustment_time = current_time

                        # Update metrics
                        DB_POOL_SIZE.labels(
                            database=self.database_name, pool_type="base"
                        ).set(self.pool_size)

            # Check for slow connection acquisitions
            if self.connection_times:
                avg_time = sum(self.connection_times) / len(self.connection_times)
                if avg_time > self.connection_timeout_threshold:
                    logger.warning(
                        f"Thời gian lấy kết nối DB cao: {avg_time:.4f}s "
                        f"(max: {self.max_connection_time:.4f}s)"
                    )

                # Reset tracking
                self.connection_times = []
                self.max_connection_time = 0

        except Exception as e:
            logger.error(f"Lỗi khi giám sát connection pool: {str(e)}")

    def _start_monitoring(self) -> None:
        """Bắt đầu task giám sát connection pool."""
        if self._monitor_task is not None:
            return

        async def monitor_loop():
            while not self._stop_event.is_set():
                await self._monitor_pool()
                await asyncio.sleep(self.check_interval)

        # Start the monitoring task
        try:
            # Kiểm tra nếu đang trong event loop
            if asyncio.get_event_loop().is_running():
                self._monitor_task = asyncio.create_task(monitor_loop())
                logger.info(
                    f"Đã bắt đầu giám sát connection pool (interval: {self.check_interval}s)"
                )
            else:
                logger.warning("Không thể bắt đầu giám sát pool: event loop không chạy")
        except RuntimeError as e:
            logger.warning(f"Không thể bắt đầu giám sát pool: {str(e)}")
        except Exception as e:
            logger.error(f"Lỗi khi bắt đầu giám sát pool: {str(e)}")

    def stop_monitoring(self) -> None:
        """Dừng task giám sát connection pool."""
        self._stop_event.set()
        logger.info("Đã dừng giám sát connection pool")

    @contextmanager
    def track_connection_time(self):
        """
        Context manager để theo dõi thời gian lấy kết nối.

        Yields:
            Context manager
        """
        start_time = time.time()
        try:
            yield
        finally:
            connection_time = time.time() - start_time

            # Record metrics
            DB_CONNECTION_TIME.labels(database=self.database_name).observe(
                connection_time
            )

            # Track for monitoring
            self.connection_times.append(connection_time)
            self.max_connection_time = max(self.max_connection_time, connection_time)

            # Log slow connections
            if connection_time > self.connection_timeout_threshold:
                logger.warning(f"Lấy kết nối DB chậm: {connection_time:.4f}s")


# Tạo singleton instance
connection_pool_manager = ConnectionPoolManager()


# Hàm tiện ích để lấy engine
def get_engine() -> AsyncEngine:
    """
    Lấy SQLAlchemy engine đã được tối ưu.

    Returns:
        SQLAlchemy AsyncEngine
    """
    return connection_pool_manager.create_engine()
