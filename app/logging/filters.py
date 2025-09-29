import logging
from typing import List, Optional, Set, Union

class SensitiveDataFilter(logging.Filter):
    """
    Filter để che giấu thông tin nhạy cảm trong log messages.
    """
    
    def __init__(
        self, 
        name: str = "",
        sensitive_fields: Optional[List[str]] = None,
        replacement: str = "***REDACTED***"
    ):
        super().__init__(name)
        self.sensitive_fields = sensitive_fields or [
            "password", "secret", "token", "key", "auth", 
            "credit", "card", "ssn", "social", "account"
        ]
        self.replacement = replacement
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record, masking sensitive data.
        
        Args:
            record: Log record to filter
            
        Returns:
            True to include the record in log output
        """
        # Create a copy of the original message
        if not hasattr(record, "original_msg"):
            record.original_msg = record.msg
            
        # Get the message as string
        msg = str(record.original_msg)
        
        # Replace sensitive data in message
        for field in self.sensitive_fields:
            # Simple pattern matching for common formats
            patterns = [
                f"{field}=", f"{field}:", f'"{field}":', f"'{field}':"
            ]
            
            for pattern in patterns:
                idx = msg.lower().find(pattern)
                if idx >= 0:
                    # Find the start and end of the value
                    start = idx + len(pattern)
                    # Skip whitespace
                    while start < len(msg) and msg[start].isspace():
                        start += 1
                        
                    # Find the end of the value
                    end = start
                    if start < len(msg):
                        if msg[start] in ('"', "'"):
                            # Quoted string
                            quote = msg[start]
                            start += 1
                            end = msg.find(quote, start)
                            if end < 0:
                                end = len(msg)
                        else:
                            # Unquoted value
                            while end < len(msg) and msg[end] not in (' ', ',', ';', '\n', '\t'):
                                end += 1
                    
                    # Replace the value
                    if end > start:
                        msg = msg[:start] + self.replacement + msg[end:]
        
        # Update the record message
        record.msg = msg
        
        return True

class PathFilter(logging.Filter):
    """
    Filter để chỉ log các message từ các module được chỉ định.
    """
    
    def __init__(self, paths: Union[List[str], Set[str]]):
        super().__init__()
        self.paths = set(paths)
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record based on its path.
        
        Args:
            record: Log record to filter
            
        Returns:
            True if the record should be included in log output
        """
        if not self.paths:
            return True
            
        # Check if the record's module path starts with any of our paths
        return any(record.name.startswith(path) for path in self.paths)

class SecurityAuditFilter(logging.Filter):
    """
    Filter để log chi tiết các sự kiện bảo mật quan trọng.
    """
    
    def __init__(
        self,
        name: str = "",
        security_levels: Optional[List[str]] = None
    ):
        super().__init__(name)
        self.security_levels = set(security_levels or ["WARNING", "ERROR", "CRITICAL"])
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record based on security criteria.
        
        Args:
            record: Log record to filter
            
        Returns:
            True if the record should be included in security audit logs
        """
        # Always include security-related logs
        if record.name.startswith("app.security"):
            return True
            
        # Include authentication logs
        if record.name.startswith("app.common.security.auth"):
            return True
            
        # Include logs with security-related keywords
        msg = record.getMessage().lower()
        security_keywords = [
            "login", "auth", "password", "token", "permission", "access", 
            "security", "attack", "injection", "xss", "csrf", "hack", "exploit",
            "vulnerability", "breach", "unauthorized", "forbidden"
        ]
        
        if any(keyword in msg for keyword in security_keywords):
            return True
            
        # Include specific security levels
        if record.levelname in self.security_levels:
            return True
            
        return False
