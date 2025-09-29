from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class AuditLogBase(BaseModel):
    user_id: int
    user_type: str
    event_type: str
    resource_type: str
    resource_id: str
    action: str
    before_value: Optional[Dict[str, Any]] = None
    after_value: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None


class AuditLogCreate(AuditLogBase):
    timestamp: Optional[datetime] = None


class AuditLog(AuditLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class AuditLogList(BaseModel):
    items: List[AuditLog]
    total: int
    page: int
    size: int
    pages: int


class AuditLogFilter(BaseModel):
    user_id: Optional[int] = None
    user_type: Optional[str] = None
    event_type: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
