from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Float,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from app.core.db import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        Index("idx_user_preferences_user_id", "user_id"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    font_family = Column(String(100), nullable=True)
    font_size = Column(Float, nullable=True)
    theme = Column(String(50), nullable=True)
    reading_mode = Column(String(50), nullable=True)
    language = Column(String(50), nullable=True)
    notifications_enabled = Column(Boolean, default=True)
    email_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=True)
    reading_speed_wpm = Column(Integer, nullable=True)
    auto_bookmark = Column(Boolean, default=True)
    display_recommendations = Column(Boolean, default=True)
    privacy_level = Column(String(50), default="public")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="preferences")
