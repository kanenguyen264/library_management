from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AuthenticationLogBase(BaseModel):
    user_id: Optional[int] = None
    event_type: str
    action: Optional[str] = None
    status: str
    is_success: Optional[bool] = True
    ip_address: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    user_agent: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    failure_reason: Optional[str] = None
    auth_method: Optional[str] = None
    session_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class AuthenticationLogCreate(AuthenticationLogBase):
    pass


class AuthenticationLogUpdate(BaseModel):
    status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class AuthenticationLogRead(AuthenticationLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class AuthenticationLogList(BaseModel):
    items: list[AuthenticationLogRead]
    total: int
    page: int
    size: int
    pages: int


class AuthenticationLog(AuthenticationLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class AuthenticationLogFilter(BaseModel):
    user_id: Optional[int] = None
    action: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
