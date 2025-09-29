from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
from datetime import datetime


class SystemSettingBase(BaseModel):
    """Schema cơ bản cho SystemSetting."""

    key: str
    value: str
    data_type: str
    description: Optional[str] = None
    is_public: bool = False
    group: Optional[str] = None


class SystemSettingCreate(SystemSettingBase):
    """Schema tạo mới SystemSetting."""

    @validator("data_type")
    def validate_data_type(cls, v):
        """Kiểm tra kiểu dữ liệu hợp lệ."""
        valid_types = [
            "string",
            "integer",
            "float",
            "boolean",
            "json",
            "date",
            "datetime",
            "array",
        ]
        if v not in valid_types:
            raise ValueError(
                f"Kiểu dữ liệu phải là một trong: {', '.join(valid_types)}"
            )
        return v


class SystemSettingUpdate(BaseModel):
    """Schema cập nhật SystemSetting."""

    value: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    group: Optional[str] = None


class SystemSettingInDB(SystemSettingBase):
    """Schema SystemSetting trong database."""

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SystemSettingInfo(BaseModel):
    """Schema thông tin SystemSetting."""

    id: int
    key: str
    value: str
    data_type: str
    description: Optional[str] = None
    is_public: bool
    group: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SystemSettingPublic(BaseModel):
    """Schema SystemSetting public."""

    key: str
    value: str
    data_type: str
    description: Optional[str] = None
    group: Optional[str] = None

    class Config:
        from_attributes = True
