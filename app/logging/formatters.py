import json
import logging
import datetime
from typing import Any, Dict, Optional, List

class JSONFormatter(logging.Formatter):
    """
    Format log messages as JSON for machine readability.
    Hữu ích cho việc phân tích log bằng các công cụ như ELK stack.
    """
    
    def __init__(
        self,
        fields_to_hide: Optional[List[str]] = None,
        time_format: str = "%Y-%m-%d %H:%M:%S"
    ):
        super().__init__()
        self.fields_to_hide = fields_to_hide or ["password", "token", "secret"]
        self.time_format = time_format
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record thành JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON string
        """
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime(self.time_format),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }
        
        # Add exception info if exists
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        # Add all extra attributes from the record
        for key, value in record.__dict__.items():
            if key not in log_data and not key.startswith("_") and key != "msg" and key != "args":
                # Hide sensitive fields
                if any(field in key.lower() for field in self.fields_to_hide):
                    log_data[key] = "***REDACTED***"
                else:
                    # Try to serialize complex objects
                    try:
                        json.dumps({key: value})
                        log_data[key] = value
                    except (TypeError, OverflowError):
                        log_data[key] = str(value)
        
        return json.dumps(log_data)

class ColorizedFormatter(logging.Formatter):
    """
    Format log messages with colors for better readability in console.
    """
    
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[41m",   # Red background
        "RESET": "\033[0m"        # Reset
    }
    
    def __init__(self, fmt: str = None, time_format: str = "%Y-%m-%d %H:%M:%S"):
        if not fmt:
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        super().__init__(fmt=fmt, datefmt=time_format)
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with colors.
        
        Args:
            record: Log record to format
            
        Returns:
            Colorized log message
        """
        log_message = super().format(record)
        level_name = record.levelname
        
        if level_name in self.COLORS:
            return f"{self.COLORS[level_name]}{log_message}{self.COLORS['RESET']}"
        return log_message

class SecureFormatter(logging.Formatter):
    """
    Format log messages with sensitive data masked.
    """
    
    def __init__(
        self,
        fmt: str = None,
        datefmt: str = None,
        sensitive_fields: Optional[List[str]] = None,
        mask_char: str = "*"
    ):
        if not fmt:
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.sensitive_fields = sensitive_fields or [
            "password", "token", "secret", "key", "auth", "credit_card",
            "ssn", "social", "account", "id_number"
        ]
        self.mask_char = mask_char
    
    def _mask_sensitive_data(self, message: str) -> str:
        """
        Mask sensitive data in log message.
        
        Args:
            message: Original log message
            
        Returns:
            Masked log message
        """
        for field in self.sensitive_fields:
            # Match patterns like password=123456 or "password":"123456"
            patterns = [
                rf'({field}=)([^,\s]+)',                   # password=123456
                rf'("{field}"\s*:\s*)"([^"]+)"',           # "password":"123456"
                rf"('{field}'\s*:\s*)'([^']+)'",           # 'password':'123456'
                rf'({field}:\s+)([^\s,]+)',                # password: 123456
            ]
            
            for pattern in patterns:
                import re
                message = re.sub(
                    pattern,
                    lambda m: f"{m.group(1)}{self.mask_char * min(8, len(m.group(2)))}",
                    message
                )
                
        return message
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with sensitive data masked.
        
        Args:
            record: Log record to format
            
        Returns:
            Masked log message
        """
        record.msg = self._mask_sensitive_data(str(record.msg))
        return super().format(record)
