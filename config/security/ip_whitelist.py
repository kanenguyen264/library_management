"""
Cấu hình IP Whitelist.

Module này định nghĩa các cấu hình danh sách IP được phép truy cập:
- Danh sách IP được phép truy cập vào admin site
- Danh sách IP được phép truy cập vào API endpoint nhạy cảm
- Danh sách CIDR được phép
"""

from typing import List, Optional, Dict, Set, Union
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import ipaddress


class IPWhitelistConfig(BaseSettings):
    """
    Cấu hình IP Whitelist.

    Attributes:
        IP_WHITELIST_ENABLED: Bật/tắt tính năng IP whitelist
        IP_WHITELIST_ADMIN_IPS: Danh sách IP được phép truy cập admin site
        IP_WHITELIST_API_IPS: Danh sách IP được phép truy cập API
        IP_WHITELIST_ADMIN_CIDR: Danh sách CIDR được phép truy cập admin site
        IP_WHITELIST_API_CIDR: Danh sách CIDR được phép truy cập API
        IP_WHITELIST_ADMIN_PATH_PREFIX: Prefix đường dẫn admin
        IP_WHITELIST_EXCEPTION_PATHS: Các đường dẫn được miễn trừ
        IP_WHITELIST_LOG_BLOCKED: Ghi log các IP bị chặn
    """

    IP_WHITELIST_ENABLED: bool = Field(
        default=False, description="Bật/tắt tính năng IP whitelist"
    )

    IP_WHITELIST_ADMIN_IPS: List[str] = Field(
        default=["127.0.0.1", "::1"],
        description="Danh sách IP được phép truy cập admin site",
    )

    IP_WHITELIST_API_IPS: List[str] = Field(
        default=[], description="Danh sách IP được phép truy cập API"
    )

    IP_WHITELIST_ADMIN_CIDR: List[str] = Field(
        default=["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
        description="Danh sách CIDR được phép truy cập admin site",
    )

    IP_WHITELIST_API_CIDR: List[str] = Field(
        default=[], description="Danh sách CIDR được phép truy cập API"
    )

    IP_WHITELIST_ADMIN_PATH_PREFIX: str = Field(
        default="/admin", description="Prefix đường dẫn admin"
    )

    IP_WHITELIST_EXCEPTION_PATHS: List[str] = Field(
        default=["/api/v1/health", "/api/v1/docs", "/api/v1/openapi.json"],
        description="Các đường dẫn được miễn trừ",
    )

    IP_WHITELIST_LOG_BLOCKED: bool = Field(
        default=True, description="Ghi log các IP bị chặn"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="IP_WHITELIST_",
    )

    @validator("IP_WHITELIST_ADMIN_IPS", "IP_WHITELIST_API_IPS", each_item=True)
    def validate_ip(cls, v):
        """Validate IP address format."""
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid IP address: {v}")

    @validator("IP_WHITELIST_ADMIN_CIDR", "IP_WHITELIST_API_CIDR", each_item=True)
    def validate_cidr(cls, v):
        """Validate CIDR format."""
        try:
            ipaddress.ip_network(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid CIDR: {v}")

    def is_ip_allowed_for_admin(self, ip: str) -> bool:
        """
        Kiểm tra xem IP có được phép truy cập admin site không.

        Args:
            ip: Địa chỉ IP cần kiểm tra

        Returns:
            True nếu được phép, False nếu không
        """
        if not self.IP_WHITELIST_ENABLED:
            return True

        # Kiểm tra IP riêng lẻ
        if ip in self.IP_WHITELIST_ADMIN_IPS:
            return True

        # Kiểm tra IP thuộc CIDR
        try:
            ip_obj = ipaddress.ip_address(ip)
            for cidr in self.IP_WHITELIST_ADMIN_CIDR:
                network = ipaddress.ip_network(cidr)
                if ip_obj in network:
                    return True
        except ValueError:
            return False

        return False

    def is_ip_allowed_for_api(self, ip: str) -> bool:
        """
        Kiểm tra xem IP có được phép truy cập API không.

        Args:
            ip: Địa chỉ IP cần kiểm tra

        Returns:
            True nếu được phép, False nếu không
        """
        if not self.IP_WHITELIST_ENABLED:
            return True

        # Nếu danh sách rỗng, cho phép tất cả
        if not self.IP_WHITELIST_API_IPS and not self.IP_WHITELIST_API_CIDR:
            return True

        # Kiểm tra IP riêng lẻ
        if ip in self.IP_WHITELIST_API_IPS:
            return True

        # Kiểm tra IP thuộc CIDR
        try:
            ip_obj = ipaddress.ip_address(ip)
            for cidr in self.IP_WHITELIST_API_CIDR:
                network = ipaddress.ip_network(cidr)
                if ip_obj in network:
                    return True
        except ValueError:
            return False

        return False

    def is_path_excepted(self, path: str) -> bool:
        """
        Kiểm tra xem đường dẫn có được miễn trừ khỏi whitelist không.

        Args:
            path: Đường dẫn cần kiểm tra

        Returns:
            True nếu được miễn trừ, False nếu không
        """
        for excepted_path in self.IP_WHITELIST_EXCEPTION_PATHS:
            if path.startswith(excepted_path):
                return True
        return False

    def get_middleware_config(self) -> dict:
        """
        Tạo cấu hình cho middleware IP whitelist.

        Returns:
            Dict cấu hình middleware
        """
        return {
            "enabled": self.IP_WHITELIST_ENABLED,
            "admin_ips": self.IP_WHITELIST_ADMIN_IPS,
            "api_ips": self.IP_WHITELIST_API_IPS,
            "admin_cidr": self.IP_WHITELIST_ADMIN_CIDR,
            "api_cidr": self.IP_WHITELIST_API_CIDR,
            "admin_path_prefix": self.IP_WHITELIST_ADMIN_PATH_PREFIX,
            "exception_paths": self.IP_WHITELIST_EXCEPTION_PATHS,
            "log_blocked": self.IP_WHITELIST_LOG_BLOCKED,
        }


# Khởi tạo cấu hình
ip_whitelist_config = IPWhitelistConfig()
