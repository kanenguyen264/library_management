from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ApiRequestLogBase(BaseModel):
    endpoint: str
    method: str
    user_id: Optional[int] = None
    admin_id: Optional[int] = None
    ip_address: Optional[str] = None
    status_code: int
    response_time: Optional[float] = None
    request_body: Optional[Dict[str, Any]] = None
    response_body: Optional[Dict[str, Any]] = None


class ApiRequestLogCreate(ApiRequestLogBase):
    pass


class ApiRequestLogUpdate(BaseModel):
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    response_body: Optional[Dict[str, Any]] = None


class ApiRequestLogRead(ApiRequestLogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ApiRequestLogList(BaseModel):
    items: list[ApiRequestLogRead]
    total: int
    page: int
    size: int
    pages: int


class ApiRequestLog(ApiRequestLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class ApiRequestLogFilter(BaseModel):
    endpoint: Optional[str] = None
    method: Optional[str] = None
    user_id: Optional[int] = None
    status_code: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
