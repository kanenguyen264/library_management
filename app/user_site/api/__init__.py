"""
API User Site - User-facing API endpoints cho ứng dụng đọc sách.

Tập hợp các API dùng cho phía người dùng, không bao gồm các API quản trị.
"""

from app.user_site.api.router import setup_routers

__all__ = ["setup_routers"]
