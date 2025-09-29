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

    class Config:
        from_attributes = True


class AdminLoginResponse(BaseModel):
    """Schema phản hồi đăng nhập Admin."""

    access_token: str
    refresh_token: str
    token_type: str
    admin: AdminInfo


class AdminRefreshTokenRequest(BaseModel):
    """Schema yêu cầu làm mới token."""

    refresh_token: str


class AdminChangePasswordRequest(BaseModel):
    """Schema yêu cầu đổi mật khẩu."""

    current_password: str
    new_password: str = Field(..., min_length=8)

    @validator("new_password")
    def password_strength(cls, v):
        """Kiểm tra độ mạnh của mật khẩu mới."""
        if len(v) < 8:
            raise ValueError("Mật khẩu phải có ít nhất 8 ký tự")
        if not any(c.isupper() for c in v):
            raise ValueError("Mật khẩu phải có ít nhất 1 ký tự viết hoa")
        if not any(c.islower() for c in v):
            raise ValueError("Mật khẩu phải có ít nhất 1 ký tự viết thường")
        if not any(c.isdigit() for c in v):
            raise ValueError("Mật khẩu phải có ít nhất 1 chữ số")
        return v


class TokenRefresh(BaseModel):
    """Schema yêu cầu làm mới token."""

    refresh_token: str
