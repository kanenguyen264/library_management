from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class PermissionBase(BaseModel):
    """Schema cơ bản cho Permission."""

    name: str
    resource: str
    action: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    """Schema tạo mới Permission."""

    pass


class PermissionUpdate(BaseModel):
    """Schema cập nhật Permission."""

    name: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    description: Optional[str] = None


class PermissionInDB(PermissionBase):
    """Schema Permission trong database."""

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PermissionInfo(BaseModel):
    """Schema thông tin Permission."""

    id: int
    name: str
    resource: str
    action: str
    description: Optional[str] = None

    class Config:
        from_attributes = True
