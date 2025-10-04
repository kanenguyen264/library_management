from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings as PydanticBaseSettings


class BaseSettings(PydanticBaseSettings):
    # ===============================
    # APPLICATION SETTINGS
    # ===============================
    PROJECT_NAME: str = "Book Reading API"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = (
        "A comprehensive book reading platform with user management and analytics"
    )

    # ===============================
    # API SETTINGS
    # ===============================
    API_V1_STR: str = "/api/v1"

    # ===============================
    # JWT ALGORITHM
    # ===============================
    ALGORITHM: str = "HS256"

    # ===============================
    # PAGINATION SETTINGS
    # ===============================
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # ===============================
    # UPLOAD SETTINGS
    # ===============================
    UPLOAD_FOLDER: str = "static/uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "gif", "pdf", "epub"]

    # ===============================
    # SMTP SETTINGS
    # ===============================
    SMTP_PORT: int = 587
    SMTP_TLS: bool = True

    # ===============================
    # REDIS SETTINGS
    # ===============================
    REDIS_EXPIRE: int = 3600  # 1 hour

    # ===============================
    # RATE LIMITING
    # ===============================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100

    # ===============================
    # COMPUTED PROPERTIES
    # ===============================
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == "testing"

    model_config = {
        "case_sensitive": True,
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
