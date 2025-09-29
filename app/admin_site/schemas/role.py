from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class RoleBase(BaseModel):
    """Schema cơ bản cho Role."""

    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    """Schema tạo mới Role."""

    pass


class RoleUpdate(BaseModel):
    """Schema cập nhật Role."""

    name: Optional[str] = None
    description: Optional[str] = None


class RoleInDB(RoleBase):
    """Schema Role trong database."""

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleInfo(BaseModel):
    """Schema thông tin Role."""

    id: int
    name: str
    description: Optional[str] = None

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


class RoleWithPermissions(RoleInfo):
    """Schema Role với danh sách permissions."""

    permissions: List[PermissionInfo] = []

    class Config:
        from_attributes = True
