"""
Module tối ưu hiệu năng (Performance) - Cung cấp các giải pháp tối ưu hiệu suất cho ứng dụng.

Module này bao gồm:
- Caching Strategies: Các chiến lược cache dữ liệu nhiều tầng và phân tán
- CDN: Quản lý và tối ưu hóa việc phân phối nội dung qua CDN
- DB Optimization: Tối ưu hóa truy vấn, index và pool kết nối cơ sở dữ liệu
- Profiling: Công cụ đo lường và phân tích hiệu năng code và API
- Static Assets: Tối ưu hóa tài nguyên tĩnh như hình ảnh, CSS, JavaScript
"""

# Import các module con
from app.performance import caching_strategies
from app.performance import cdn
from app.performance import db_optimization
from app.performance import profiling
from app.performance import static_assets

# Import các class và hàm chính để dễ sử dụng
from app.performance.caching_strategies import (
    LayeredCache,
    CacheLayer,
    CacheStrategy,
    CacheTier,
    cached,
    DistributedCache,
    InvalidationManager,
    InvalidationStrategy,
)

from app.performance.cdn import CDNManager, CDNProvider

from app.performance.db_optimization import (
    ConnectionPoolManager,
    IndexOptimizer,
    QueryAnalyzer,
    connection_pool_manager,
    get_engine,
)

from app.performance.profiling import (
    APIProfiler,
    CodeProfiler,
    profile_endpoint,
    profile_function,
    profile_memory,
    profile_cpu,
)

from app.performance.static_assets import (
    AssetOptimizer,
    optimize_image,
    optimize_css,
    optimize_js,
)


# Hàm tiện ích để thiết lập module performance
def setup_performance(app=None, db=None):
    """
    Thiết lập và khởi tạo các tính năng tối ưu hiệu năng.

    Args:
        app: Ứng dụng FastAPI (tùy chọn)
        db: Session SQLAlchemy (tùy chọn)
    """
    # Khởi tạo API Profiler nếu có app
    if app:
        profiler = profiling.setup_api_profiler(app)

    # Khởi tạo Connection Pool nếu có db
    if db:
        connection_pool = db_optimization.setup_connection_pool(db)

    # Trả về các instance đã khởi tạo
    return {
        "api_profiler": profiler if app else None,
        "connection_pool": connection_pool if db else None,
    }


# Export danh sách modules và functions
__all__ = [
    "setup_performance",
    "caching_strategies",
    "cdn",
    "db_optimization",
    "profiling",
    "static_assets",
    "LayeredCache",
    "CacheLayer",
    "CacheStrategy",
    "CacheTier",
    "cached",
    "DistributedCache",
    "InvalidationManager",
    "InvalidationStrategy",
    "CDNManager",
    "CDNProvider",
    "ConnectionPoolManager",
    "IndexOptimizer",
    "QueryAnalyzer",
    "connection_pool_manager",
    "get_engine",
    "APIProfiler",
    "CodeProfiler",
    "profile_endpoint",
    "profile_function",
    "profile_memory",
    "profile_cpu",
    "AssetOptimizer",
    "optimize_image",
    "optimize_css",
    "optimize_js",
]
