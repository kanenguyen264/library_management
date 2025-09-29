from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class SecurityLogBase(BaseModel):
    event_type: str
    severity: str
    user_id: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_path: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    action_taken: Optional[str] = None
    is_resolved: Optional[bool] = False
    resolution_notes: Optional[str] = None


class SecurityLogCreate(SecurityLogBase):
    timestamp: Optional[datetime] = None


class SecurityLog(SecurityLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class SecurityLogList(BaseModel):
    items: List[SecurityLog]
    total: int
    page: int
    size: int
    pages: int


class SecurityLogFilter(BaseModel):
    event_type: Optional[str] = None
    severity: Optional[str] = None
    user_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_resolved: Optional[bool] = None
