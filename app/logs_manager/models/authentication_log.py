from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.sql import func

from app.core.db import Base


class AuthenticationLog(Base):
    __tablename__ = "authentication_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("user_data.users.id"), nullable=True, index=True
    )
    event_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại sự kiện (login, logout, password_reset, etc)",
    )
    action = Column(
        String,
        nullable=True,
        index=True,
        comment="Hành động cụ thể thực hiện",
    )
    status = Column(
        String, nullable=False, index=True, comment="Trạng thái (success, failure)"
    )
    is_success = Column(Boolean, default=True, index=True)
    ip_address = Column(String, index=True, comment="Địa chỉ IP")
    location = Column(JSON, comment="Thông tin vị trí địa lý dựa trên IP")
    user_agent = Column(String, comment="Thông tin user agent")
    device_info = Column(JSON, comment="Thông tin thiết bị")
    failure_reason = Column(String, comment="Lý do thất bại (nếu có)")
    auth_method = Column(String, comment="Phương thức xác thực (password, oauth, etc)")
    session_id = Column(String, comment="ID phiên đăng nhập (nếu thành công)")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
