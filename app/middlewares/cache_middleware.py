from typing import Callable, Dict, List, Optional, Any, Union
import hashlib
import json
import time
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import get_settings
from app.logging.setup import get_logger
import redis.asyncio as redis

settings = get_settings()
logger = get_logger(__name__)


class CacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware để tự động cache responses từ API.
    Hỗ trợ cache hit/miss tracking và invalidation.
    """

    def __init__(
        self,
        app: FastAPI,
        redis_client: redis.Redis = None,
        redis_host: str = settings.REDIS_HOST,
        redis_port: int = settings.REDIS_PORT,
        redis_password: str = settings.REDIS_PASSWORD,
        redis_db: int = settings.REDIS_DB,
        default_ttl: int = 300,  # 5 minutes
        cacheable_status_codes: List[int] = None,
        cacheable_methods: List[str] = None,
        cache_by_auth: bool = True,
        cache_by_query_params: bool = True,
        exclude_paths: List[str] = None,
        exclude_query_params: List[str] = None,
        vary_headers: List[str] = None,
        key_prefix: str = "api_cache",
    ):
        """
        Khởi tạo middleware.

        Args:
            app: FastAPI application
            redis_client: Redis client
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password
            redis_db: Redis database
            default_ttl: Default cache TTL in seconds
            cacheable_status_codes: Status codes to cache
            cacheable_methods: HTTP methods to cache
            cache_by_auth: Whether to include auth in cache key
            cache_by_query_params: Whether to include query params in cache key
            exclude_paths: Paths to exclude from caching
            exclude_query_params: Query params to exclude from cache key
            vary_headers: Headers to include in cache key
            key_prefix: Cache key prefix
        """
        super().__init__(app)

        self.redis_client = redis_client

        if not self.redis_client:
            self.redis_client = redis.from_url(
                f"redis://{':' + redis_password + '@' if redis_password else ''}{redis_host}:{redis_port}/{redis_db}"
            )

        self.default_ttl = default_ttl
        self.cacheable_status_codes = cacheable_status_codes or [
            200,
            203,
            204,
            206,
            300,
            301,
            302,
            304,
            307,
            308,
        ]
        self.cacheable_methods = cacheable_methods or ["GET", "HEAD"]
        self.cache_by_auth = cache_by_auth
        self.cache_by_query_params = cache_by_query_params
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/api/v1/auth/",
        ]
        self.exclude_query_params = exclude_query_params or [
            "timestamp",
            "nocache",
            "refresh",
        ]
        self.vary_headers = vary_headers or [
            "Accept",
            "Accept-Encoding",
            "Accept-Language",
        ]
        self.key_prefix = key_prefix

    async def dispatch(self, request: Request, call_next):
        """
        Process request through middleware, caching response if applicable.

        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint in chain

        Returns:
            Response
        """
        # Skip non-cacheable requests
        if not self._is_cacheable(request):
            return await call_next(request)

        # Generate cache key
        cache_key = await self._generate_cache_key(request)

        # Check cache
        cached_data = await self.redis_client.get(cache_key)

        if cached_data:
            # Parse cached response
            try:
                cached_response = json.loads(cached_data)

                # Create response from cache
                response = Response(
                    content=cached_response.get("body", b"").encode(),
                    status_code=cached_response.get("status_code", 200),
                    headers=cached_response.get("headers", {}),
                )

                # Add cache headers
                response.headers["X-Cache"] = "HIT"

                logger.debug(f"Cache hit for {request.url.path}")
                return response

            except Exception as e:
                logger.warning(f"Error parsing cached response: {str(e)}")

        # Cache miss, proceed with request
        response = await call_next(request)

        # Cache the response if applicable
        if self._should_cache_response(response):
            await self._cache_response(cache_key, response)

        # Add cache miss header
        response.headers["X-Cache"] = "MISS"

        return response

    def _is_cacheable(self, request: Request) -> bool:
        """
        Check if request is cacheable.

        Args:
            request: FastAPI request

        Returns:
            Whether the request is cacheable
        """
        # Check method
        if request.method not in self.cacheable_methods:
            return False

        # Check path
        path = request.url.path
        if any(path.startswith(exclude) for exclude in self.exclude_paths):
            return False

        # Check cache-control headers
        cache_control = request.headers.get("Cache-Control", "")
        if "no-cache" in cache_control or "no-store" in cache_control:
            return False

        # Check query params
        query_params = dict(request.query_params)
        for param in self.exclude_query_params:
            if param in query_params:
                return False

        return True

    def _should_cache_response(self, response: Response) -> bool:
        """
        Check if response should be cached.

        Args:
            response: FastAPI response

        Returns:
            Whether the response should be cached
        """
        # Check status code
        if response.status_code not in self.cacheable_status_codes:
            return False

        # Check cache-control headers
        cache_control = response.headers.get("Cache-Control", "")
        if (
            "no-cache" in cache_control
            or "no-store" in cache_control
            or "private" in cache_control
        ):
            return False

        # Check content type
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith(
            ("application/json", "text/", "application/xml")
        ):
            return False

        return True

    async def _generate_cache_key(self, request: Request) -> str:
        """
        Generate cache key for request.

        Args:
            request: FastAPI request

        Returns:
            Cache key
        """
        # Create key parts
        key_parts = [self.key_prefix, request.method, request.url.path]

        # Add query params if enabled
        if self.cache_by_query_params and request.query_params:
            # Filter out excluded params
            filtered_params = {
                k: v
                for k, v in request.query_params.items()
                if k not in self.exclude_query_params
            }

            if filtered_params:
                # Sort params for consistent cache keys
                sorted_params = sorted(filtered_params.items())
                key_parts.append(str(sorted_params))

        # Add auth info if enabled
        if self.cache_by_auth:
            # Extract user ID from state if available
            user_id = getattr(request.state, "user_id", None)
            if user_id:
                key_parts.append(f"user:{user_id}")
            else:
                # Add auth header hash if available
                auth_header = request.headers.get("Authorization")
                if auth_header:
                    # Only include the type (e.g. "Bearer") and a hash of the token
                    auth_parts = auth_header.split()
                    if len(auth_parts) == 2:
                        token_hash = hashlib.md5(auth_parts[1].encode()).hexdigest()
                        key_parts.append(f"{auth_parts[0]}:{token_hash}")
                else:
                    key_parts.append("anonymous")

        # Add vary headers if available
        for header in self.vary_headers:
            value = request.headers.get(header)
            if value:
                key_parts.append(f"{header}:{value}")

        # Generate final key
        key_str = ":".join(str(part) for part in key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()

    async def _cache_response(self, cache_key: str, response: Response) -> None:
        """
        Cache response.

        Args:
            cache_key: Cache key
            response: FastAPI response
        """
        # Get TTL from Cache-Control if available
        ttl = self.default_ttl
        cache_control = response.headers.get("Cache-Control", "")
        if "max-age=" in cache_control:
            try:
                max_age = int(cache_control.split("max-age=")[1].split(",")[0])
                ttl = max_age
            except (ValueError, IndexError):
                pass

        # Prepare response data for cache
        try:
            body = response.body.decode()
        except UnicodeDecodeError:
            # If body is binary, store as base64
            import base64

            body = base64.b64encode(response.body).decode()

        # Store headers excluding hop-by-hop headers
        hop_by_hop_headers = {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }

        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in hop_by_hop_headers
        }

        # Add cache metadata
        headers["X-Cache-Date"] = str(int(time.time()))

        # Create cache data
        cache_data = {
            "status_code": response.status_code,
            "headers": headers,
            "body": body,
        }

        # Store in Redis
        try:
            await self.redis_client.setex(cache_key, ttl, json.dumps(cache_data))
        except Exception as e:
            logger.warning(f"Error caching response: {str(e)}")

    async def invalidate_cache(self, pattern: str) -> int:
        """
        Invalidate cache by pattern.

        Args:
            pattern: Cache key pattern

        Returns:
            Number of keys deleted
        """
        try:
            keys = await self.redis_client.keys(f"{self.key_prefix}:{pattern}")
            if keys:
                return await self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Error invalidating cache: {str(e)}")
            return 0
