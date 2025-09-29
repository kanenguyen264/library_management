"""
Module tối ưu cơ sở dữ liệu (DB Optimization) - Cung cấp công cụ tối ưu truy vấn và kết nối.

Module này cung cấp:
- Connection Pool: Quản lý và tối ưu hóa pool kết nối database
- Index Optimizer: Phân tích và đề xuất/tạo indexes để tối ưu truy vấn
- Query Analyzer: Phân tích và tối ưu hóa các câu truy vấn SQL
"""

from app.performance.db_optimization.connection_pool import (
    ConnectionPoolManager,
    connection_pool_manager,
    get_engine,
)

from app.performance.db_optimization.index_optimizer import IndexOptimizer

from app.performance.db_optimization.query_analyzer import (
    QueryAnalyzer,
    QueryOptimizationRecommendation,
    get_query_analyzer as create_query_analyzer,
)

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo singleton instances
_index_optimizer = None
_query_analyzer = None


def get_index_optimizer(db=None):
    """
    Lấy hoặc khởi tạo Index Optimizer.

    Args:
        db: Database session (tùy chọn)

    Returns:
        IndexOptimizer instance
    """
    global _index_optimizer
    if _index_optimizer is None:
        try:
            _index_optimizer = IndexOptimizer(
                enabled=getattr(settings, "DB_INDEX_OPTIMIZER_ENABLED", False),
                auto_create_indexes=getattr(settings, "DB_AUTO_CREATE_INDEXES", False),
                analyze_queries=True,
            )
            logger.info("Đã khởi tạo Index Optimizer")
        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo Index Optimizer: {str(e)}")
            # Tạo optimizer mặc định với tất cả các tính năng bị tắt
            _index_optimizer = IndexOptimizer(
                enabled=False,
                auto_create_indexes=False,
                analyze_queries=False,
            )
            logger.info("Đã khởi tạo Index Optimizer mặc định (disabled)")
    return _index_optimizer


def get_query_analyzer(db=None):
    """
    Lấy hoặc khởi tạo Query Analyzer.

    Args:
        db: Database session (tùy chọn)

    Returns:
        QueryAnalyzer instance
    """
    global _query_analyzer
    if _query_analyzer is None:
        try:
            _query_analyzer = create_query_analyzer(
                db_session=db,
                tracing_enabled=getattr(settings, "TRACING_ENABLED", False),
            )
            logger.info("Đã khởi tạo Query Analyzer")
        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo Query Analyzer: {str(e)}")
            from app.performance.db_optimization.query_analyzer import QueryAnalyzer

            _query_analyzer = QueryAnalyzer()
            logger.info("Đã khởi tạo Query Analyzer mặc định")
    return _query_analyzer


def setup_connection_pool(db=None, **kwargs):
    """
    Thiết lập và cấu hình Connection Pool.

    Args:
        db: Database session (tùy chọn)
        **kwargs: Tham số cấu hình bổ sung

    Returns:
        ConnectionPoolManager instance
    """
    # Lấy connection pool đã được khởi tạo singleton
    pool = connection_pool_manager

    # Khởi tạo engine nếu chưa
    engine = pool.create_engine()

    # Bắt đầu monitoring
    if getattr(settings, "DB_MONITOR_CONNECTIONS", False):
        pool._start_monitoring()
        logger.info("Đã bắt đầu giám sát connection pool")

    return pool


async def analyze_slow_queries(db, limit=10):
    """
    Phân tích các truy vấn chậm trong cơ sở dữ liệu.

    Args:
        db: Database session
        limit: Số lượng truy vấn chậm cần phân tích

    Returns:
        Danh sách phân tích và đề xuất tối ưu
    """
    analyzer = get_query_analyzer(db)
    return await analyzer.get_slow_queries(limit=limit)


async def suggest_indexes(db):
    """
    Đề xuất các index nên được tạo để tối ưu hiệu năng.

    Args:
        db: Database session

    Returns:
        Danh sách index được đề xuất
    """
    optimizer = get_index_optimizer(db)
    return await optimizer.suggest_indexes(db)


def apply_db_optimizations():
    """
    Áp dụng các tối ưu hóa cơ sở dữ liệu khi ứng dụng khởi động.

    Thực hiện:
    - Cấu hình connection pool
    - Thiết lập index optimizer
    - Thiết lập query analyzer

    Returns:
        bool: True nếu tối ưu hóa thành công
    """
    try:
        # Thiết lập connection pool
        pool = setup_connection_pool()
        logger.info("Đã thiết lập connection pool")

        # Khởi tạo các optimizer
        get_index_optimizer()
        get_query_analyzer()

        logger.info("Áp dụng tối ưu hóa DB thành công")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi áp dụng tối ưu hóa DB: {str(e)}")
        return False


# Export các components
__all__ = [
    "ConnectionPoolManager",
    "connection_pool_manager",
    "get_engine",
    "IndexOptimizer",
    "QueryAnalyzer",
    "QueryOptimizationRecommendation",
    "get_index_optimizer",
    "get_query_analyzer",
    "setup_connection_pool",
    "analyze_slow_queries",
    "suggest_indexes",
    "apply_db_optimizations",
]
