from typing import Dict, List, Any, Optional, Union, Tuple, Set
import os
import time
import asyncio
import hashlib
import mimetypes
import logging
import json
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
import re
from urllib.parse import urlparse, urljoin
import subprocess
from PIL import Image
import io
import gzip
import brotli
from html.parser import HTMLParser
import cssmin
import jsmin
import httpx

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.performance.cdn.cdn_manager import cdn_manager

settings = get_settings()
logger = get_logger(__name__)

class AssetType:
    """Các loại tài nguyên tĩnh."""
    IMAGE = "image"
    CSS = "css"
    JS = "js"
    HTML = "html"
    FONT = "font"
    OTHER = "other"

class ImageFormat:
    """Các định dạng ảnh."""
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    AVIF = "avif"

class CompressionType:
    """Các loại nén."""
    GZIP = "gzip"
    BROTLI = "brotli"
    NONE = "none"

class AssetOptimizer:
    """
    Tối ưu tài nguyên tĩnh.
    Cung cấp:
    - Nén ảnh
    - Chuyển đổi định dạng ảnh
    - Minify CSS/JS/HTML
    - Nén files
    - Tối ưu font
    """
    
    def __init__(
        self,
        output_dir: Optional[str] = None,
        optimize_images: bool = True,
        optimize_css: bool = True,
        optimize_js: bool = True,
        optimize_html: bool = True,
        optimize_fonts: bool = False,
        compress_assets: bool = True,
        image_quality: int = 85,
        max_image_width: Optional[int] = 1920,
        webp_quality: int = 80,
        avif_quality: int = 70,
        use_cdn: bool = True
    ):
        """
        Khởi tạo asset optimizer.
        
        Args:
            output_dir: Thư mục output
            optimize_images: Tự động tối ưu ảnh
            optimize_css: Tự động tối ưu CSS
            optimize_js: Tự động tối ưu JS
            optimize_html: Tự động tối ưu HTML
            optimize_fonts: Tự động tối ưu font
            compress_assets: Tự động nén assets
            image_quality: Chất lượng ảnh JPEG (0-100)
            max_image_width: Chiều rộng tối đa của ảnh
            webp_quality: Chất lượng WebP (0-100)
            avif_quality: Chất lượng AVIF (0-100)
            use_cdn: Sử dụng CDN
        """
        # Thư mục output
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self.output_dir = output_dir or os.path.join(base_dir, "static", "optimized")
        
        # Tạo thư mục nếu chưa tồn tại
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Cấu hình tối ưu
        self.optimize_images = optimize_images
        self.optimize_css = optimize_css
        self.optimize_js = optimize_js
        self.optimize_html = optimize_html
        self.optimize_fonts = optimize_fonts
        self.compress_assets = compress_assets
        
        # Cấu hình ảnh
        self.image_quality = image_quality
        self.max_image_width = max_image_width
        self.webp_quality = webp_quality
        self.avif_quality = avif_quality
        
        # Sử dụng CDN
        self.use_cdn = use_cdn
        
        logger.info(
            f"Khởi tạo AssetOptimizer với output_dir='{self.output_dir}', "
            f"optimize_images={optimize_images}, optimize_css={optimize_css}, "
            f"optimize_js={optimize_js}, optimize_html={optimize_html}, "
            f"compress_assets={compress_assets}, use_cdn={use_cdn}"
        )
        
    def _get_asset_type(self, file_path: str) -> str:
        """
        Xác định loại tài nguyên.
        
        Args:
            file_path: Đường dẫn file
            
        Returns:
            Loại tài nguyên
        """
        # Lấy extension
        ext = os.path.splitext(file_path)[1].lower()
        
        # Xác định loại
        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"]:
            return AssetType.IMAGE
        elif ext in [".css", ".scss", ".sass", ".less"]:
            return AssetType.CSS
        elif ext in [".js", ".mjs", ".ts"]:
            return AssetType.JS
        elif ext in [".html", ".htm", ".xhtml"]:
            return AssetType.HTML
        elif ext in [".ttf", ".otf", ".woff", ".woff2", ".eot"]:
            return AssetType.FONT
        else:
            return AssetType.OTHER
            
    def _get_output_path(self, file_path: str, suffix: str = "", new_ext: Optional[str] = None) -> str:
        """
        Tạo đường dẫn output.
        
        Args:
            file_path: Đường dẫn file gốc
            suffix: Hậu tố thêm vào tên file
            new_ext: Phần mở rộng mới
            
        Returns:
            Đường dẫn output
        """
        # Lấy tên file và extension
        filename, ext = os.path.splitext(os.path.basename(file_path))
        
        # Thay extension nếu có
        if new_ext:
            ext = new_ext if new_ext.startswith(".") else f".{new_ext}"
            
        # Tạo tên file mới
        new_filename = f"{filename}{suffix}{ext}"
        
        # Tạo đường dẫn output
        rel_dir = os.path.dirname(os.path.relpath(file_path, os.path.dirname(self.output_dir)))
        output_dir = os.path.join(self.output_dir, rel_dir)
        
        # Tạo thư mục nếu chưa tồn tại
        os.makedirs(output_dir, exist_ok=True)
        
        return os.path.join(output_dir, new_filename)
        
    async def optimize_image(
        self,
        file_path: str,
        output_formats: Optional[List[str]] = None,
        quality: Optional[int] = None,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        upload_to_cdn: bool = True
    ) -> Dict[str, str]:
        """
        Tối ưu ảnh.
        
        Args:
            file_path: Đường dẫn ảnh
            output_formats: Các định dạng output
            quality: Chất lượng ảnh (0-100)
            max_width: Chiều rộng tối đa
            max_height: Chiều cao tối đa
            upload_to_cdn: Upload lên CDN
            
        Returns:
            Dict {format: url}
        """
        try:
            # Các định dạng output
            output_formats = output_formats or [ImageFormat.WEBP]
            
            # Các tham số mặc định
            quality = quality or self.image_quality
            max_width = max_width or self.max_image_width
            
            # Kết quả
            result = {}
            
            # Đọc ảnh
            async with aiofiles.open(file_path, "rb") as f:
                img_data = await f.read()
                img = Image.open(io.BytesIO(img_data))
                
            # Resize nếu cần
            original_width, original_height = img.size
            if max_width and max_width < original_width:
                # Tính tỷ lệ
                ratio = max_width / original_width
                new_height = int(original_height * ratio)
                
                # Resize
                img = img.resize((max_width, new_height), Image.LANCZOS)
                
            # Giới hạn chiều cao nếu cần
            if max_height and img.size[1] > max_height:
                # Tính tỷ lệ
                ratio = max_height / img.size[1]
                new_width = int(img.size[0] * ratio)
                
                # Resize
                img = img.resize((new_width, max_height), Image.LANCZOS)
                
            # Định dạng gốc
            original_format = file_path.split(".")[-1].lower()
            if original_format in ["jpg", "jpeg"]:
                original_format = ImageFormat.JPEG
            elif original_format in ["png"]:
                original_format = ImageFormat.PNG
            
            # Tối ưu ảnh theo từng định dạng
            for output_format in output_formats:
                # Tạo đường dẫn output
                output_path = self._get_output_path(file_path, new_ext=output_format)
                
                # Xử lý theo định dạng
                if output_format == ImageFormat.WEBP:
                    # Lưu ảnh WebP
                    webp_quality = self.webp_quality
                    img.save(output_path, "WEBP", quality=webp_quality, method=6)
                    
                elif output_format == ImageFormat.AVIF:
                    # Kiểm tra xem pillow có hỗ trợ AVIF không
                    if "AVIF" in Image.registered_extensions():
                        avif_quality = self.avif_quality
                        img.save(output_path, "AVIF", quality=avif_quality)
                    else:
                        logger.warning("Pillow không hỗ trợ định dạng AVIF, bỏ qua")
                        continue
                        
                elif output_format == ImageFormat.JPEG:
                    # Lưu ảnh JPEG
                    if img.mode == "RGBA":
                        # Chuyển đổi từ RGBA sang RGB
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3])
                        background.save(output_path, "JPEG", quality=quality, optimize=True)
                    else:
                        img.save(output_path, "JPEG", quality=quality, optimize=True)
                        
                elif output_format == ImageFormat.PNG:
                    # Lưu ảnh PNG
                    img.save(output_path, "PNG", optimize=True)
                    
                # Upload lên CDN nếu cần
                if upload_to_cdn and self.use_cdn:
                    cdn_path = os.path.relpath(output_path, self.output_dir)
                    url = await cdn_manager.upload_asset(output_path, cdn_path)
                    result[output_format] = url
                else:
                    # URL cục bộ
                    path = os.path.relpath(output_path, os.path.dirname(os.path.dirname(self.output_dir)))
                    result[output_format] = f"/static/{path}"
                    
            # Đóng ảnh
            img.close()
            
            return result
            
        except Exception as e:
            logger.error(f"Lỗi khi tối ưu ảnh '{file_path}': {str(e)}")
            return {}
            
    async def minify_css(
        self,
        file_path: str,
        upload_to_cdn: bool = True
    ) -> str:
        """
        Minify CSS.
        
        Args:
            file_path: Đường dẫn file CSS
            upload_to_cdn: Upload lên CDN
            
        Returns:
            URL của file đã tối ưu
        """
        try:
            # Tạo đường dẫn output
            output_path = self._get_output_path(file_path, suffix=".min")
            
            # Đọc nội dung file
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                
            # Minify CSS
            minified = cssmin.cssmin(content)
            
            # Lưu file
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(minified)
                
            # Nén file nếu cần
            if self.compress_assets:
                compressed_paths = await self.compress_file(output_path)
                
            # Upload lên CDN nếu cần
            if upload_to_cdn and self.use_cdn:
                cdn_path = os.path.relpath(output_path, self.output_dir)
                url = await cdn_manager.upload_asset(output_path, cdn_path)
                return url
            else:
                # URL cục bộ
                path = os.path.relpath(output_path, os.path.dirname(os.path.dirname(self.output_dir)))
                return f"/static/{path}"
                
        except Exception as e:
            logger.error(f"Lỗi khi minify CSS '{file_path}': {str(e)}")
            return ""
            
    async def minify_js(
        self,
        file_path: str,
        upload_to_cdn: bool = True
    ) -> str:
        """
        Minify JavaScript.
        
        Args:
            file_path: Đường dẫn file JS
            upload_to_cdn: Upload lên CDN
            
        Returns:
            URL của file đã tối ưu
        """
        try:
            # Tạo đường dẫn output
            output_path = self._get_output_path(file_path, suffix=".min")
            
            # Đọc nội dung file
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                
            # Minify JS
            minified = jsmin.jsmin(content)
            
            # Lưu file
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(minified)
                
            # Nén file nếu cần
            if self.compress_assets:
                compressed_paths = await self.compress_file(output_path)
                
            # Upload lên CDN nếu cần
            if upload_to_cdn and self.use_cdn:
                cdn_path = os.path.relpath(output_path, self.output_dir)
                url = await cdn_manager.upload_asset(output_path, cdn_path)
                return url
            else:
                # URL cục bộ
                path = os.path.relpath(output_path, os.path.dirname(os.path.dirname(self.output_dir)))
                return f"/static/{path}"
                
        except Exception as e:
            logger.error(f"Lỗi khi minify JS '{file_path}': {str(e)}")
            return ""
            
    async def compress_file(
        self,
        file_path: str,
        compression_types: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Nén file.
        
        Args:
            file_path: Đường dẫn file
            compression_types: Các loại nén
            
        Returns:
            Dict {compression_type: output_path}
        """
        try:
            # Các loại nén
            compression_types = compression_types or [CompressionType.GZIP, CompressionType.BROTLI]
            
            # Kết quả
            result = {}
            
            # Đọc nội dung file
            async with aiofiles.open(file_path, "rb") as f:
                content = await f.read()
                
            # Nén theo từng loại
            for compression_type in compression_types:
                if compression_type == CompressionType.GZIP:
                    # Tạo đường dẫn output
                    output_path = f"{file_path}.gz"
                    
                    # Nén với gzip
                    compressed = gzip.compress(content, compresslevel=9)
                    
                    # Lưu file
                    async with aiofiles.open(output_path, "wb") as f:
                        await f.write(compressed)
                        
                    result[CompressionType.GZIP] = output_path
                    
                elif compression_type == CompressionType.BROTLI:
                    # Tạo đường dẫn output
                    output_path = f"{file_path}.br"
                    
                    # Nén với brotli
                    compressed = brotli.compress(content, quality=11)
                    
                    # Lưu file
                    async with aiofiles.open(output_path, "wb") as f:
                        await f.write(compressed)
                        
                    result[CompressionType.BROTLI] = output_path
                    
            return result
            
        except Exception as e:
            logger.error(f"Lỗi khi nén file '{file_path}': {str(e)}")
            return {}
            
    async def optimize_directory(
        self,
        directory_path: str,
        upload_to_cdn: bool = True,
        recursive: bool = True,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, str]]:
        """
        Tối ưu tất cả files trong thư mục.
        
        Args:
            directory_path: Đường dẫn thư mục
            upload_to_cdn: Upload lên CDN
            recursive: Đệ quy vào thư mục con
            include_patterns: Các pattern bao gồm
            exclude_patterns: Các pattern loại trừ
            
        Returns:
            Dict {file_path: {format: url}}
        """
        # Tạo patterns
        include_regex = None
        exclude_regex = None
        
        if include_patterns:
            include_regex = re.compile("|".join(include_patterns))
            
        if exclude_patterns:
            exclude_regex = re.compile("|".join(exclude_patterns))
            
        # Kết quả
        result = {}
        
        # Duyệt qua các file trong thư mục
        for root, dirs, files in os.walk(directory_path):
            # Xử lý các file
            for file in files:
                # Đường dẫn đầy đủ
                file_path = os.path.join(root, file)
                
                # Kiểm tra patterns
                if include_regex and not include_regex.search(file_path):
                    continue
                    
                if exclude_regex and exclude_regex.search(file_path):
                    continue
                    
                # Tối ưu file
                try:
                    asset_type = self._get_asset_type(file_path)
                    
                    if asset_type == AssetType.IMAGE and self.optimize_images:
                        # Tối ưu ảnh
                        urls = await self.optimize_image(file_path, upload_to_cdn=upload_to_cdn)
                        if urls:
                            result[file_path] = urls
                            
                    elif asset_type == AssetType.CSS and self.optimize_css:
                        # Minify CSS
                        url = await self.minify_css(file_path, upload_to_cdn=upload_to_cdn)
                        if url:
                            result[file_path] = {"css": url}
                            
                    elif asset_type == AssetType.JS and self.optimize_js:
                        # Minify JS
                        url = await self.minify_js(file_path, upload_to_cdn=upload_to_cdn)
                        if url:
                            result[file_path] = {"js": url}
                            
                    elif asset_type == AssetType.HTML and self.optimize_html:
                        # TODO: Tối ưu HTML
                        pass
                        
                    elif asset_type == AssetType.FONT and self.optimize_fonts:
                        # TODO: Tối ưu font
                        pass
                        
                    elif self.compress_assets:
                        # Nén file khác
                        compressed_paths = await self.compress_file(file_path)
                        if compressed_paths:
                            result[file_path] = {"compressed": compressed_paths}
                            
                except Exception as e:
                    logger.error(f"Lỗi khi tối ưu file '{file_path}': {str(e)}")
                    
            # Dừng đệ quy nếu không cần
            if not recursive:
                break
                
        return result
        
    async def generate_asset_manifest(
        self,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Tạo manifest cho assets.
        
        Args:
            output_path: Đường dẫn output
            
        Returns:
            Asset manifest
        """
        try:
            # Tạo manifest
            manifest = {
                "assets": {},
                "generated_at": datetime.now().isoformat(),
                "version": "1.0"
            }
            
            # Duyệt qua các file trong thư mục output
            for root, dirs, files in os.walk(self.output_dir):
                for file in files:
                    # Bỏ qua files .gz và .br
                    if file.endswith((".gz", ".br")):
                        continue
                        
                    # Đường dẫn đầy đủ
                    file_path = os.path.join(root, file)
                    
                    # Đường dẫn tương đối
                    rel_path = os.path.relpath(file_path, self.output_dir)
                    
                    # Lấy hash của file
                    async with aiofiles.open(file_path, "rb") as f:
                        content = await f.read()
                        file_hash = hashlib.md5(content).hexdigest()
                        
                    # Lấy loại file
                    asset_type = self._get_asset_type(file_path)
                    
                    # Kiểm tra các phiên bản nén
                    gzip_path = f"{file_path}.gz"
                    brotli_path = f"{file_path}.br"
                    
                    compressed_versions = {}
                    
                    if os.path.exists(gzip_path):
                        compressed_versions["gzip"] = os.path.relpath(gzip_path, self.output_dir)
                        
                    if os.path.exists(brotli_path):
                        compressed_versions["brotli"] = os.path.relpath(brotli_path, self.output_dir)
                        
                    # Thêm vào manifest
                    manifest["assets"][rel_path] = {
                        "hash": file_hash,
                        "size": os.path.getsize(file_path),
                        "type": asset_type,
                        "mime_type": mimetypes.guess_type(file_path)[0],
                        "compressed": compressed_versions
                    }
                    
                    # Thêm URL nếu sử dụng CDN
                    if self.use_cdn:
                        manifest["assets"][rel_path]["url"] = f"{cdn_manager.provider.base_url}/{rel_path}"
                        
            # Lưu manifest nếu cần
            if output_path:
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(manifest, indent=2))
                    
            return manifest
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo asset manifest: {str(e)}")
            return {"assets": {}, "error": str(e)}

# Tạo singleton instance
asset_optimizer = AssetOptimizer()
