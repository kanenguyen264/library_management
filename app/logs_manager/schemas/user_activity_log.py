from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class UserActivityLogBase(BaseModel):
    user_id: int
    activity_type: str
    resource_id: str
    resource_type: str
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="activity_metadata")
    device_info: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    duration: Optional[int] = None

    class Config:
        from_attributes = True
        validate_by_name = True
        # Các tên field được xử lý trong Field với alias


class UserActivityLogCreate(UserActivityLogBase):
    pass


class UserActivityLogUpdate(BaseModel):
    description: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class UserActivityLogRead(UserActivityLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class UserActivityLogList(BaseModel):
    items: list[UserActivityLogRead]
    total: int
    page: int
    size: int
    pages: int


class UserActivityLog(UserActivityLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class UserActivityLogFilter(BaseModel):
    user_id: Optional[int] = None
    activity_type: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
