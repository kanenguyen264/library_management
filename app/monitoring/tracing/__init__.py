"""
Module truy vết (Tracing) - Theo dõi luồng xử lý của các request qua hệ thống.

Module này cung cấp:
- Theo dõi đường đi của các request từ đầu đến cuối
- Đo thời gian xử lý cho từng khâu trong luồng request
- Phát hiện những điểm nghẽn hiệu năng
- Tạo distributed traces để theo dõi request xuyên service
"""

from app.monitoring.tracing.tracer import (
    Tracer,
    Span,
    SpanKind,
    trace,
    setup_tracer,
    TracingMiddleware,
)

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo tracer mặc định
tracer = Tracer


def init_tracing(app=None, service_name: str = None):
    """
    Khởi tạo hệ thống tracing cho ứng dụng.

    Args:
        app: Ứng dụng FastAPI (tùy chọn)
        service_name: Tên service (nếu None, lấy từ cấu hình)
    """
    if not settings.TRACING_ENABLED:
        logger.info("Tracing đã bị tắt trong cấu hình")
        return False

    try:
        # Lấy tên service từ cấu hình nếu không được cung cấp
        service_name = service_name or settings.SERVICE_NAME

        # Thiết lập tracer
        setup_tracer(service_name=service_name)

        # Đăng ký middleware nếu có app
        if app:
            # Thêm middleware tracing
            exclude_paths = ["/health", "/metrics", "/favicon.ico"]
            app.add_middleware(TracingMiddleware, exclude_paths=exclude_paths)

            # Hooks cho startup và shutdown
            @app.on_event("startup")
            async def startup_tracing():
                # Ghi startup event
                span = Tracer.create_span("app.startup", SpanKind.INTERNAL)
                Tracer.export_span_start(span)
                span.end()
                logger.info("Tracing đã được khởi tạo cho ứng dụng")

        logger.info(f"Đã khởi tạo tracing cho service '{service_name}'")
        return True

    except Exception as e:
        logger.error(f"Lỗi khi khởi tạo tracing: {str(e)}")
        return False


# Export các biến, hàm và class
__all__ = [
    "tracer",
    "init_tracing",
    "Tracer",
    "Span",
    "SpanKind",
    "trace",
    "setup_tracer",
    "TracingMiddleware",
]
