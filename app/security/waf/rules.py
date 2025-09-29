import re
from typing import Dict, List, Pattern, Optional
from app.core.constants import ATTACK_PATTERNS

# Biên dịch regex trước để tối ưu hiệu suất
COMPILED_PATTERNS: Dict[str, List[Pattern]] = {
    attack_type: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for attack_type, patterns in ATTACK_PATTERNS.items()
}

def detect_sql_injection(value: str) -> bool:
    """
    Phát hiện các mẫu tấn công SQL injection trong chuỗi.
    
    Args:
        value: Chuỗi cần kiểm tra
        
    Returns:
        True nếu phát hiện tấn công, False nếu không
    """
    patterns = COMPILED_PATTERNS.get("SQL_INJECTION", [])
    return any(pattern.search(value) for pattern in patterns)

def detect_xss(value: str) -> bool:
    """
    Phát hiện các mẫu tấn công Cross-Site Scripting (XSS) trong chuỗi.
    
    Args:
        value: Chuỗi cần kiểm tra
        
    Returns:
        True nếu phát hiện tấn công, False nếu không
    """
    patterns = COMPILED_PATTERNS.get("XSS", [])
    return any(pattern.search(value) for pattern in patterns)

def detect_path_traversal(value: str) -> bool:
    """
    Phát hiện các mẫu tấn công Path Traversal trong chuỗi.
    
    Args:
        value: Chuỗi cần kiểm tra
        
    Returns:
        True nếu phát hiện tấn công, False nếu không
    """
    patterns = COMPILED_PATTERNS.get("PATH_TRAVERSAL", [])
    return any(pattern.search(value) for pattern in patterns)

def check_attack_vectors(value: str, attack_types: Optional[List[str]] = None) -> Dict[str, bool]:
    """
    Kiểm tra nhiều vector tấn công trong một chuỗi.
    
    Args:
        value: Chuỗi cần kiểm tra
        attack_types: Danh sách loại tấn công cần kiểm tra, nếu None sẽ kiểm tra tất cả
        
    Returns:
        Dict kết quả với khóa là loại tấn công, giá trị là True nếu phát hiện tấn công
    """
    if attack_types is None:
        attack_types = list(COMPILED_PATTERNS.keys())
        
    results = {}
    for attack_type in attack_types:
        patterns = COMPILED_PATTERNS.get(attack_type, [])
        results[attack_type] = any(pattern.search(value) for pattern in patterns)
        
    return results
