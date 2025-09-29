from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index, func
from app.core.db import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"
    __table_args__ = (
        Index("idx_system_settings_key", "key"),
        Index("idx_system_settings_group", "group"),
        Index("idx_system_settings_is_public", "is_public"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    data_type = Column(String(50), nullable=False)
    is_public = Column(Boolean, default=False)
    group = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
