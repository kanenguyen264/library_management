from sqlalchemy import Column, Integer, String, Float, DateTime, Index, func
from app.core.db import Base


class SystemMetric(Base):
    __tablename__ = "system_metrics"
    __table_args__ = (
        Index("idx_system_metrics_metric_name", "metric_name"),
        Index("idx_system_metrics_timestamp", "timestamp"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    unit = Column(String(50), nullable=True)
    timestamp = Column(DateTime, nullable=False)
    recorded_at = Column(DateTime, default=func.now())
