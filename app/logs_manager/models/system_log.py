from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean
from sqlalchemy.sql import func

from app.core.db import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại sự kiện hệ thống (startup, shutdown, config_change, etc)",
    )
    component = Column(
        String,
        nullable=False,
        index=True,
        comment="Thành phần hệ thống (app, database, cache, etc)",
    )
    message = Column(String, nullable=False)
    details = Column(JSON, comment="Chi tiết sự kiện")
    environment = Column(
        String, index=True, comment="Môi trường (production, staging, development)"
    )
    server_name = Column(String, index=True)
    success = Column(Boolean, default=True, comment="Sự kiện thành công hay không")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
