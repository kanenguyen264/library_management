from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime


class AdminBase(BaseModel):
    """Schema cơ bản cho Admin."""

    username: str
    email: EmailStr
    full_name: Optional[str] = None


class AdminCreate(AdminBase):
    """Schema tạo mới Admin."""

    password: str = Field(..., min_length=8)
    is_super_admin: bool = False

    @validator("password")
    def password_strength(cls, v):
        """Kiểm tra độ mạnh của mật khẩu."""
        if len(v) < 8:
            raise ValueError("Mật khẩu phải có ít nhất 8 ký tự")
        if not any(c.isupper() for c in v):
            raise ValueError("Mật khẩu phải có ít nhất 1 ký tự viết hoa")
        if not any(c.islower() for c in v):
            raise ValueError("Mật khẩu phải có ít nhất 1 ký tự viết thường")
        if not any(c.isdigit() for c in v):
            raise ValueError("Mật khẩu phải có ít nhất 1 chữ số")
        return v


class AdminUpdate(BaseModel):
    """Schema cập nhật Admin."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None


class AdminInDB(AdminBase):
    """Schema Admin trong database."""

    id: int
    is_super_admin: bool
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminInfo(BaseModel):
    """Schema thông tin Admin."""

    id: int
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    is_super_admin: bool
    is_active: bool

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Schema thông tin Role."""

    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class AdminWithRoles(AdminInfo):
    """Schema Admin với danh sách roles."""

    roles: List[RoleInfo] = []

    class Config:
        from_attributes = True


class AdminListResponse(BaseModel):
    """Schema phản hồi danh sách Admin."""

    items: List[AdminInfo]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0

    class Config:
        from_attributes = True


class AdminResponse(AdminInfo):
    """Schema phản hồi chi tiết Admin."""

    roles: Optional[List[RoleInfo]] = None
    permissions: Optional[List[str]] = None
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True
