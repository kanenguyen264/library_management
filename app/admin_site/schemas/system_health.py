from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
from datetime import datetime, date
import json


class SystemHealthBase(BaseModel):
    """Schema cơ bản cho SystemHealth."""

    component: str
    status: str
    message: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class SystemHealthCreate(SystemHealthBase):
    """Schema tạo mới SystemHealth."""

    @validator("status")
    def validate_status(cls, v):
        """Kiểm tra trạng thái hợp lệ."""
        valid_status = ["healthy", "warning", "critical", "unknown"]
        if v not in valid_status:
            raise ValueError(f"Trạng thái phải là một trong: {', '.join(valid_status)}")
        return v


class SystemHealthUpdate(BaseModel):
    """Schema cập nhật SystemHealth."""

    component: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    last_updated: Optional[datetime] = None

    @validator("status")
    def validate_status(cls, v):
        """Kiểm tra trạng thái hợp lệ."""
        if v is None:
            return v

        valid_status = ["healthy", "warning", "critical", "unknown"]
        if v not in valid_status:
            raise ValueError(f"Trạng thái phải là một trong: {', '.join(valid_status)}")
        return v


class SystemHealthInDB(SystemHealthBase):
    """Schema SystemHealth trong database."""

    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SystemHealthInfo(SystemHealthInDB):
    """Schema thông tin SystemHealth."""

    class Config:
        from_attributes = True
