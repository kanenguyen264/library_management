from sqlalchemy import Column, Integer, String, DateTime, JSON, Float, ForeignKey
from sqlalchemy.sql import func

from app.core.db import Base


class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("user_data.users.id"), nullable=True, index=True
    )
    session_id = Column(String, index=True, comment="ID phiên người dùng")
    query = Column(String, nullable=False, index=True, comment="Từ khóa tìm kiếm")
    filters = Column(JSON, comment="Các bộ lọc áp dụng")
    results_count = Column(Integer, default=0, comment="Số lượng kết quả trả về")
    category = Column(
        String, index=True, comment="Danh mục tìm kiếm (sách, tác giả, v.v)"
    )
    source = Column(String, comment="Nguồn tìm kiếm (web, mobile app, v.v)")
    search_duration = Column(Float, comment="Thời gian thực hiện tìm kiếm (ms)")
    clicked_results = Column(JSON, comment="Danh sách kết quả được click")
    ip_address = Column(String, comment="Địa chỉ IP người dùng")
    user_agent = Column(String, comment="Thông tin user agent")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    class Config:
        orm_mode = True
