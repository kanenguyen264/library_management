"""
Cấu hình logging cho ứng dụng.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional

# Các mặc định chung
DEFAULT_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "json": {"()": "app.logging.formatters.JSONFormatter"},
        "colorized": {"()": "app.logging.formatters.ColorizedFormatter"},
        "secure": {"()": "app.logging.formatters.SecureFormatter"},
    },
    "filters": {
        "sensitive_data": {"()": "app.logging.filters.SensitiveDataFilter"},
        "security_audit": {"()": "app.logging.filters.SecurityAuditFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "colorized",
            "filters": ["sensitive_data"],
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "app.logging.handlers.RotatingSecureFileHandler",
            "level": "INFO",
            "formatter": "secure",
            "filters": ["sensitive_data"],
            "filename": "logs/app.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "permissions": 0o600,  # -rw-------
        },
        "security_file": {
            "class": "app.logging.handlers.RotatingSecureFileHandler",
            "level": "INFO",
            "formatter": "json",
            "filters": ["sensitive_data", "security_audit"],
            "filename": "logs/security.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10,
            "permissions": 0o600,  # -rw-------
        },
        "error_file": {
            "class": "app.logging.handlers.RotatingSecureFileHandler",
            "level": "ERROR",
            "formatter": "json",
            "filters": ["sensitive_data"],
            "filename": "logs/error.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10,
            "permissions": 0o600,  # -rw-------
        },
    },
    "loggers": {
        "app": {"level": "INFO", "handlers": ["console", "file"], "propagate": False},
        "app.security": {
            "level": "INFO",
            "handlers": ["console", "security_file"],
            "propagate": False,
        },
        "app.admin_site": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "app.user_site": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "app.errors": {
            "level": "ERROR",
            "handlers": ["console", "error_file"],
            "propagate": False,
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}

# Cấu hình cho môi trường development
DEVELOPMENT_LOGGING_CONFIG = DEFAULT_LOGGING_CONFIG.copy()
DEVELOPMENT_LOGGING_CONFIG.update(
    {
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "colorized",
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "app": {"level": "DEBUG", "handlers": ["console"], "propagate": False}
        },
        "root": {"level": "INFO", "handlers": ["console"]},
    }
)

# Cấu hình cho môi trường production
PRODUCTION_LOGGING_CONFIG = DEFAULT_LOGGING_CONFIG.copy()
PRODUCTION_LOGGING_CONFIG.update(
    {
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "json",
                "filters": ["sensitive_data"],
                "stream": "ext://sys.stdout",
            },
            "slack": {
                "class": "app.logging.handlers.SlackHandler",
                "level": "ERROR",
                "formatter": "secure",
                "webhook_url": os.environ.get("SLACK_WEBHOOK_URL", ""),
                "channel": os.environ.get("SLACK_CHANNEL", "#alerts"),
            },
            "database": {
                "class": "app.logging.handlers.DatabaseHandler",
                "level": "WARNING",
                "session_maker": "app.common.db.session.engine",
            },
        },
        "loggers": {
            "app": {
                "level": "INFO",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "app.security": {
                "level": "INFO",
                "handlers": ["console", "security_file", "slack", "database"],
                "propagate": False,
            },
            "app.errors": {
                "level": "ERROR",
                "handlers": ["console", "error_file", "slack", "database"],
                "propagate": False,
            },
        },
    }
)

# Cấu hình cho môi trường testing
TESTING_LOGGING_CONFIG = DEFAULT_LOGGING_CONFIG.copy()
TESTING_LOGGING_CONFIG.update(
    {
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "app": {"level": "WARNING", "handlers": ["console"], "propagate": False}
        },
        "root": {"level": "WARNING", "handlers": ["console"]},
    }
)

# Cấu hình riêng cho admin site
ADMIN_SITE_LOGGING_CONFIG = {
    "handlers": {
        "admin_file": {
            "class": "app.logging.handlers.RotatingSecureFileHandler",
            "level": "INFO",
            "formatter": "json",
            "filters": ["sensitive_data"],
            "filename": "logs/admin.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "permissions": 0o600,  # -rw-------
        },
        "admin_audit": {
            "class": "app.logging.handlers.RotatingSecureFileHandler",
            "level": "INFO",
            "formatter": "json",
            "filename": "logs/admin_audit.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10,
            "permissions": 0o600,  # -rw-------
        },
    },
    "loggers": {
        "app.admin_site": {
            "level": "INFO",
            "handlers": ["console", "admin_file"],
            "propagate": False,
        },
        "app.admin_site.audit": {
            "level": "INFO",
            "handlers": ["console", "admin_audit"],
            "propagate": False,
        },
    },
}

# Cấu hình riêng cho user site
USER_SITE_LOGGING_CONFIG = {
    "handlers": {
        "user_file": {
            "class": "app.logging.handlers.RotatingSecureFileHandler",
            "level": "INFO",
            "formatter": "json",
            "filters": ["sensitive_data"],
            "filename": "logs/user.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "permissions": 0o600,  # -rw-------
        }
    },
    "loggers": {
        "app.user_site": {
            "level": "INFO",
            "handlers": ["console", "user_file"],
            "propagate": False,
        }
    },
}

# Các field nhạy cảm cần che dấu
SENSITIVE_FIELDS = [
    "password",
    "secret",
    "token",
    "key",
    "auth",
    "credit",
    "card",
    "ssn",
    "social",
    "account",
    "api_key",
    "authorization",
    "security",
    "private",
    "credentials",
    "session",
]
