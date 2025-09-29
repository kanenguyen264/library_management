from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        Index("idx_admin_sessions_admin_id", "admin_id"),
        Index("idx_admin_sessions_login_time", "login_time"),
        Index("idx_admin_sessions_status", "status"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("admin.admins.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    login_time = Column(DateTime, nullable=False)
    logout_time = Column(DateTime, nullable=True)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    admin = relationship("Admin", back_populates="sessions")
