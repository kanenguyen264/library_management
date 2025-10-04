import os
from typing import Union

from .base import BaseSettings
from .development import DevelopmentSettings
from .production import ProductionSettings


def get_settings() -> Union[DevelopmentSettings, ProductionSettings]:
    """
    Factory function to get the appropriate settings instance.
    
    Returns:
        Settings instance based on ENVIRONMENT variable:
        - If ENVIRONMENT=development: Uses hardcoded values (no .env needed)
        - If ENVIRONMENT=production: Loads secrets from .env file
    """
    environment = os.getenv("ENVIRONMENT", "development").lower()
    
    if environment == "production":
        return ProductionSettings()
    else:
        return DevelopmentSettings()


# Global settings instance
settings = get_settings()

# Export for easy imports
__all__ = ["settings", "get_settings"] 