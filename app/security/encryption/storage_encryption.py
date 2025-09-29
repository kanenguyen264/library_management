import os
import json
import base64
import tempfile
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes, hmac
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from typing import Union, BinaryIO, Dict, Any, Optional
from app.core.config import get_settings

settings = get_settings()

class FileEncryption:
    """
    Class để mã hóa và giải mã files. Sử dụng AES-256-CBC với HMAC-SHA256 để xác thực.
    """
    
    def __init__(
        self, 
        key: Optional[bytes] = None,
        salt_size: int = 16,
        iterations: int = 100000
    ):
        """
        Khởi tạo với một key có sẵn hoặc từ biến môi trường.
        
        Args:
            key: Khóa mã hóa (tùy chọn, nếu không có sẽ lấy từ env)
            salt_size: Kích thước salt cho key derivation
            iterations: Số lần lặp lại cho PBKDF2
        """
        self.backend = default_backend()
        self.salt_size = salt_size
        self.iterations = iterations
        
        # Lấy key từ env nếu không được cung cấp
        if key is None:
            env_key = os.environ.get("STORAGE_ENCRYPTION_KEY")
            if env_key:
                try:
                    key = base64.b64decode(env_key)
                except Exception:
                    # Nếu không decode được, sử dụng trực tiếp
                    key = env_key.encode()
                    
            # Nếu vẫn không có key, tạo mới cho dev và cảnh báo cho prod
            if not key:
                if settings.APP_ENV == "production":
                    raise ValueError("STORAGE_ENCRYPTION_KEY must be set in production environment")
                
                # Tạo key mới cho dev
                key = os.urandom(32)  # 256 bits
                os.environ["STORAGE_ENCRYPTION_KEY"] = base64.b64encode(key).decode()
        
        self.master_key = key if isinstance(key, bytes) else key.encode()
        
    def derive_key(self, salt: bytes) -> Dict[str, bytes]:
        """
        Tạo encryption key và authentication key từ master key và salt.
        
        Args:
            salt: Salt cho key derivation
            
        Returns:
            Dict với encryption_key và auth_key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=48,  # 32 bytes for encryption + 16 bytes for auth
            salt=salt,
            iterations=self.iterations,
            backend=self.backend
        )
        
        derived = kdf.derive(self.master_key)
        return {
            "encryption_key": derived[:32],
            "auth_key": derived[32:]
        }
        
    def encrypt_file(
        self, 
        input_file: Union[str, BinaryIO], 
        output_file: Optional[Union[str, BinaryIO]] = None
    ) -> Optional[str]:
        """
        Mã hóa một file.
        
        Args:
            input_file: Đường dẫn file hoặc file-like object để đọc
            output_file: Đường dẫn file hoặc file-like object để ghi output (tùy chọn)
            
        Returns:
            Đường dẫn file output nếu output_file là None, None nếu không
        """
        # Tạo salt mới
        salt = os.urandom(self.salt_size)
        
        # Tạo IV ngẫu nhiên
        iv = os.urandom(16)
        
        # Tạo keys
        keys = self.derive_key(salt)
        enc_key = keys["encryption_key"]
        auth_key = keys["auth_key"]
        
        # Thiết lập cipher
        cipher = Cipher(
            algorithms.AES(enc_key),
            modes.CBC(iv),
            backend=self.backend
        )
        encryptor = cipher.encryptor()
        
        # Thiết lập HMAC
        h = hmac.HMAC(auth_key, hashes.SHA256(), backend=self.backend)
        
        # Mở file input
        if isinstance(input_file, str):
            input_file_obj = open(input_file, "rb")
            close_input = True
        else:
            input_file_obj = input_file
            close_input = False
            
        # Xác định output
        if output_file is None:
            # Nếu không có output_file, tạo temp file và trả về đường dẫn
            fd, temp_path = tempfile.mkstemp(suffix=".enc")
            output_file_obj = os.fdopen(fd, "wb")
            close_output = True
        elif isinstance(output_file, str):
            output_file_obj = open(output_file, "wb")
            close_output = True
        else:
            output_file_obj = output_file
            close_output = False
            
        try:
            # Viết metadata
            output_file_obj.write(salt)
            output_file_obj.write(iv)
            
            # Update HMAC với salt và iv
            h.update(salt)
            h.update(iv)
            
            # Đọc và mã hóa từng chunk
            padder = padding.PKCS7(128).padder()
            
            while True:
                chunk = input_file_obj.read(1024 * 1024)  # Đọc 1MB mỗi lần
                if not chunk:
                    break
                    
                # Padding cho chunk cuối
                if len(chunk) < 1024 * 1024:
                    chunk = padder.update(chunk) + padder.finalize()
                    
                # Mã hóa chunk
                encrypted_chunk = encryptor.update(chunk)
                
                # Update HMAC
                h.update(encrypted_chunk)
                
                # Viết chunk đã mã hóa
                output_file_obj.write(encrypted_chunk)
                
            # Viết phần còn lại và HMAC
            output_file_obj.write(encryptor.finalize())
            output_file_obj.write(h.finalize())
            
            # Trả về đường dẫn nếu cần
            if output_file is None:
                return temp_path
            return None
                
        finally:
            # Đóng các file
            if close_input:
                input_file_obj.close()
            if close_output:
                output_file_obj.close()
                
    def decrypt_file(
        self, 
        input_file: Union[str, BinaryIO], 
        output_file: Optional[Union[str, BinaryIO]] = None
    ) -> Optional[str]:
        """
        Giải mã một file.
        
        Args:
            input_file: Đường dẫn file hoặc file-like object để đọc
            output_file: Đường dẫn file hoặc file-like object để ghi output (tùy chọn)
            
        Returns:
            Đường dẫn file output nếu output_file là None, None nếu không
        """
        # Mở file input
        if isinstance(input_file, str):
            input_file_obj = open(input_file, "rb")
            close_input = True
        else:
            input_file_obj = input_file
            close_input = False
            
        # Xác định output
        if output_file is None:
            # Tạo temp file và trả về đường dẫn
            fd, temp_path = tempfile.mkstemp(suffix=".dec")
            output_file_obj = os.fdopen(fd, "wb")
            close_output = True
        elif isinstance(output_file, str):
            output_file_obj = open(output_file, "wb")
            close_output = True
        else:
            output_file_obj = output_file
            close_output = False
            
        try:
            # Đọc metadata
            salt = input_file_obj.read(self.salt_size)
            iv = input_file_obj.read(16)
            
            # Tạo keys
            keys = self.derive_key(salt)
            enc_key = keys["encryption_key"]
            auth_key = keys["auth_key"]
            
            # Thiết lập HMAC
            h = hmac.HMAC(auth_key, hashes.SHA256(), backend=self.backend)
            h.update(salt)
            h.update(iv)
            
            # Đọc và verify HMAC
            # Cần đọc toàn bộ file để lấy HMAC ở cuối
            encrypted_data = input_file_obj.read()
            stored_hmac = encrypted_data[-32:]  # HMAC SHA256 = 32 bytes
            encrypted_data = encrypted_data[:-32]
            
            # Update HMAC với dữ liệu đã mã hóa
            h.update(encrypted_data)
            
            # Verify HMAC
            try:
                h.verify(stored_hmac)
            except Exception:
                raise ValueError("HMAC verification failed: File may have been tampered with")
                
            # Thiết lập cipher để giải mã
            cipher = Cipher(
                algorithms.AES(enc_key),
                modes.CBC(iv),
                backend=self.backend
            )
            decryptor = cipher.decryptor()
            
            # Giải mã
            decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()
            
            # Xử lý padding
            unpadder = padding.PKCS7(128).unpadder()
            try:
                unpadded_data = unpadder.update(decrypted_data) + unpadder.finalize()
            except Exception:
                raise ValueError("Padding is incorrect: File may be corrupted")
                
            # Viết dữ liệu đã giải mã
            output_file_obj.write(unpadded_data)
            
            # Trả về đường dẫn nếu cần
            if output_file is None:
                return temp_path
            return None
                
        finally:
            # Đóng các file
            if close_input:
                input_file_obj.close()
            if close_output:
                output_file_obj.close()
