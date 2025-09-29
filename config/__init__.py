"""
Chọn cấu hình dựa trên biến môi trường
"""
import os
from typing import Union

from config.development import settings as development_settings
from config.production import settings as production_settings
from config.testing import settings as testing_settings

# Lấy môi trường từ biến môi trường, mặc định là development
environment = os.getenv("APP_ENV", "development").lower()

# Chọn cấu hình phù hợp
if environment == "production":
    settings = production_settings
elif environment == "testing":
    settings = testing_settings
else:
    settings = development_settings
