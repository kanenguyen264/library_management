from sqlalchemy import Column, Integer, String, DateTime, JSON, Float, Boolean
from sqlalchemy.sql import func

from app.core.db import Base


class PerformanceLog(Base):
    __tablename__ = "performance_logs"

    id = Column(Integer, primary_key=True, index=True)
    operation_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại hoạt động (database_query, api_call, render, etc)",
    )
    component = Column(
        String,
        nullable=False,
        index=True,
        comment="Thành phần hệ thống (database, api, frontend, etc)",
    )
    operation_name = Column(String, index=True, comment="Tên cụ thể của hoạt động")
    duration_ms = Column(
        Float, nullable=False, comment="Thời gian thực hiện (milliseconds)"
    )
    resource_usage = Column(JSON, comment="Tài nguyên sử dụng (CPU, RAM, etc)")
    context = Column(JSON, comment="Ngữ cảnh hoạt động")
    performance_metadata = Column(JSON, comment="Thông tin bổ sung")
    success = Column(Boolean, default=True, comment="Hoạt động thành công hay không")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
