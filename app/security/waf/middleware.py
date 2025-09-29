import json
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN
from app.core.config import get_settings
from app.security.waf.rules import check_attack_vectors
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

class WAFMiddleware(BaseHTTPMiddleware):
    """
    Web Application Firewall middleware phát hiện và chặn các vector tấn công phổ biến.
    """
    
    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.app_env = settings.APP_ENV
        self.debug = settings.DEBUG
        
    async def analyze_request(self, request: Request) -> dict:
        """Phân tích request để phát hiện các dấu hiệu tấn công."""
        attacks_found = {}
        
        # Phân tích URL path
        path = request.url.path
        attacks_found["path"] = check_attack_vectors(path)
        
        # Phân tích query params
        query_params = dict(request.query_params)
        if query_params:
            query_str = json.dumps(query_params)
            attacks_found["query"] = check_attack_vectors(query_str)
            
        # Phân tích headers (loại trừ một số header an toàn)
        safe_headers = {"user-agent", "accept", "accept-encoding", "connection", "host"}
        unsafe_headers = {k: v for k, v in request.headers.items() if k.lower() not in safe_headers}
        
        if unsafe_headers:
            headers_str = json.dumps(unsafe_headers)
            attacks_found["headers"] = check_attack_vectors(headers_str)
            
        # Phân tích body (nếu có)
        has_attack_in_body = False
        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                body = await request.body()
                if body:
                    body_text = body.decode("utf-8", errors="ignore")
                    if body_text:
                        attacks_found["body"] = check_attack_vectors(body_text)
                        has_attack_in_body = any(attacks_found["body"].values())
        except Exception as e:
            logger.error(f"WAF: Error analyzing request body: {str(e)}")
        
        return attacks_found
    
    def is_attack_detected(self, analysis: dict) -> bool:
        """Kiểm tra xem có phát hiện tấn công hay không từ kết quả phân tích."""
        for section, results in analysis.items():
            if any(results.values()):
                return True
        return False
    
    async def dispatch(self, request: Request, call_next):
        # Bypass WAF trong môi trường development nếu cần
        if self.app_env == "development" and not self.debug:
            return await call_next(request)
            
        # Phân tích request
        analysis = await self.analyze_request(request)
        
        # Kiểm tra kết quả phân tích
        if self.is_attack_detected(analysis):
            # Log sự cố
            log_data = {
                "ip": request.client.host,
                "path": request.url.path,
                "method": request.method,
                "attack_analysis": analysis,
                "headers": dict(request.headers)
            }
            logger.warning(f"WAF: Potential attack detected", extra=log_data)
            
            # Trả về lỗi
            return JSONResponse(
                status_code=HTTP_403_FORBIDDEN,
                content={
                    "detail": "Request bị từ chối vì lý do bảo mật."
                }
            )
            
        # Tiếp tục request
        return await call_next(request)
