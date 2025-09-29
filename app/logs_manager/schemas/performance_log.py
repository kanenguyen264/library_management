from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class PerformanceLogBase(BaseModel):
    operation_type: str
    component: str
    operation_name: Optional[str] = None
    duration_ms: float
    resource_usage: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    success: Optional[bool] = True


class PerformanceLogCreate(PerformanceLogBase):
    pass


class PerformanceLogUpdate(BaseModel):
    duration_ms: Optional[float] = None
    resource_usage: Optional[Dict[str, Any]] = None


class PerformanceLogRead(PerformanceLogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PerformanceLogList(BaseModel):
    items: list[PerformanceLogRead]
    total: int
    page: int
    size: int
    pages: int


class PerformanceLog(PerformanceLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class PerformanceLogFilter(BaseModel):
    operation_type: Optional[str] = None
    component: Optional[str] = None
    status_code: Optional[int] = None
    min_duration_ms: Optional[float] = None
    max_duration_ms: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
