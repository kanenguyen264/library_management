from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ErrorLogBase(BaseModel):
    error_type: str
    severity: str
    message: str
    stack_trace: Optional[str] = None
    user_id: Optional[int] = None
    request_path: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    component: Optional[str] = None
    handled: Optional[bool] = False
    resolution_status: Optional[str] = None
    resolution_time: Optional[datetime] = None
    frequency: Optional[int] = 1


class ErrorLogCreate(ErrorLogBase):
    pass


class ErrorLogUpdate(BaseModel):
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    request_data: Optional[Dict[str, Any]] = None


class ErrorLogRead(ErrorLogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ErrorLogList(BaseModel):
    items: list[ErrorLogRead]
    total: int
    page: int
    size: int
    pages: int


class ErrorLog(ErrorLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class ErrorLogFilter(BaseModel):
    error_level: Optional[str] = None
    error_code: Optional[str] = None
    source: Optional[str] = None
    user_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
