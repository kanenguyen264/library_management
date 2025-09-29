from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class AdminActivityLogBase(BaseModel):
    admin_id: int
    activity_type: str
    action: str
    resource_id: str
    resource_type: str
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: Optional[bool] = True


class AdminActivityLogCreate(AdminActivityLogBase):
    timestamp: Optional[datetime] = None


class AdminActivityLog(AdminActivityLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class AdminActivityLogRead(AdminActivityLog):
    admin_username: Optional[str] = None
    admin_email: Optional[str] = None
    formatted_timestamp: Optional[str] = None

    class Config:
        from_attributes = True


class AdminActivityLogList(BaseModel):
    items: List[AdminActivityLog]
    total: int
    page: int
    size: int
    pages: int


class AdminActivityLogFilter(BaseModel):
    admin_id: Optional[int] = None
    activity_type: Optional[str] = None
    resource_type: Optional[str] = None
    success: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
