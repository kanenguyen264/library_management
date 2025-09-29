"""
Module CDN (Content Delivery Network) - Quản lý và tối ưu phân phối nội dung tĩnh.

Module này cung cấp:
- Quản lý nội dung qua CDN
- Upload và đồng bộ tài sản tĩnh
- Version và cache control cho tài nguyên
- Invalidation cache CDN
"""

from app.performance.cdn.cdn_manager import CDNManager, CDNProvider, LocalCDNProvider

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo singleton CDN Manager
_cdn_manager = None


def get_cdn_manager(**kwargs):
    """
    Lấy hoặc khởi tạo singleton CDN Manager.

    Args:
        **kwargs: Tham số cấu hình cho CDN Manager nếu chưa được khởi tạo

    Returns:
        CDNManager instance
    """
    global _cdn_manager
    if _cdn_manager is None:
        # Khởi tạo provider dựa trên cấu hình
        provider = None

        # Thêm các providers khác dựa trên cấu hình
        if settings.CDN_PROVIDER == "local":
            provider = LocalCDNProvider(
                storage_path=settings.STATIC_FILES_DIR, base_url=settings.STATIC_URL
            )
        elif settings.CDN_PROVIDER == "s3":
            # Khi có thêm provider AWS S3, có thể bổ sung tại đây
            pass
        elif settings.CDN_PROVIDER == "cloudfront":
            # Khi có thêm provider Cloudfront, có thể bổ sung tại đây
            pass

        # Tạo CDN Manager với provider đã chọn
        _cdn_manager = CDNManager(
            provider=provider,
            asset_root=settings.STATIC_FILES_DIR,
            cache_max_age=settings.CDN_CACHE_MAX_AGE,
            **kwargs,
        )

        logger.info(f"Đã khởi tạo CDN Manager với provider: {settings.CDN_PROVIDER}")

    return _cdn_manager


# Các hàm tiện ích để sử dụng trực tiếp
async def upload_asset(file_path, cdn_path=None):
    """
    Upload tài sản lên CDN.

    Args:
        file_path: Đường dẫn file cần upload
        cdn_path: Đường dẫn trên CDN (nếu None, sẽ dùng tên file)

    Returns:
        URL của tài sản trên CDN
    """
    cdn = get_cdn_manager()
    return await cdn.upload_asset(file_path, cdn_path)


async def get_asset_url(asset_path):
    """
    Lấy URL đầy đủ của tài sản trên CDN.

    Args:
        asset_path: Đường dẫn tài sản

    Returns:
        URL đầy đủ của tài sản
    """
    cdn = get_cdn_manager()
    return await cdn.get_asset_url(asset_path)


async def invalidate_assets(asset_paths):
    """
    Vô hiệu hóa cache CDN cho các tài sản.

    Args:
        asset_paths: Danh sách đường dẫn tài sản cần vô hiệu hóa

    Returns:
        True nếu thành công
    """
    cdn = get_cdn_manager()
    return await cdn.invalidate_assets(asset_paths)


# Export các components
__all__ = [
    "CDNManager",
    "CDNProvider",
    "LocalCDNProvider",
    "get_cdn_manager",
    "upload_asset",
    "get_asset_url",
    "invalidate_assets",
]
