from sqlalchemy import Column, Integer, String, Text, DateTime, Index, func
from app.core.db import Base


class SystemHealth(Base):
    __tablename__ = "system_health"
    __table_args__ = (
        Index("idx_system_health_component", "component"),
        Index("idx_system_health_status", "status"),
        Index("idx_system_health_last_updated", "last_updated"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    component = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)
    message = Column(Text, nullable=True)
    last_updated = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
