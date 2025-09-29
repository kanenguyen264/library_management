from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func

from app.core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("user_data.users.id"), nullable=False, index=True
    )
    user_type = Column(String, index=True, comment="Loại người dùng (admin, regular)")
    event_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại sự kiện audit (data_access, data_modification, etc)",
    )
    resource_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại tài nguyên (user_data, financial_data, sensitive_info, etc)",
    )
    resource_id = Column(String, nullable=False, index=True)
    action = Column(
        String,
        nullable=False,
        index=True,
        comment="Hành động (view, modify, export, etc)",
    )
    before_value = Column(JSON, comment="Giá trị trước khi thay đổi")
    after_value = Column(JSON, comment="Giá trị sau khi thay đổi")
    audit_metadata = Column(JSON, comment="Metadata bổ sung")
    ip_address = Column(String, comment="Địa chỉ IP")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
