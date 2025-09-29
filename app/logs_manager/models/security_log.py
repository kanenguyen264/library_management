from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.sql import func

from app.core.db import Base


class SecurityLog(Base):
    __tablename__ = "security_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại sự kiện bảo mật (suspicious_access, bruteforce, permission_violation, etc)",
    )
    severity = Column(
        String,
        nullable=False,
        index=True,
        comment="Mức độ nghiêm trọng (critical, high, medium, low)",
    )
    user_id = Column(
        Integer, ForeignKey("user_data.users.id"), nullable=True, index=True
    )
    ip_address = Column(String, index=True, comment="Địa chỉ IP")
    user_agent = Column(String, comment="Thông tin user agent")
    request_path = Column(String, comment="Đường dẫn request")
    details = Column(JSON, comment="Chi tiết sự kiện")
    action_taken = Column(String, comment="Hành động đã thực hiện (block, alert, etc)")
    is_resolved = Column(Boolean, default=False, index=True)
    resolution_notes = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
