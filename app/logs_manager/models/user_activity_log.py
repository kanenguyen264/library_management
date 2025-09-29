from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func

from app.core.db import Base


class UserActivityLog(Base):
    __tablename__ = "user_activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("user_data.users.id"), nullable=False, index=True
    )
    activity_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại hoạt động (view, bookmark, comment, rate, etc)",
    )
    resource_id = Column(
        String,
        nullable=False,
        index=True,
        comment="ID tài nguyên liên quan (sách, bài viết)",
    )
    resource_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Loại tài nguyên (book, article, etc)",
    )
    activity_metadata = Column(JSON, comment="Dữ liệu bổ sung về hoạt động")
    device_info = Column(JSON, comment="Thông tin thiết bị")
    session_id = Column(String, index=True, comment="ID phiên người dùng")
    ip_address = Column(String, comment="Địa chỉ IP người dùng")
    user_agent = Column(String, comment="Thông tin user agent")
    duration = Column(Integer, comment="Thời gian thực hiện hoạt động (giây)")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
