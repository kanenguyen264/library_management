from typing import Dict, List, Any, Optional, Union, Set, Tuple, Callable
import logging
import time
import uuid
import threading
import contextvars
import asyncio
from functools import wraps
from enum import Enum

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Context variables cho distributed tracing
TRACE_ID = contextvars.ContextVar("trace_id", default=None)
SPAN_ID = contextvars.ContextVar("span_id", default=None)
PARENT_SPAN_ID = contextvars.ContextVar("parent_span_id", default=None)

class SpanKind(str, Enum):
    """Loại span."""
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"
    INTERNAL = "internal"

class Span:
    """
    Span cho distributed tracing.
    Đại diện cho một đơn vị công việc trong hệ thống.
    """
    
    def __init__(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
        start_time: Optional[float] = None
    ):
        """
        Khởi tạo span.
        
        Args:
            name: Tên span
            kind: Loại span
            trace_id: ID trace
            parent_span_id: ID span cha
            attributes: Thuộc tính của span
            start_time: Thời gian bắt đầu (epoch seconds)
        """
        # Thông tin span
        self.name = name
        self.kind = kind
        
        # IDs
        self.trace_id = trace_id or TRACE_ID.get() or str(uuid.uuid4())
        self.span_id = str(uuid.uuid4())
        self.parent_span_id = parent_span_id or PARENT_SPAN_ID.get()
        
        # Thời gian
        self.start_time = start_time or time.time()
        self.end_time = None
        self.duration = None
        
        # Thuộc tính
        self.attributes = attributes or {}
        
        # Trạng thái
        self.status_code = None
        self.status_message = None
        self.is_recording = True
        
        # Events
        self.events = []
        
        # Links
        self.links = []
        
    def __enter__(self):
        """Context manager entry."""
        # Lưu trữ context
        self._token_trace_id = TRACE_ID.set(self.trace_id)
        self._token_span_id = SPAN_ID.set(self.span_id)
        self._token_parent_span_id = PARENT_SPAN_ID.set(self.span_id)  # Current span becomes parent
        
        # Export span bắt đầu
        Tracer.export_span_start(self)
        
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # Ghi nhận exception
        if exc_type is not None:
            self.record_exception(exc_val, attributes={
                "exception.type": exc_type.__name__,
                "exception.message": str(exc_val)
            })
            self.set_status("ERROR", str(exc_val))
            
        # Kết thúc span
        self.end()
        
        # Khôi phục context
        TRACE_ID.reset(self._token_trace_id)
        SPAN_ID.reset(self._token_span_id)
        PARENT_SPAN_ID.reset(self._token_parent_span_id)
        
    def end(self, end_time: Optional[float] = None):
        """
        Kết thúc span.
        
        Args:
            end_time: Thời gian kết thúc (epoch seconds)
        """
        if self.end_time is not None:
            # Span đã kết thúc
            return
            
        # Thiết lập thời gian kết thúc
        self.end_time = end_time or time.time()
        
        # Tính thời gian thực hiện
        self.duration = self.end_time - self.start_time
        
        # Thiết lập trạng thái recording
        self.is_recording = False
        
        # Export span kết thúc
        Tracer.export_span_end(self)
        
    def set_attribute(self, key: str, value: Any):
        """
        Thiết lập thuộc tính cho span.
        
        Args:
            key: Tên thuộc tính
            value: Giá trị thuộc tính
        """
        if not self.is_recording:
            return
            
        self.attributes[key] = value
        
    def set_attributes(self, attributes: Dict[str, Any]):
        """
        Thiết lập nhiều thuộc tính cho span.
        
        Args:
            attributes: Dict thuộc tính
        """
        if not self.is_recording:
            return
            
        self.attributes.update(attributes)
        
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None, timestamp: Optional[float] = None):
        """
        Thêm event vào span.
        
        Args:
            name: Tên event
            attributes: Thuộc tính event
            timestamp: Thời gian event (epoch seconds)
        """
        if not self.is_recording:
            return
            
        self.events.append({
            "name": name,
            "attributes": attributes or {},
            "timestamp": timestamp or time.time()
        })
        
    def record_exception(self, exception: Exception, attributes: Optional[Dict[str, Any]] = None):
        """
        Ghi nhận exception vào span.
        
        Args:
            exception: Ngoại lệ
            attributes: Thuộc tính bổ sung
        """
        if not self.is_recording:
            return
            
        # Tạo attributes cho exception
        exc_attributes = {
            "exception.type": type(exception).__name__,
            "exception.message": str(exception)
        }
        
        # Thêm attributes bổ sung
        if attributes:
            exc_attributes.update(attributes)
            
        # Thêm event exception
        self.add_event("exception", exc_attributes)
        
    def set_status(self, code: str, message: Optional[str] = None):
        """
        Thiết lập trạng thái cho span.
        
        Args:
            code: Mã trạng thái (OK, ERROR)
            message: Thông báo trạng thái
        """
        if not self.is_recording:
            return
            
        self.status_code = code
        self.status_message = message
        
    def add_link(self, trace_id: str, span_id: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Thêm link tới span khác.
        
        Args:
            trace_id: ID trace của span đích
            span_id: ID của span đích
            attributes: Thuộc tính link
        """
        if not self.is_recording:
            return
            
        self.links.append({
            "trace_id": trace_id,
            "span_id": span_id,
            "attributes": attributes or {}
        })
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Chuyển đổi span thành dict.
        
        Returns:
            Dict đại diện cho span
        """
        return {
            "name": self.name,
            "kind": self.kind,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "attributes": self.attributes,
            "status_code": self.status_code,
            "status_message": self.status_message,
            "events": self.events,
            "links": self.links
        }

class Tracer:
    """
    Tracer cho distributed tracing.
    Quản lý việc tạo, theo dõi và export spans.
    """
    
    # Cấu hình tracer
    enabled = settings.TRACING_ENABLED
    exporter = None
    
    @classmethod
    def configure(cls, exporter=None, enabled: bool = True):
        """
        Cấu hình tracer.
        
        Args:
            exporter: Exporter cho spans
            enabled: Bật/tắt tracing
        """
        cls.exporter = exporter
        cls.enabled = enabled and settings.TRACING_ENABLED
        
        if cls.enabled and not cls.exporter:
            # Tạo exporter mặc định
            if settings.TRACING_EXPORTER == "jaeger":
                try:
                    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
                    from opentelemetry.sdk.trace.export import BatchSpanProcessor
                    from opentelemetry.sdk.trace import TracerProvider
                    
                    cls.exporter = JaegerExporter(
                        agent_host_name=settings.JAEGER_AGENT_HOST,
                        agent_port=settings.JAEGER_AGENT_PORT
                    )
                    
                    provider = TracerProvider()
                    provider.add_span_processor(BatchSpanProcessor(cls.exporter))
                    
                except ImportError:
                    logger.warning("Không thể import Jaeger exporter. Hãy cài đặt: pip install opentelemetry-exporter-jaeger")
                    
            elif settings.TRACING_EXPORTER == "zipkin":
                try:
                    from opentelemetry.exporter.zipkin.json import ZipkinExporter
                    from opentelemetry.sdk.trace.export import BatchSpanProcessor
                    from opentelemetry.sdk.trace import TracerProvider
                    
                    cls.exporter = ZipkinExporter(
                        endpoint=settings.ZIPKIN_ENDPOINT
                    )
                    
                    provider = TracerProvider()
                    provider.add_span_processor(BatchSpanProcessor(cls.exporter))
                    
                except ImportError:
                    logger.warning("Không thể import Zipkin exporter. Hãy cài đặt: pip install opentelemetry-exporter-zipkin")
                    
            else:
                # Log exporter
                cls.exporter = LogExporter()
                
    @classmethod
    def create_span(
        cls,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        start_time: Optional[float] = None
    ) -> Span:
        """
        Tạo span mới.
        
        Args:
            name: Tên span
            kind: Loại span
            trace_id: ID trace
            parent_span_id: ID span cha
            attributes: Thuộc tính của span
            start_time: Thời gian bắt đầu (epoch seconds)
            
        Returns:
            Span object
        """
        # Tạo span
        span = Span(
            name=name,
            kind=kind,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes=attributes,
            start_time=start_time
        )
        
        return span
        
    @classmethod
    def get_current_span(cls) -> Optional[Span]:
        """
        Lấy span hiện tại từ context.
        
        Returns:
            Span hiện tại hoặc None
        """
        trace_id = TRACE_ID.get()
        span_id = SPAN_ID.get()
        
        if not trace_id or not span_id:
            return None
            
        # Tạo dummy span
        span = Span(
            name="current_span",
            trace_id=trace_id,
            parent_span_id=PARENT_SPAN_ID.get()
        )
        span.span_id = span_id
        
        return span
        
    @classmethod
    def export_span_start(cls, span: Span):
        """
        Export span khi bắt đầu.
        
        Args:
            span: Span bắt đầu
        """
        if not cls.enabled or not cls.exporter:
            return
            
        try:
            cls.exporter.export_span_start(span)
        except Exception as e:
            logger.error(f"Lỗi khi export span bắt đầu: {str(e)}")
            
    @classmethod
    def export_span_end(cls, span: Span):
        """
        Export span khi kết thúc.
        
        Args:
            span: Span kết thúc
        """
        if not cls.enabled or not cls.exporter:
            return
            
        try:
            cls.exporter.export_span_end(span)
        except Exception as e:
            logger.error(f"Lỗi khi export span kết thúc: {str(e)}")

class LogExporter:
    """Exporter ghi spans vào log."""
    
    def export_span_start(self, span: Span):
        """
        Export span bắt đầu vào log.
        
        Args:
            span: Span bắt đầu
        """
        logger.debug(f"Span bắt đầu: {span.name}, trace_id={span.trace_id}, span_id={span.span_id}")
        
    def export_span_end(self, span: Span):
        """
        Export span kết thúc vào log.
        
        Args:
            span: Span kết thúc
        """
        logger.debug(
            f"Span kết thúc: {span.name}, trace_id={span.trace_id}, span_id={span.span_id}, "
            f"duration={span.duration:.6f}s, status={span.status_code}"
        )

# Tạo singleton tracer
tracer = Tracer()

# Decorators tiện ích
def trace(
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None
):
    """
    Decorator để trace function.
    
    Args:
        name: Tên span (mặc định là tên function)
        kind: Loại span
        attributes: Thuộc tính span
        
    Returns:
        Decorator
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Xác định tên span
            span_name = name or func.__qualname__
            
            # Tạo span attributes
            span_attributes = (attributes or {}).copy()
            
            # Thêm thông tin function
            span_attributes.update({
                "function.name": func.__name__,
                "function.qualname": func.__qualname__,
                "function.module": func.__module__
            })
            
            # Bắt đầu span
            with tracer.create_span(span_name, kind, attributes=span_attributes) as span:
                try:
                    # Thực hiện function
                    result = await func(*args, **kwargs)
                    
                    # Đánh dấu span thành công
                    span.set_status("OK")
                    
                    return result
                except Exception as e:
                    # Ghi nhận exception
                    span.record_exception(e)
                    span.set_status("ERROR", str(e))
                    raise
                    
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Xác định tên span
            span_name = name or func.__qualname__
            
            # Tạo span attributes
            span_attributes = (attributes or {}).copy()
            
            # Thêm thông tin function
            span_attributes.update({
                "function.name": func.__name__,
                "function.qualname": func.__qualname__,
                "function.module": func.__module__
            })
            
            # Bắt đầu span
            with tracer.create_span(span_name, kind, attributes=span_attributes) as span:
                try:
                    # Thực hiện function
                    result = func(*args, **kwargs)
                    
                    # Đánh dấu span thành công
                    span.set_status("OK")
                    
                    return result
                except Exception as e:
                    # Ghi nhận exception
                    span.record_exception(e)
                    span.set_status("ERROR", str(e))
                    raise
                    
        # Chọn wrapper phù hợp
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        
    return decorator

class TracingMiddleware(BaseHTTPMiddleware):
    """
    Middleware tự động trace HTTP requests.
    """
    
    def __init__(self, app, exclude_paths: Optional[List[str]] = None):
        """
        Khởi tạo middleware.
        
        Args:
            app: ASGI app
            exclude_paths: Danh sách đường dẫn loại trừ khỏi tracing
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or []
        
    async def dispatch(self, request: Request, call_next):
        """
        Xử lý request và trace.
        
        Args:
            request: Request object
            call_next: Hàm xử lý tiếp theo
            
        Returns:
            Response
        """
        # Kiểm tra exclude
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
            
        # Lấy traceparent header nếu có
        trace_parent = request.headers.get("traceparent")
        trace_id = None
        parent_span_id = None
        
        if trace_parent:
            # Parse W3C Trace Context header
            # Format: version-trace_id-parent_id-flags
            try:
                parts = trace_parent.split("-")
                if len(parts) >= 3:
                    trace_id = parts[1]
                    parent_span_id = parts[2]
            except Exception:
                pass
                
        # Tạo span attributes
        attributes = {
            "http.method": request.method,
            "http.url": str(request.url),
            "http.host": request.headers.get("host", ""),
            "http.user_agent": request.headers.get("user-agent", ""),
            "http.path": request.url.path,
            "http.route": request.url.path,
            "http.scheme": request.url.scheme,
            "http.flavor": f"HTTP/{request.scope.get('http_version', '1.1')}"
        }
        
        # Bắt đầu span
        with tracer.create_span(
            name=f"HTTP {request.method} {request.url.path}",
            kind=SpanKind.SERVER,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes=attributes
        ) as span:
            try:
                # Gọi xử lý tiếp theo
                response = await call_next(request)
                
                # Thêm thông tin response
                span.set_attribute("http.status_code", response.status_code)
                
                # Đánh dấu trạng thái span
                if 200 <= response.status_code < 400:
                    span.set_status("OK")
                else:
                    span.set_status("ERROR", f"HTTP status code: {response.status_code}")
                    
                # Thêm header trace vào response
                response.headers["traceparent"] = f"00-{span.trace_id}-{span.span_id}-01"
                
                return response
            except Exception as e:
                # Ghi nhận exception
                span.record_exception(e)
                span.set_status("ERROR", str(e))
                raise

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.exporter.zipkin.json import ZipkinExporter
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    # Tạo mock modules
    class MockTracer:
        def start_as_current_span(self, name, **kwargs):
            class MockSpan:
                def __enter__(self):
                    return self
                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass
                def set_attribute(self, key, value):
                    pass
                def add_event(self, name, attributes=None):
                    pass
                def set_status(self, status, description=None):
                    pass
                def record_exception(self, exception):
                    pass
            return MockSpan()
    
    class MockTracerProvider:
        def get_tracer(self, name, version=None):
            return MockTracer()
    
    class MockTraceModule:
        def get_tracer(self, name, version=None):
            return MockTracer()
        def set_tracer_provider(self, provider):
            pass
    
    trace = MockTraceModule()
    
    class TracerProvider(MockTracerProvider):
        pass
    
    class BatchSpanProcessor:
        def __init__(self, exporter):
            pass
    
    class JaegerExporter:
        def __init__(self, **kwargs):
            pass
    
    class ZipkinExporter:
        def __init__(self, **kwargs):
            pass

def create_jaeger_exporter(endpoint: str) -> Any:
    """Tạo Jaeger exporter"""
    if not OPENTELEMETRY_AVAILABLE:
        logger.warning("OpenTelemetry không được cài đặt. Tracing sẽ không hoạt động.")
        return None
        
    # Use JaegerExporter class directly instead of jaeger_exporter module
    return JaegerExporter(
        collector_endpoint=endpoint
    )

def setup_tracer(service_name: str, exporter_type: str = "jaeger") -> None:
    """
    Thiết lập distributed tracing.
    
    Args:
        service_name: Tên service
        exporter_type: Loại exporter (jaeger hoặc zipkin)
    """
    if not OPENTELEMETRY_AVAILABLE:
        logger.warning("OpenTelemetry không được cài đặt. Tracing sẽ không hoạt động.")
        return
        
    # Tạo tracer provider
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
    
    # Tạo exporter tùy theo loại
    if exporter_type.lower() == "jaeger":
        if not JAEGER_AVAILABLE:
            logger.warning("JaegerExporter không khả dụng do thiếu thư viện.")
            return
            
        jaeger_exporter = JaegerExporter(
            agent_host_name=get_settings().JAEGER_HOST,
            agent_port=get_settings().JAEGER_PORT,
        )
        # Add span processor
        tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
    elif exporter_type.lower() == "zipkin":
        # Tạo Zipkin exporter
        zipkin_exporter = ZipkinExporter(
            endpoint=get_settings().ZIPKIN_ENDPOINT
        )
        # Add span processor
        tracer_provider.add_span_processor(BatchSpanProcessor(zipkin_exporter))
    else:
        logger.error(f"Không hỗ trợ exporter type: {exporter_type}")
        return
        
    logger.info(f"Đã thiết lập tracing cho service {service_name} với exporter {exporter_type}")

try:
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    JAEGER_AVAILABLE = True
except ImportError:
    JAEGER_AVAILABLE = False
    
    class JaegerExporter:
        def __init__(self, *args, **kwargs):
            pass
