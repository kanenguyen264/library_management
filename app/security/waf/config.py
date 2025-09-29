from typing import Dict, List, Set, Pattern, Optional
import re
from enum import Enum


class AttackType(str, Enum):
    """Các loại tấn công web phổ biến mà WAF phát hiện."""

    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    OPEN_REDIRECT = "open_redirect"
    SSRF = "ssrf"
    XXE = "xxe"
    CSRF = "csrf"
    LDAP_INJECTION = "ldap_injection"
    NOSQL_INJECTION = "nosql_injection"
    HTTP_METHOD_OVERRIDE = "http_method_override"
    HTTP_POLLUTION = "http_pollution"


# Các mẫu regex để phát hiện SQL Injection
SQL_INJECTION_PATTERNS = [
    r"[\s\']+(OR|AND)[\s\']+(.*?)[\s\']*=[\s\']*\w+",
    r";\s*(\w+\s+)+",
    r"(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|RENAME)[\s\(]+",
    r"\/\*.*?\*\/",
    r"#.+$",
    r"--.*$",
    r"(SLEEP|BENCHMARK)\s*\(",
    r"WAITFOR\s+DELAY",
    r"(INFORMATION_SCHEMA|SYSIBM|SYSDUMMY)",
]

# Các mẫu regex để phát hiện Cross-Site Scripting (XSS)
XSS_PATTERNS = [
    r"<script.*?>",
    r"<\s*script\b[^>]*>(.*?)<\s*/\s*script\s*>",
    r"javascript:[^\w\s]",
    r"on\w+\s*=\s*[\"']",
    r"(document|window|eval|setTimeout|setInterval)\s*\(",
    r"innerHTML|outerHTML|document\.write",
    r"fromCharCode|String\.fromCharCode",
    r"<\s*img[^>]*\bsrc\s*=\s*[^>]*>",
    r"<\s*iframe[^>]*\bsrc\s*=\s*[^>]*>",
    r"<\s*embed[^>]*\bsrc\s*=\s*[^>]*>",
    r"<\s*object[^>]*\bdata\s*=\s*[^>]*>",
    r"data:text\/html",
    r"&#x[0-9a-f]{2}",
]

# Các mẫu regex để phát hiện Path Traversal
PATH_TRAVERSAL_PATTERNS = [
    r"\.\.\/",
    r"\.\.\\",
    r"%2e%2e%2f",
    r"%252e%252e%252f",
    r"\.\.%2f",
    r"\.\.%5c",
    r"%2e%2e\/",
    r"%2e%2e\\",
    r"\.\.%252f",
    r"\.\.%255c",
    r"\.\.\/",
]

# Các mẫu regex để phát hiện Command Injection
COMMAND_INJECTION_PATTERNS = [
    r"[\;\|\`\&\$\(\)\\><]",
    r"[^\w]ping\s+",
    r"[^\w]wget\s+",
    r"[^\w]curl\s+",
    r"[^\w]bash\s+",
    r"[^\w]sh\s+",
    r"[^\w]cmd\s+",
    r"[^\w]python\s+",
    r"[^\w]perl\s+",
    r"[^\w]ruby\s+",
    r"[^\w]lua\s+",
    r"[^\w]nmap\s+",
    r"[^\w]nc\s+",
    r"[^\w]netcat\s+",
    r"[^\w]nslookup\s+",
    r"[^\w]telnet\s+",
    r"[^\w]ssh\s+",
]

# Các mẫu regex để phát hiện Open Redirect
OPEN_REDIRECT_PATTERNS = [
    r"(https?|ftp):\/\/(?!(?:www\.)?(?:example\.com|localhost))",
    r"(?:[\/\\]{2,}[^\/\\]+)",
    r"\/\/\d+\.\d+\.\d+\.\d+",
    r"\/\/[0-9a-f:]+",
    r"%2f%2f",
    r"data:",
    r"vbscript:",
    r"javascript:",
]

# Các mẫu regex để phát hiện Server-Side Request Forgery (SSRF)
SSRF_PATTERNS = [
    r"(https?|ftp|file|dict|gopher|ldap|s3):\/\/(?!(?:www\.)?(?:example\.com|localhost))",
    r"127\.0\.0\.\d+",
    r"localhost",
    r"0\.0\.0\.0",
    r"10\.\d+\.\d+\.\d+",
    r"172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+",
    r"192\.168\.\d+\.\d+",
    r"169\.254\.\d+\.\d+",
    r"::1",
    r"fc00::",
    r"fe80::",
    r"metadata\.google\.internal",
]

# Các mẫu regex để phát hiện XML External Entity (XXE)
XXE_PATTERNS = [
    r"<!ENTITY",
    r"<!DOCTYPE[^>]+SYSTEM",
    r"<!DOCTYPE[^>]+PUBLIC",
    r"<!\[CDATA\[",
    r"<!\[INCLUDE\[",
    r"file:\/\/",
    r"php:\/\/",
    r"phar:\/\/",
]

# Các mẫu nộ CSRF
CSRF_PATTERNS = [
    r"<form.*?>",
    r"document\.forms\[.*?\]\.submit",
    r"XMLHttpRequest",
    r"fetch\s*\(",
    r"(?:get|post|put|delete).*?url",
]

# Các mẫu regex để phát hiện LDAP Injection
LDAP_INJECTION_PATTERNS = [
    r"\(\s*\|\s*",
    r"\)\s*\(\s*\|",
    r"\(\s*&\s*",
    r"\*[^a-zA-Z0-9]",
    r"\(\s*\!\s*",
    r"objectClass=\*",
    r"objectClass=\)",
    r"cn=[^,]*,",
    r"sn=[^,]*,",
]

# Các mẫu regex để phát hiện NoSQL Injection
NOSQL_INJECTION_PATTERNS = [
    r"\{\s*\$where\s*:",
    r"\{\s*\$gt\s*:",
    r"\{\s*\$ne\s*:",
    r"\{\s*\$nin\s*:",
    r"\{\s*\$or\s*:",
    r"\{\s*\$and\s*:",
    r"\$regex\s*:",
    r"\$exists\s*:",
    r"\$elemMatch\s*:",
]

# Các mẫu regex để phát hiện HTTP Method Override
HTTP_METHOD_OVERRIDE_PATTERNS = [
    r"(_method|X-HTTP-Method|X-HTTP-Method-Override|X-Method-Override)=",
    r"(_method|X-HTTP-Method|X-HTTP-Method-Override|X-Method-Override):",
]

# Các mẫu regex để phát hiện HTTP Parameter Pollution
HTTP_POLLUTION_PATTERNS = [
    r"[&\?][^=]*?=[^&]*?[&\?][^=]*?=",
    r"[&\?][^=]*?=[^&]*?%26[^=]*?=",
    r"[&\?][^=]*?=[^&]*?%3F[^=]*?=",
]

# Tổng hợp tất cả các mẫu regex theo loại tấn công
ATTACK_PATTERNS = {
    AttackType.SQL_INJECTION: SQL_INJECTION_PATTERNS,
    AttackType.XSS: XSS_PATTERNS,
    AttackType.PATH_TRAVERSAL: PATH_TRAVERSAL_PATTERNS,
    AttackType.COMMAND_INJECTION: COMMAND_INJECTION_PATTERNS,
    AttackType.OPEN_REDIRECT: OPEN_REDIRECT_PATTERNS,
    AttackType.SSRF: SSRF_PATTERNS,
    AttackType.XXE: XXE_PATTERNS,
    AttackType.CSRF: CSRF_PATTERNS,
    AttackType.LDAP_INJECTION: LDAP_INJECTION_PATTERNS,
    AttackType.NOSQL_INJECTION: NOSQL_INJECTION_PATTERNS,
    AttackType.HTTP_METHOD_OVERRIDE: HTTP_METHOD_OVERRIDE_PATTERNS,
    AttackType.HTTP_POLLUTION: HTTP_POLLUTION_PATTERNS,
}

# Danh sách các header an toàn không cần kiểm tra
SAFE_HEADERS = {
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "connection",
    "content-length",
    "host",
    "pragma",
    "user-agent",
}

# Danh sách các tham số request có thể nhạy cảm
SENSITIVE_PARAMS = {
    "password",
    "token",
    "api_key",
    "apikey",
    "secret",
    "pass",
    "pwd",
    "credentials",
    "auth",
    "session",
}

# Mức độ nghiêm trọng của các loại tấn công
ATTACK_SEVERITY = {
    AttackType.SQL_INJECTION: "high",
    AttackType.XSS: "medium",
    AttackType.PATH_TRAVERSAL: "high",
    AttackType.COMMAND_INJECTION: "critical",
    AttackType.OPEN_REDIRECT: "medium",
    AttackType.SSRF: "high",
    AttackType.XXE: "high",
    AttackType.CSRF: "medium",
    AttackType.LDAP_INJECTION: "high",
    AttackType.NOSQL_INJECTION: "high",
    AttackType.HTTP_METHOD_OVERRIDE: "low",
    AttackType.HTTP_POLLUTION: "low",
}

# Các đường dẫn được miễn kiểm tra WAF
WHITELISTED_PATHS = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/favicon.ico",
    "/metrics",
    "/static/",
]

# Cấu hình mặc định cho WAF
DEFAULT_WAF_CONFIG = {
    "enabled": True,
    "block_attacks": True,  # Tự động chặn các tấn công phát hiện được
    "log_all_requests": False,  # Log tất cả request hay chỉ log các tấn công
    "whitelist_ips": [],  # Danh sách IP không kiểm tra
    "blacklist_ips": [],  # Danh sách IP tự động chặn
    "whitelisted_paths": WHITELISTED_PATHS,
    "check_query_params": True,  # Kiểm tra query parameters
    "check_request_body": True,  # Kiểm tra request body
    "check_headers": True,  # Kiểm tra headers
    "check_cookies": True,  # Kiểm tra cookies
    "enabled_attack_types": [  # Các loại tấn công được phát hiện
        AttackType.SQL_INJECTION,
        AttackType.XSS,
        AttackType.PATH_TRAVERSAL,
        AttackType.COMMAND_INJECTION,
        AttackType.OPEN_REDIRECT,
        AttackType.SSRF,
        AttackType.XXE,
    ],
    "blocked_attack_types": [  # Các loại tấn công tự động chặn
        AttackType.SQL_INJECTION,
        AttackType.COMMAND_INJECTION,
        AttackType.PATH_TRAVERSAL,
        AttackType.XXE,
    ],
    "min_attack_score": 75,  # Điểm tối thiểu để xác định là tấn công (0-100)
    "max_request_size": 10 * 1024 * 1024,  # Kích thước request tối đa (10MB)
}


# Hàm để biên dịch regex patterns
def compile_patterns() -> Dict[str, List[Pattern]]:
    """
    Biên dịch tất cả regex patterns để tối ưu hiệu suất.

    Returns:
        Dict các patterns đã được biên dịch
    """
    compiled_patterns = {}

    for attack_type, patterns in ATTACK_PATTERNS.items():
        compiled_patterns[attack_type] = [
            re.compile(pattern, re.IGNORECASE) for pattern in patterns
        ]

    return compiled_patterns


# Biên dịch sẵn các patterns
try:
    COMPILED_PATTERNS = compile_patterns()
except Exception as e:
    import logging

    logging.error(f"Lỗi khi biên dịch WAF patterns: {str(e)}")
    COMPILED_PATTERNS = {}
