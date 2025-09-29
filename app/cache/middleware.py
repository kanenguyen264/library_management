from typing import Dict, List, Any, Optional, Union, Set, Tuple, Callable
import time
import json
import asyncio
import logging
import hashlib
from datetime import datetime, timedelta

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.cache.manager import cache_manager
from app.monitoring.metrics import metrics

settings = get_settings()
logger = get_logger(__name__)

class CacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware cho phép cache response của API.
    Cung cấp:
    - Cache tự động cho GET requests
    - Cache phân tầng (in-memory + Redis)
    - Invalidation của cache khi có write operations (POST, PUT, PATCH, DELETE)
    - Hỗ trợ cache with variations dựa trên headers, query params
    """
    
    def __init__(
        self,
        app: ASGIApp,
        ttl: int = 60,  # 1 phút
        cache_get_requests: bool = True,
        exclude_paths: Optional[List[str]] = None,
        exclude_prefixes: Optional[List[str]] = None,
        vary_headers: Optional[List[str]] = None,
        vary_query_params: Optional[List[str]] = None,
        cache_control_header: bool = True,
        cache_namespace: str = "api_responses",
        invalidation_patterns: Optional[Dict[str, List[str]]] = None
    ):
        """
        Khởi tạo middleware.
        
        Args:
            app: ASGI app
            ttl: Thời gian sống cache (giây)
            cache_get_requests: Tự động cache GET requests
            exclude_paths: Đường dẫn không cache
            exclude_prefixes: Tiền tố đường dẫn không cache
            vary_headers: Headers ảnh hưởng đến cache key
            vary_query_params: Query params ảnh hưởng đến cache key
            cache_control_header: Thêm Cache-Control header
            cache_namespace: Namespace cho cache
            invalidation_patterns: Mẫu vô hiệu hóa cache {path: [patterns]}
        """
        super().__init__(app)
        
        # Cấu hình cache
        self.ttl = ttl
        self.cache_get_requests = cache_get_requests
        self.exclude_paths = exclude_paths or []
        self.exclude_prefixes = exclude_prefixes or []
        self.vary_headers = vary_headers or ["accept", "accept-encoding"]
        self.vary_query_params = vary_query_params or ["lang", "version"]
        self.cache_control_header = cache_control_header
        self.cache_namespace = cache_namespace
        
        # Mẫu vô hiệu hóa cache
        self.invalidation_patterns = invalidation_patterns or {
            # Vô hiệu hóa cache sách khi có thay đổi
            "POST /api/v1/books": ["books:*"],
            "PUT /api/v1/books/*": ["books:*", "books:detail:*"],
            "DELETE /api/v1/books/*": ["books:*", "books:detail:*"],
            
            # Vô hiệu hóa cache tác giả
            "POST /api/v1/authors": ["authors:*"],
            "PUT /api/v1/authors/*": ["authors:*", "authors:detail:*"],
            "DELETE /api/v1/authors/*": ["authors:*", "authors:detail:*"],
            
            # Vô hiệu hóa cache danh mục
            "POST /api/v1/categories": ["categories:*"],
            "PUT /api/v1/categories/*": ["categories:*", "categories:detail:*"],
            "DELETE /api/v1/categories/*": ["categories:*", "categories:detail:*"],
        }
        
        logger.info(
            f"Khởi tạo CacheMiddleware với ttl={ttl}s, cache_namespace='{cache_namespace}', "
            f"cache_get_requests={cache_get_requests}"
        )
        
    def should_cache_response(self, request: Request) -> bool:
        """
        Xác định xem có nên cache response hay không.
        
        Args:
            request: Request object
            
        Returns:
            True nếu nên cache
        """
        # Chỉ cache GET requests
        if not self.cache_get_requests or request.method != "GET":
            return False
            
        # Kiểm tra đường dẫn
        path = request.url.path
        
        # Exclude paths
        if path in self.exclude_paths:
            return False
            
        # Exclude prefixes
        for prefix in self.exclude_prefixes:
            if path.startswith(prefix):
                return False
                
        return True
        
    def generate_cache_key(self, request: Request) -> str:
        """
        Tạo cache key từ request.
        
        Args:
            request: Request object
            
        Returns:
            Cache key
        """
        # Base key từ path
        key_parts = [request.url.path]
        
        # Thêm query params
        query_params = dict(request.query_params)
        for param in self.vary_query_params:
            if param in query_params:
                key_parts.append(f"{param}={query_params[param]}")
                
        # Thêm headers
        for header in self.vary_headers:
            if header in request.headers:
                key_parts.append(f"{header}={request.headers[header]}")
                
        # Join và hash
        key_str = ":".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()
        
    def get_invalidation_patterns(self, request: Request) -> List[str]:
        """
        Lấy patterns vô hiệu hóa cho request.
        
        Args:
            request: Request object
            
        Returns:
            Danh sách patterns cần vô hiệu hóa
        """
        method = request.method
        path = request.url.path
        
        # Tạo key lookup: "METHOD /path/to/resource"
        key = f"{method} {path}"
        patterns = []
        
        # Tìm khớp chính xác
        if key in self.invalidation_patterns:
            patterns.extend(self.invalidation_patterns[key])
            
        # Tìm khớp wildcard
        for pattern_key, pattern_list in self.invalidation_patterns.items():
            # Tách method và path pattern
            try:
                pattern_method, pattern_path = pattern_key.split(" ", 1)
            except ValueError:
                continue
                
            # Kiểm tra method
            if pattern_method != method:
                continue
                
            # Chuyển đổi pattern dạng /users/* thành /users/
            if "*" in pattern_path:
                pattern_prefix = pattern_path.split("*")[0]
                if path.startswith(pattern_prefix):
                    patterns.extend(pattern_list)
                    
        return patterns
        
    async def set_cache_control_header(self, response: Response, max_age: int) -> None:
        """
        Thêm Cache-Control header.
        
        Args:
            response: Response object
            max_age: Max age (seconds)
        """
        if not self.cache_control_header:
            return
            
        cache_control = f"public, max-age={max_age}"
        response.headers["Cache-Control"] = cache_control
        
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Xử lý request và cache response.
        
        Args:
            request: Request object
            call_next: Hàm xử lý tiếp theo
            
        Returns:
            Response
        """
        # Đo thời gian xử lý
        start_time = time.time()
        
        # Kiểm tra xem có nên cache hay không
        should_cache = self.should_cache_response(request)
        cache_hit = False
        
        if should_cache:
            # Tạo cache key
            cache_key = self.generate_cache_key(request)
            
            # Lấy từ cache
            cached_response = await cache_manager.get(cache_key, namespace=self.cache_namespace)
            
            if cached_response:
                # Cache hit
                cache_hit = True
                
                # Tạo response từ cached data
                try:
                    status_code = cached_response.get("status_code", 200)
                    headers = cached_response.get("headers", {})
                    content = cached_response.get("content", b"")
                    
                    # Tạo response
                    response = Response(
                        content=content,
                        status_code=status_code,
                        headers=dict(headers)
                    )
                    
                    # Thêm header cho biết từ cache
                    response.headers["X-Cache"] = "HIT"
                    
                    # Thêm Cache-Control
                    await self.set_cache_control_header(response, self.ttl)
                    
                    # Ghi metrics
                    metrics.cache_hit_count.inc()
                    metrics.cache_request_duration.observe(time.time() - start_time)
                    
                    return response
                    
                except Exception as e:
                    # Lỗi khi tạo response từ cache
                    logger.error(f"Lỗi khi tạo response từ cache: {str(e)}")
                    cache_hit = False
                    
        # Gọi handler tiếp theo
        response = await call_next(request)
        
        # Cache miss, lưu response mới vào cache
        if should_cache and not cache_hit and 200 <= response.status_code < 400:
            try:
                # Đọc response content
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk
                    
                # Tái tạo response
                response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
                
                # Chuẩn bị dữ liệu cache
                cache_data = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "content": response_body
                }
                
                # Lưu vào cache
                await cache_manager.set(
                    cache_key,
                    cache_data,
                    namespace=self.cache_namespace,
                    ttl=self.ttl
                )
                
                # Thêm header
                response.headers["X-Cache"] = "MISS"
                
                # Thêm Cache-Control
                await self.set_cache_control_header(response, self.ttl)
                
                # Ghi metrics
                metrics.cache_miss_count.inc()
                
            except Exception as e:
                # Lỗi khi cache response
                logger.error(f"Lỗi khi cache response: {str(e)}")
                
        # Kiểm tra vô hiệu hóa cache
        if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            patterns = self.get_invalidation_patterns(request)
            
            if patterns:
                # Vô hiệu hóa cache
                for pattern in patterns:
                    await cache_manager.clear(pattern, namespace=self.cache_namespace)
                    logger.debug(f"Đã vô hiệu hóa cache: {pattern}")
                    
                # Ghi metrics
                metrics.cache_invalidation_count.inc(len(patterns))
                
        # Đo thời gian xử lý
        metrics.request_duration.observe(time.time() - start_time)
        
        return response
