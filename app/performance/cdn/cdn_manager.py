from typing import Dict, List, Any, Optional, Union, Set, Tuple
import os
import time
import asyncio
import hashlib
import mimetypes
import logging
import json
import aiofiles
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
import re
from urllib.parse import urlparse, urljoin

from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

class CDNProvider:
    """Lớp cơ sở cho các CDN providers."""
    
    async def upload(self, file_path: str, cdn_path: str) -> str:
        """
        Upload file lên CDN.
        
        Args:
            file_path: Đường dẫn file cục bộ
            cdn_path: Đường dẫn trên CDN
            
        Returns:
            URL của file trên CDN
        """
        raise NotImplementedError("Subclasses must implement upload()")
        
    async def delete(self, cdn_path: str) -> bool:
        """
        Xóa file khỏi CDN.
        
        Args:
            cdn_path: Đường dẫn trên CDN
            
        Returns:
            True nếu thành công
        """
        raise NotImplementedError("Subclasses must implement delete()")
        
    async def list_files(self, prefix: str = "") -> List[str]:
        """
        Liệt kê files trên CDN.
        
        Args:
            prefix: Tiền tố đường dẫn
            
        Returns:
            Danh sách đường dẫn
        """
        raise NotImplementedError("Subclasses must implement list_files()")
        
    async def invalidate(self, cdn_paths: List[str]) -> bool:
        """
        Vô hiệu hóa cache cho files.
        
        Args:
            cdn_paths: Danh sách đường dẫn trên CDN
            
        Returns:
            True nếu thành công
        """
        raise NotImplementedError("Subclasses must implement invalidate()")

class LocalCDNProvider(CDNProvider):
    """Provider sử dụng thư mục cục bộ làm CDN."""
    
    def __init__(
        self, 
        storage_path: str = None,
        base_url: str = None
    ):
        """
        Khởi tạo local provider.
        
        Args:
            storage_path: Thư mục lưu trữ
            base_url: URL cơ sở
        """
        self.storage_path = storage_path or settings.STORAGE_LOCAL_PATH
        self.base_url = base_url or f"http://{settings.SERVER_HOST}:{settings.SERVER_PORT}/static"
        
        # Tạo thư mục nếu chưa tồn tại
        os.makedirs(self.storage_path, exist_ok=True)
        
        logger.info(f"Khởi tạo Local CDN provider với storage_path='{self.storage_path}', base_url='{self.base_url}'")
        
    async def upload(self, file_path: str, cdn_path: str) -> str:
        """
        Copy file vào thư mục lưu trữ.
        
        Args:
            file_path: Đường dẫn file cục bộ
            cdn_path: Đường dẫn trên CDN
            
        Returns:
            URL của file
        """
        # Tạo đường dẫn đích
        dest_path = os.path.join(self.storage_path, cdn_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # Copy file
        try:
            async with aiofiles.open(file_path, "rb") as src_file:
                content = await src_file.read()
                
            async with aiofiles.open(dest_path, "wb") as dest_file:
                await dest_file.write(content)
                
            # Trả về URL
            return urljoin(self.base_url, cdn_path)
            
        except Exception as e:
            logger.error(f"Lỗi khi upload file '{file_path}' lên Local CDN: {str(e)}")
            raise
            
    async def delete(self, cdn_path: str) -> bool:
        """
        Xóa file từ thư mục lưu trữ.
        
        Args:
            cdn_path: Đường dẫn trên CDN
            
        Returns:
            True nếu thành công
        """
        try:
            # Lấy đường dẫn đầy đủ
            file_path = os.path.join(self.storage_path, cdn_path)
            
            # Kiểm tra file tồn tại
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Lỗi khi xóa file '{cdn_path}' từ Local CDN: {str(e)}")
            return False
            
    async def list_files(self, prefix: str = "") -> List[str]:
        """
        Liệt kê files trong thư mục lưu trữ.
        
        Args:
            prefix: Tiền tố đường dẫn
            
        Returns:
            Danh sách đường dẫn
        """
        try:
            base_path = os.path.join(self.storage_path, prefix)
            if not os.path.exists(base_path):
                return []
                
            result = []
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.storage_path)
                    result.append(rel_path)
                    
            return result
            
        except Exception as e:
            logger.error(f"Lỗi khi liệt kê files từ Local CDN: {str(e)}")
            return []
            
    async def invalidate(self, cdn_paths: List[str]) -> bool:
        """
        Vô hiệu hóa cache cho files (không áp dụng cho Local CDN).
        
        Args:
            cdn_paths: Danh sách đường dẫn trên CDN
            
        Returns:
            True luôn (không làm gì)
        """
        # Local CDN không cần invalidate
        return True

class CDNManager:
    """
    Quản lý nội dung trên CDN.
    Cung cấp:
    - Upload files lên CDN
    - Quản lý đường dẫn
    - Vô hiệu hóa cache
    - Version management cho tài nguyên tĩnh
    """
    
    def __init__(
        self,
        provider: Optional[CDNProvider] = None,
        cache_max_age: int = 86400,  # 1 day
        asset_root: str = None,
        versioning: bool = True,
        version_query_param: str = "v",
        manifest_file: str = None
    ):
        """
        Khởi tạo CDN Manager.
        
        Args:
            provider: CDN provider
            cache_max_age: Thời gian cache (giây)
            asset_root: Thư mục gốc của assets
            versioning: Bật/tắt versioning
            version_query_param: Tham số query cho version
            manifest_file: File manifest cho versioning
        """
        # Khởi tạo provider
        self.provider = provider or LocalCDNProvider()
        
        # Cấu hình CDN
        self.cache_max_age = cache_max_age
        self.versioning = versioning
        self.version_query_param = version_query_param
        
        # Đường dẫn
        self.asset_root = asset_root or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "static"
        )
        
        # Manifest file
        if manifest_file:
            self.manifest_file = manifest_file
        else:
            self.manifest_file = os.path.join(self.asset_root, "asset-manifest.json")
            
        # Version manifest
        self.manifest = {}
        self.last_manifest_update = 0
        
        logger.info(
            f"Khởi tạo CDN Manager với provider={provider.__class__.__name__}, "
            f"asset_root='{self.asset_root}', versioning={versioning}"
        )
        
    async def _load_manifest(self, force: bool = False) -> Dict[str, str]:
        """
        Tải manifest file.
        
        Args:
            force: Tải lại bất kể đã có hay chưa
            
        Returns:
            Version manifest
        """
        # Kiểm tra xem có cần tải lại không
        now = time.time()
        if not force and self.manifest and (now - self.last_manifest_update) < 300:  # 5 phút
            return self.manifest
            
        try:
            # Kiểm tra file tồn tại
            if os.path.exists(self.manifest_file):
                async with aiofiles.open(self.manifest_file, "r") as f:
                    content = await f.read()
                    self.manifest = json.loads(content)
                    self.last_manifest_update = now
                    logger.debug(f"Đã tải manifest file với {len(self.manifest)} entries")
            else:
                # Khởi tạo manifest trống
                self.manifest = {}
                self.last_manifest_update = now
                
            return self.manifest
            
        except Exception as e:
            logger.error(f"Lỗi khi tải manifest file: {str(e)}")
            return {}
            
    async def _save_manifest(self) -> bool:
        """
        Lưu manifest file.
        
        Returns:
            True nếu thành công
        """
        try:
            # Đảm bảo thư mục tồn tại
            os.makedirs(os.path.dirname(self.manifest_file), exist_ok=True)
            
            # Lưu file
            async with aiofiles.open(self.manifest_file, "w") as f:
                await f.write(json.dumps(self.manifest, indent=2))
                
            logger.debug(f"Đã lưu manifest file với {len(self.manifest)} entries")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu manifest file: {str(e)}")
            return False
            
    async def _generate_version(self, file_path: str) -> str:
        """
        Tạo version cho file.
        
        Args:
            file_path: Đường dẫn file
            
        Returns:
            Version string
        """
        try:
            # Sử dụng hash nội dung và thời gian sửa đổi
            stat = os.stat(file_path)
            mtime = int(stat.st_mtime)
            
            # Tạo hash của file
            async with aiofiles.open(file_path, "rb") as f:
                content = await f.read()
                file_hash = hashlib.md5(content).hexdigest()[:8]
                
            return f"{file_hash}{mtime}"
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo version cho file '{file_path}': {str(e)}")
            return datetime.now().strftime("%Y%m%d%H%M%S")
            
    async def upload_asset(
        self,
        file_path: str,
        cdn_path: Optional[str] = None,
        update_manifest: bool = True
    ) -> str:
        """
        Upload file lên CDN.
        
        Args:
            file_path: Đường dẫn file cục bộ
            cdn_path: Đường dẫn trên CDN (None để tự tạo)
            update_manifest: Cập nhật manifest
            
        Returns:
            URL của file trên CDN
        """
        try:
            # Kiểm tra file tồn tại
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File '{file_path}' không tồn tại")
                
            # Tạo cdn_path nếu chưa có
            if not cdn_path:
                if file_path.startswith(self.asset_root):
                    # File nằm trong asset_root
                    rel_path = os.path.relpath(file_path, self.asset_root)
                    cdn_path = rel_path.replace("\\", "/")
                else:
                    # File không nằm trong asset_root
                    filename = os.path.basename(file_path)
                    cdn_path = f"uploads/{filename}"
                    
            # Tạo version nếu cần
            if self.versioning:
                version = await self._generate_version(file_path)
                
                # Tải manifest nếu cần
                await self._load_manifest()
                
                # Lưu version vào manifest
                if update_manifest:
                    self.manifest[cdn_path] = version
                    await self._save_manifest()
                    
            # Upload lên CDN
            url = await self.provider.upload(file_path, cdn_path)
            
            # Trả về URL với version nếu cần
            if self.versioning:
                version = self.manifest.get(cdn_path, "")
                if version:
                    separator = "?" if "?" not in url else "&"
                    url = f"{url}{separator}{self.version_query_param}={version}"
                    
            return url
            
        except Exception as e:
            logger.error(f"Lỗi khi upload asset '{file_path}': {str(e)}")
            raise
            
    async def upload_directory(
        self,
        directory_path: str,
        cdn_prefix: Optional[str] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Upload toàn bộ thư mục lên CDN.
        
        Args:
            directory_path: Đường dẫn thư mục
            cdn_prefix: Tiền tố đường dẫn trên CDN
            exclude_patterns: Các pattern loại trừ
            
        Returns:
            Dict {local_path: cdn_url}
        """
        # Tạo pattern loại trừ
        exclude_regex = None
        if exclude_patterns:
            exclude_regex = re.compile("|".join(exclude_patterns))
            
        # Kết quả
        result = {}
        
        # Duyệt qua các file trong thư mục
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                # Đường dẫn đầy đủ
                file_path = os.path.join(root, file)
                
                # Kiểm tra pattern loại trừ
                if exclude_regex and exclude_regex.search(file_path):
                    continue
                    
                # Tạo cdn_path
                rel_path = os.path.relpath(file_path, directory_path)
                
                if cdn_prefix:
                    cdn_path = f"{cdn_prefix}/{rel_path}".replace("\\", "/")
                else:
                    cdn_path = rel_path.replace("\\", "/")
                    
                # Upload file
                try:
                    url = await self.upload_asset(file_path, cdn_path, update_manifest=True)
                    result[file_path] = url
                except Exception as e:
                    logger.error(f"Không thể upload '{file_path}': {str(e)}")
                    
        # Lưu manifest
        if self.versioning:
            await self._save_manifest()
            
        return result
        
    async def get_asset_url(self, asset_path: str) -> str:
        """
        Lấy URL của asset với version.
        
        Args:
            asset_path: Đường dẫn asset
            
        Returns:
            URL với version
        """
        try:
            # Đảm bảo asset_path có định dạng đúng
            asset_path = asset_path.replace("\\", "/")
            
            # Tải manifest nếu cần
            if self.versioning:
                await self._load_manifest()
                
            # Lấy version từ manifest
            version = self.manifest.get(asset_path, "")
            
            # Tạo URL
            url = urljoin(self.provider.base_url, asset_path)
            
            # Thêm version nếu có
            if version:
                separator = "?" if "?" not in url else "&"
                url = f"{url}{separator}{self.version_query_param}={version}"
                
            return url
            
        except Exception as e:
            logger.error(f"Lỗi khi lấy URL cho asset '{asset_path}': {str(e)}")
            return urljoin(self.provider.base_url, asset_path)
            
    async def invalidate_assets(self, asset_paths: List[str]) -> bool:
        """
        Vô hiệu hóa cache cho assets.
        
        Args:
            asset_paths: Danh sách đường dẫn assets
            
        Returns:
            True nếu thành công
        """
        try:
            # Gọi invalidate của provider
            success = await self.provider.invalidate(asset_paths)
            
            # Cập nhật manifest nếu cần
            if success and self.versioning:
                # Tải manifest
                await self._load_manifest()
                
                # Cập nhật version cho từng asset
                for asset_path in asset_paths:
                    # Chuẩn hóa đường dẫn
                    normalized_path = asset_path.replace("\\", "/")
                    
                    # Tìm file cục bộ
                    local_path = os.path.join(self.asset_root, normalized_path)
                    
                    if os.path.exists(local_path):
                        # Tạo version mới
                        version = await self._generate_version(local_path)
                        self.manifest[normalized_path] = version
                    else:
                        # Xóa khỏi manifest nếu file không tồn tại
                        if normalized_path in self.manifest:
                            del self.manifest[normalized_path]
                            
                # Lưu manifest
                await self._save_manifest()
                
            return success
            
        except Exception as e:
            logger.error(f"Lỗi khi invalidate assets: {str(e)}")
            return False
            
    async def delete_asset(self, asset_path: str) -> bool:
        """
        Xóa asset khỏi CDN.
        
        Args:
            asset_path: Đường dẫn asset
            
        Returns:
            True nếu thành công
        """
        try:
            # Chuẩn hóa đường dẫn
            normalized_path = asset_path.replace("\\", "/")
            
            # Xóa khỏi CDN
            success = await self.provider.delete(normalized_path)
            
            # Cập nhật manifest nếu cần
            if success and self.versioning:
                # Tải manifest
                await self._load_manifest()
                
                # Xóa khỏi manifest
                if normalized_path in self.manifest:
                    del self.manifest[normalized_path]
                    await self._save_manifest()
                    
            return success
            
        except Exception as e:
            logger.error(f"Lỗi khi xóa asset '{asset_path}': {str(e)}")
            return False
            
    async def sync_directory(
        self,
        directory_path: str,
        cdn_prefix: Optional[str] = None,
        delete_missing: bool = False,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Đồng bộ thư mục lên CDN.
        
        Args:
            directory_path: Đường dẫn thư mục
            cdn_prefix: Tiền tố đường dẫn trên CDN
            delete_missing: Xóa files không còn tồn tại
            exclude_patterns: Các pattern loại trừ
            
        Returns:
            Dict {local_path: cdn_url}
        """
        try:
            # Upload thư mục
            result = await self.upload_directory(
                directory_path,
                cdn_prefix,
                exclude_patterns
            )
            
            # Xóa files không còn tồn tại
            if delete_missing:
                # Lấy danh sách files trên CDN
                prefix = cdn_prefix or ""
                cdn_files = await self.provider.list_files(prefix)
                
                # Lấy danh sách files cục bộ
                local_files = []
                for root, dirs, files in os.walk(directory_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, directory_path)
                        
                        if cdn_prefix:
                            cdn_path = f"{cdn_prefix}/{rel_path}".replace("\\", "/")
                        else:
                            cdn_path = rel_path.replace("\\", "/")
                            
                        local_files.append(cdn_path)
                        
                # Tìm files chỉ có trên CDN
                files_to_delete = [f for f in cdn_files if f.startswith(prefix) and f not in local_files]
                
                # Xóa files
                for file_path in files_to_delete:
                    await self.delete_asset(file_path)
                    
            return result
            
        except Exception as e:
            logger.error(f"Lỗi khi đồng bộ thư mục '{directory_path}': {str(e)}")
            return {}

# Tạo singleton instance
cdn_manager = CDNManager()
