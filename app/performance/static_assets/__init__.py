"""
Module tối ưu tài nguyên tĩnh (Static Assets) - Công cụ tối ưu hóa tài nguyên web tĩnh.

Module này cung cấp:
- Tối ưu hóa hình ảnh (nén, resize, chuyển đổi định dạng)
- Minify CSS và JavaScript
- Nén tài nguyên (gzip, brotli)
- Hash và versioning tài nguyên
"""

from app.performance.static_assets.optimizer import (
    AssetOptimizer,
    AssetType,
    ImageFormat,
    CompressionType,
)

from app.logging.setup import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)

# Khởi tạo singleton instance
_asset_optimizer = None


def get_asset_optimizer():
    """
    Lấy hoặc khởi tạo Asset Optimizer.

    Returns:
        AssetOptimizer instance
    """
    global _asset_optimizer
    if _asset_optimizer is None:
        _asset_optimizer = AssetOptimizer(
            output_dir=settings.STATIC_FILES_DIR,
            optimize_images=True,
            optimize_css=True,
            optimize_js=True,
            compress_assets=True,
            image_quality=settings.IMAGE_QUALITY,
        )
        logger.info("Đã khởi tạo Asset Optimizer")
    return _asset_optimizer


# Các hàm tiện ích để dễ dàng sử dụng
async def optimize_image(file_path, output_formats=None, quality=None, max_width=None):
    """
    Tối ưu hóa hình ảnh với nhiều định dạng.

    Args:
        file_path: Đường dẫn hình ảnh
        output_formats: Các định dạng đầu ra (mặc định: webp, jpg)
        quality: Chất lượng hình ảnh (0-100)
        max_width: Chiều rộng tối đa

    Returns:
        Dict[str, str] chứa URL của các định dạng hình ảnh
    """
    optimizer = get_asset_optimizer()
    return await optimizer.optimize_image(
        file_path=file_path,
        output_formats=output_formats or [ImageFormat.WEBP, ImageFormat.JPEG],
        quality=quality or settings.IMAGE_QUALITY,
        max_width=max_width,
    )


async def optimize_css(file_path):
    """
    Tối ưu hóa và minify file CSS.

    Args:
        file_path: Đường dẫn file CSS

    Returns:
        Đường dẫn file CSS đã tối ưu
    """
    optimizer = get_asset_optimizer()
    return await optimizer.minify_css(file_path)


async def optimize_js(file_path):
    """
    Tối ưu hóa và minify file JavaScript.

    Args:
        file_path: Đường dẫn file JavaScript

    Returns:
        Đường dẫn file JavaScript đã tối ưu
    """
    optimizer = get_asset_optimizer()
    return await optimizer.minify_js(file_path)


async def optimize_directory(directory_path, recursive=True):
    """
    Tối ưu hóa toàn bộ thư mục tài nguyên tĩnh.

    Args:
        directory_path: Đường dẫn thư mục
        recursive: Tối ưu đệ quy trong thư mục con

    Returns:
        Dict chứa kết quả tối ưu
    """
    optimizer = get_asset_optimizer()
    return await optimizer.optimize_directory(
        directory_path=directory_path, recursive=recursive
    )


# Export các components
__all__ = [
    "AssetOptimizer",
    "AssetType",
    "ImageFormat",
    "CompressionType",
    "get_asset_optimizer",
    "optimize_image",
    "optimize_css",
    "optimize_js",
    "optimize_directory",
]
