from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
from datetime import datetime, date
import json


class SystemMetricBase(BaseModel):
    """Schema cơ bản cho SystemMetric."""

    metric_name: str
    metric_value: float
    unit: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SystemMetricCreate(SystemMetricBase):
    """Schema tạo mới SystemMetric."""

    pass


class SystemMetricUpdate(BaseModel):
    """Schema cập nhật SystemMetric."""

    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    unit: Optional[str] = None
    timestamp: Optional[datetime] = None


class SystemMetricInDB(SystemMetricBase):
    """Schema SystemMetric trong database."""

    id: int
    recorded_at: datetime

    class Config:
        from_attributes = True


class SystemMetricInfo(SystemMetricInDB):
    """Schema thông tin SystemMetric."""

    class Config:
        from_attributes = True
