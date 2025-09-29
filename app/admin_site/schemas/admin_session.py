from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AdminSessionBase(BaseModel):
    """Schema cơ bản cho phiên đăng nhập của admin."""

    admin_id: int
    ip_address: str
    user_agent: str


class AdminSessionCreate(AdminSessionBase):
    """Schema tạo phiên đăng nhập admin."""

    token: str
    expires_at: datetime


class AdminSessionResponse(AdminSessionBase):
    """Schema thông tin phiên đăng nhập admin."""

    id: int
    token: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    expires_at: datetime
    status: str = "active"

    class Config:
        from_attributes = True


class AdminSessionList(BaseModel):
    """Schema danh sách phiên đăng nhập admin."""

    id: int
    ip_address: str
    user_agent: str
    status: str
    login_time: datetime
    logout_time: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminSessionInfo(BaseModel):
    """Schema thông tin chi tiết phiên đăng nhập admin."""

    id: int
    admin_id: int
    ip_address: str
    user_agent: str
    login_time: datetime
    logout_time: Optional[datetime] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
