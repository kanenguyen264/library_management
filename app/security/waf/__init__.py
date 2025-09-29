from fastapi import FastAPI
from app.security.waf.middleware import WAFMiddleware
from app.security.waf.rules import (
    check_attack_vectors,
    detect_sql_injection,
    detect_xss,
    detect_path_traversal,
)
from app.security.waf.config import (
    AttackType,
    ATTACK_PATTERNS,
    COMPILED_PATTERNS,
    DEFAULT_WAF_CONFIG,
)
from app.logging.setup import get_logger

logger = get_logger(__name__)


def setup_waf(app: FastAPI) -> None:
    """
    Thiết lập Web Application Firewall cho ứng dụng FastAPI.

    Args:
        app: Ứng dụng FastAPI
    """
    # Thêm WAF middleware vào ứng dụng
    app.add_middleware(WAFMiddleware)

    logger.info("Đã thiết lập Web Application Firewall (WAF) cho ứng dụng")

    # Log số lượng patterns đã tải
    pattern_count = sum(len(patterns) for patterns in ATTACK_PATTERNS.values())
    logger.info(
        f"WAF đã tải {pattern_count} mẫu tấn công cho {len(ATTACK_PATTERNS)} loại tấn công"
    )


__all__ = [
    "WAFMiddleware",
    "setup_waf",
    "check_attack_vectors",
    "detect_sql_injection",
    "detect_xss",
    "detect_path_traversal",
    "AttackType",
    "ATTACK_PATTERNS",
    "COMPILED_PATTERNS",
    "DEFAULT_WAF_CONFIG",
]
