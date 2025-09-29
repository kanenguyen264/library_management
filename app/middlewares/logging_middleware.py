import time
import json
import uuid
from typing import Callable, List, Optional, Dict, Any
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from app.logging.setup import get_logger
from app.core.config import get_settings
import traceback
from contextlib import asynccontextmanager
from app.logs_manager.services import create_api_request_log
from app.logs_manager.schemas.api_request_log import ApiRequestLogCreate
from app.core.db import Base

settings = get_settings()
logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware để ghi log tất cả requests và responses.
    Hỗ trợ debug, phân tích hiệu suất và tracking.
    """

    def __init__(
        self,
        app: FastAPI,
        skip_paths: Optional[List[str]] = None,
        skip_methods: Optional[List[str]] = None,
        log_headers: bool = True,
        log_body: bool = False,
        log_responses: bool = True,
        sensitive_headers: Optional[List[str]] = None,
        sensitive_body_fields: Optional[List[str]] = None,
        log_errors_only: bool = False,
        correlation_id_header: str = "X-Correlation-ID",
    ):
        """
        Khởi tạo middleware.

        Args:
            app: FastAPI application
            skip_paths: List of paths to skip logging
            skip_methods: List of HTTP methods to skip logging
            log_headers: Whether to log request headers
            log_body: Whether to log request body
            log_responses: Whether to log response body
            sensitive_headers: List of sensitive headers to mask
            sensitive_body_fields: List of sensitive body fields to mask
            log_errors_only: Whether to log only error responses
            correlation_id_header: Header name for correlation ID
        """
        super().__init__(app)

        self.skip_paths = skip_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/favicon.ico",
            "/_debug",
        ]

        self.skip_methods = skip_methods or ["OPTIONS"]
        self.log_headers = log_headers
        self.log_body = log_body
        self.log_responses = log_responses
        self.log_errors_only = log_errors_only
        self.correlation_id_header = correlation_id_header

        self.sensitive_headers = [
            h.lower()
            for h in (
                sensitive_headers
                or ["Authorization", "Cookie", "Set-Cookie", "X-API-Key"]
            )
        ]

        self.sensitive_body_fields = sensitive_body_fields or [
            "password",
            "secret",
            "token",
            "api_key",
            "password_confirmation",
            "credit_card",
            "card_number",
        ]

    async def dispatch(self, request: Request, call_next):
        """
        Process request through middleware, logging request and response.

        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint in chain

        Returns:
            Response
        """
        # Skip logging for certain paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        # Skip logging for certain methods
        if request.method in self.skip_methods:
            return await call_next(request)

        # Generate correlation ID
        correlation_id = request.headers.get(
            self.correlation_id_header, f"correlation-{uuid.uuid4()}"
        )

        # Start timing
        start_time = time.time()

        # Prepare request logging
        path = request.url.path
        query_params = dict(request.query_params)
        client_host = request.client.host if request.client else "unknown"

        # Log the request
        log_data = {
            "correlation_id": correlation_id,
            "request": {
                "method": request.method,
                "path": path,
                "query_params": query_params,
                "client_ip": client_host,
                "user_agent": request.headers.get("User-Agent", "unknown"),
            },
            "timestamp": start_time,
        }

        # Add headers if enabled
        if self.log_headers:
            headers = dict(request.headers)
            # Mask sensitive headers
            for header in self.sensitive_headers:
                if header in headers:
                    headers[header] = "***REDACTED***"

            log_data["request"]["headers"] = headers

        # Add request body if enabled
        if self.log_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Save the request body
                body = await request.body()
                request_body = body.decode()

                # Try to parse as JSON
                try:
                    body_json = json.loads(request_body)
                    # Mask sensitive fields
                    for field in self.sensitive_body_fields:
                        if field in body_json:
                            body_json[field] = "***REDACTED***"

                    log_data["request"]["body"] = body_json
                except json.JSONDecodeError:
                    # Not JSON, add raw body with limit
                    if len(request_body) > 1000:
                        log_data["request"]["body"] = (
                            request_body[:1000] + "... (truncated)"
                        )
                    else:
                        log_data["request"]["body"] = request_body

                # Create a copy of the request with the body
                async def receive():
                    return {"type": "http.request", "body": body}

                request._receive = receive

            except Exception as e:
                logger.warning(f"Error reading request body: {str(e)}")

        # Process the request
        try:
            # Add correlation ID header to request
            request.state.correlation_id = correlation_id

            # Pass to next middleware
            response = await call_next(request)

            # Calculate processing time
            process_time = time.time() - start_time

            # Only log successful requests if log_errors_only is True
            if self.log_errors_only and response.status_code < 400:
                return response

            # Add response information
            log_data["response"] = {
                "status_code": response.status_code,
                "process_time_ms": round(process_time * 1000, 2),
            }

            # Add response body if enabled
            if self.log_responses and response.status_code != 204:
                # We need to access the response body without consuming it
                original_response_body = response.body

                if original_response_body:
                    try:
                        body_str = original_response_body.decode()

                        # Try to parse as JSON
                        try:
                            response_json = json.loads(body_str)
                            # Mask sensitive fields
                            for field in self.sensitive_body_fields:
                                if field in response_json:
                                    response_json[field] = "***REDACTED***"

                            log_data["response"]["body"] = response_json
                        except json.JSONDecodeError:
                            # Not JSON, add raw body with limit
                            if len(body_str) > 1000:
                                log_data["response"]["body"] = (
                                    body_str[:1000] + "... (truncated)"
                                )
                            else:
                                log_data["response"]["body"] = body_str

                    except Exception as e:
                        logger.warning(f"Error reading response body: {str(e)}")

            # Log to API request log database
            try:
                # Extract user ID and admin ID if available
                user_id = getattr(request.state, "user_id", None)
                admin_id = getattr(request.state, "admin_id", None)

                # Create API request log entry
                for db in Base():
                    await create_api_request_log(
                        db,
                        ApiRequestLogCreate(
                            endpoint=path,
                            method=request.method,
                            status_code=response.status_code,
                            duration_ms=round(process_time * 1000, 2),
                            user_id=user_id,
                            admin_id=admin_id,
                            client_ip=client_host,
                            user_agent=request.headers.get("User-Agent", "unknown"),
                            correlation_id=correlation_id,
                            request_data=(
                                {
                                    "query_params": query_params,
                                    "headers": log_data["request"].get("headers", {}),
                                }
                                if self.log_headers
                                else {}
                            ),
                            response_data=log_data["response"],
                            errors=log_data.get("error", None),
                        ),
                    )
                    break
            except Exception as e:
                logger.error(f"Error logging API request to database: {str(e)}")
                logger.error(traceback.format_exc())

            # Log to application logs
            if response.status_code >= 500:
                logger.error(f"API Error: {json.dumps(log_data)}")
            elif response.status_code >= 400:
                logger.warning(f"API Warning: {json.dumps(log_data)}")
            else:
                logger.info(f"API Info: {json.dumps(log_data)}")

            # Add correlation ID to response headers
            response.headers[self.correlation_id_header] = correlation_id

            return response

        except Exception as e:
            # Calculate processing time
            process_time = time.time() - start_time

            # Log the error
            log_data["error"] = {
                "type": type(e).__name__,
                "message": str(e),
                "process_time_ms": round(process_time * 1000, 2),
            }

            logger.exception(f"API Unhandled Exception: {path}", extra=log_data)

            # Return an error response
            return Response(
                content=json.dumps(
                    {
                        "detail": "Internal server error",
                        "correlation_id": correlation_id,
                    }
                ),
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json",
                headers={self.correlation_id_header: correlation_id},
            )
