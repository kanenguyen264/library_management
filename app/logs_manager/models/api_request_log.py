from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    JSON,
    ForeignKey,
    LargeBinary,
    Boolean,
)
from sqlalchemy.sql import func

from app.core.db import Base


class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String, nullable=False, index=True, comment="Đường dẫn API")
    method = Column(String, nullable=False, index=True, comment="Phương thức HTTP")
    status_code = Column(Integer, index=True, comment="Mã trạng thái phản hồi")
    request_body = Column(JSON, comment="Nội dung request (đã sanitize)")
    response_body = Column(JSON, comment="Nội dung phản hồi (đã sanitize)")
    headers = Column(JSON, comment="Headers của request (đã sanitize)")
    query_params = Column(JSON, comment="Query parameters")
    user_id = Column(
        Integer, ForeignKey("user_data.users.id"), nullable=True, index=True
    )
    ip_address = Column(String, index=True, comment="Địa chỉ IP")
    user_agent = Column(String, comment="Thông tin user agent")
    duration_ms = Column(Integer, comment="Thời gian xử lý (milliseconds)")
    error = Column(String, comment="Lỗi nếu có")
    is_error = Column(Boolean, default=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
