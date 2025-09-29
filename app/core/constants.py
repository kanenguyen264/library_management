# Các hằng số ứng dụng
API_V1_PREFIX = "/api/v1"

# Status codes
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Roles
ROLE_ADMIN = "admin"
ROLE_SUPERADMIN = "superadmin"
ROLE_USER = "user"

# Security logs
AUTH_FAILED = "auth_failed"
AUTH_SUCCESS = "auth_success"
PERMISSION_DENIED = "permission_denied"
RESOURCE_ACCESS = "resource_access"
SECURITY_EVENT = "security_event"

# Rate limiting
RATE_LIMIT_PREFIX = "ratelimit"
RATE_LIMIT_RESET = 60  # seconds

# Cache
CACHE_PREFIX = "readingbook"
CACHE_DEFAULT_TIMEOUT = 60 * 30  # 30 minutes

# Security attack patterns
ATTACK_PATTERNS = {
    "SQL_INJECTION": [
        r"(\%27)|(\')|(\-\-)|(\%23)|(#)",
        r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",
        r"((\%27)|(\'))(\%6F|o|\%4F)(\%72|r|\%52)",
    ],
    "XSS": [
        r"<[^\w<>]*(?:[^<>\"'\s]*:)?[^\w<>]*(?:\W*s\W*c\W*r\W*i\W*p\W*t|\W*f\W*o\W*r\W*m|\W*s\W*t\W*y\W*l\W*e|\W*o\W*b\W*j\W*e\W*c\W*t|\W*a\W*p\W*p\W*l\W*e\W*t|\W*e\W*m\W*b\W*e\W*d)",
        r"((\%3C)|<)((\%2F)|\/)*[a-z0-9\%]+((\%3E)|>)",
        r"((\%3C)|<)[^\n]+((\%3E)|>)",
    ],
    "PATH_TRAVERSAL": [
        r"\.\.\/",
        r"\.\.\\",
        r"%2e%2e%2f",
        r"%252e%252e%252f",
        r"\.\.%2f",
        r"\.\.%5c",
    ],
}
