from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    JSON,
    ForeignKey,
    Text,
    Boolean,
)
from sqlalchemy.sql import func

from app.core.db import Base


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    error_type = Column(String, nullable=False, index=True, comment="Loại lỗi")
    severity = Column(
        String,
        nullable=False,
        index=True,
        comment="Mức độ nghiêm trọng (critical, error, warning, info)",
    )
    message = Column(String, nullable=False)
    stack_trace = Column(Text)
    user_id = Column(
        Integer, ForeignKey("user_data.users.id"), nullable=True, index=True
    )
    request_path = Column(String, comment="Đường dẫn request")
    context = Column(JSON, comment="Ngữ cảnh xảy ra lỗi")
    component = Column(String, index=True, comment="Thành phần hệ thống gặp lỗi")
    handled = Column(Boolean, default=False, comment="Đã xử lý hay chưa")
    resolution_status = Column(String, comment="Trạng thái giải quyết")
    resolution_time = Column(DateTime(timezone=True))
    frequency = Column(Integer, default=1, comment="Số lần xuất hiện")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
