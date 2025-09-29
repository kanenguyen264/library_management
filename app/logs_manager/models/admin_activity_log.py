from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.sql import func

from app.core.db import Base


class AdminActivityLog(Base):
    __tablename__ = "admin_activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(
        Integer, ForeignKey("user_data.users.id"), nullable=False, index=True
    )
    activity_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại hoạt động quản trị (create, update, delete, etc)",
    )
    action = Column(String, nullable=False, comment="Hành động cụ thể")
    resource_id = Column(
        String, nullable=False, index=True, comment="ID tài nguyên tác động"
    )
    resource_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại tài nguyên (book, user, setting, etc)",
    )
    before_state = Column(JSON, comment="Trạng thái trước khi thay đổi")
    after_state = Column(JSON, comment="Trạng thái sau khi thay đổi")
    details = Column(JSON, comment="Chi tiết hành động")
    ip_address = Column(String, comment="Địa chỉ IP quản trị viên")
    user_agent = Column(String, comment="Thông tin user agent")
    success = Column(Boolean, default=True, comment="Thao tác thành công hay không")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
