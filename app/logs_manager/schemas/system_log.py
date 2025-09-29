from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class SystemLogBase(BaseModel):
    event_type: str
    component: str
    message: str
    details: Optional[Dict[str, Any]] = None
    environment: Optional[str] = None
    server_name: Optional[str] = None
    success: Optional[bool] = True


class SystemLogCreate(SystemLogBase):
    timestamp: Optional[datetime] = None


class SystemLog(SystemLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class SystemLogList(BaseModel):
    items: List[SystemLog]
    total: int
    page: int
    size: int
    pages: int


class SystemLogFilter(BaseModel):
    event_type: Optional[str] = None
    component: Optional[str] = None
    environment: Optional[str] = None
    success: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
